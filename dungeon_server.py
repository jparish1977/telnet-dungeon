#!/usr/bin/env python3
"""
Telnet Dungeon Crawler - BBS-style multiplayer dungeon game
Run: python dungeon_server.py [port]
Connect: telnet localhost 2323
"""

import asyncio
import sys
import random

from dungeon.config import *
from dungeon.items import *
from dungeon.persistence import (
    save_character, load_character, list_saves, delete_save,
    load_bans, save_bans,
    load_custom_monsters, save_custom_monsters,
    save_builtin_overrides,
    load_custom_floor, save_custom_floor,
    load_scene_themes, save_scene_themes,
    SAVE_DIR,
)
from dungeon.floor import (
    DUNGEON_FLOORS, generate_floor,
    get_floor_size, get_floor, set_floor, get_floor_spawn, find_open_tile,
    is_tile_blocked, MAX_FLOOR,
    get_overworld, set_overworld, generate_overworld,
    get_overworld_spawn, is_overworld,
)
from dungeon.monsters import (
    MONSTERS_BY_FLOOR,
    get_monsters_for_floor,
    get_floor_monsters, spawn_floor_monsters, move_floor_monsters,
    get_monster_at, kill_monster,
)
from dungeon.character import (
    sanitize_character, validate_position,
    get_atk, get_def,
)
from dungeon.renderer_3d import render_3d_view
from dungeon.renderer_minimap import render_minimap
from dungeon.protocol.telnet import TelnetAdapter



from dungeon.world import World
from dungeon.shop import run_shop
from dungeon.combat import run_combat, run_pvp, handle_game_over, handle_pvp_death, _bar
from dungeon.menus import (
    title_screen as _title_screen,
    create_character as _create_character,
    load_character_menu as _load_character_menu,
)
from dungeon.gm.tools import (
    gm_pick_player as _gm_pick_player,
    gm_menu as _gm_menu,
)

WORLD = World()



# ── Game Session ───────────────────────────────────────────────────
class GameSession:
    def __init__(self, reader=None, writer=None, adapter=None):
        self.io = adapter if adapter else TelnetAdapter(reader, writer)
        self.char = None
        self.running = True
        self.message_log = []
        self.combat_shield_bonus = 0
        self.is_gm = False

    # ── I/O delegation ────────────────────────────────────────────
    # These delegate to self.io so existing code (self.send, self.get_char, etc.)
    # continues to work without changing every call site at once.

    async def send(self, text):
        await self.io.send(text)

    async def send_line(self, text=""):
        await self.io.send_line(text)

    async def move_to(self, row, col):
        await self.io.move_to(row, col)

    async def clear_row(self, row):
        await self.io.clear_row(row)

    async def get_input(self, prompt="> ", preserve_spaces=False, prefill=""):
        result = await self.io.get_input(prompt, preserve_spaces, prefill)
        if not self.io.running:
            self.running = False
        return result

    async def get_char(self, prompt="", redraw_on_resize=False):
        result = await self.io.get_char(prompt, redraw_on_resize)
        if not self.io.running:
            self.running = False
        return result

    # ── Terminal state (delegated to adapter) ─────────────────────

    @property
    def term_width(self):
        return self.io.term_width

    @property
    def term_height(self):
        return self.io.term_height

    @property
    def resized(self):
        return self.io.resized

    @resized.setter
    def resized(self, value):
        self.io.resized = value

    @property
    def notify_event(self):
        return self.io.notify_event

    @property
    def writer(self):
        return self.io.writer

    # ── Layout helpers ────────────────────────────────────────────

    def get_view_size(self):
        """Calculate 3D viewport size. Aspect-ratio limited, extra space goes to log."""
        map_radius = self.get_map_radius()
        map_cols = (map_radius * 2 + 1) + 4
        avail_w = self.term_width - map_cols - 4
        vw = max(20, avail_w)
        max_vh = max(8, vw // 3)
        avail_h = self.term_height - 8
        vh = min(max_vh, avail_h)
        return vw, vh

    def get_log_rows(self):
        """How many rows available for the message/chat log below the viewport."""
        vw, vh = self.get_view_size()
        used = 2 + vh + 2 + 2 + 1 + 1
        return max(2, self.term_height - used)

    def get_map_radius(self):
        return max(3, min(7, (self.term_height - 10) // 3))


    def log(self, msg):
        self.message_log.append(msg)
        if len(self.message_log) > 5:
            self.message_log.pop(0)

    async def title_screen(self):
        return await _title_screen(self, WORLD)

    async def create_character(self):
        await _create_character(self, WORLD)

    async def load_character_menu(self):
        return await _load_character_menu(self, WORLD)

    def get_atk(self):
        return self.char['base_atk'] + WEAPONS[self.char['weapon']]['atk']

    def get_def(self):
        return self.char['base_def'] + ARMOR[self.char['armor']]['def'] + self.combat_shield_bonus

    async def check_level_up(self):
        while self.char['xp'] >= self.char['xp_next']:
            self.char['level'] += 1
            self.char['xp'] -= self.char['xp_next']
            self.char['xp_next'] = int(self.char['xp_next'] * 1.5)

            hp_gain = random.randint(3, 8)
            mp_gain = random.randint(1, 4) if self.char['max_mp'] > 0 else 0
            atk_gain = random.randint(0, 2)
            def_gain = random.randint(0, 1)

            self.char['max_hp'] += hp_gain
            self.char['hp'] = self.char['max_hp']
            self.char['max_mp'] += mp_gain
            self.char['mp'] = self.char['max_mp']
            self.char['base_atk'] += atk_gain
            self.char['base_def'] += def_gain

            self.log(color(f"*** LEVEL UP! Now level {self.char['level']}! ***", YELLOW))
            self.log(f"  HP+{hp_gain} MP+{mp_gain} ATK+{atk_gain} DEF+{def_gain}")

            # Learn spells
            for spell_name, spell in SPELLS.items():
                if self.char['level'] >= spell['min_level'] and self.char['max_mp'] > 0:
                    if 'spells' not in self.char:
                        self.char['spells'] = []
                    if spell_name not in self.char['spells']:
                        self.char['spells'].append(spell_name)
                        self.log(color(f"  Learned {spell_name}!", CYAN))

    async def combat(self, monster_template, allies=None):
        return await run_combat(self, monster_template, allies)

    def _bar(self, cur, max_val, width, bar_color):
        return _bar(cur, max_val, width, bar_color)

    async def shop(self):
        await run_shop(self)

    async def game_over(self):
        await handle_game_over(self)

    async def pvp_death(self, killer_name):
        await handle_pvp_death(self, killer_name)

    async def draw_game_screen(self):
        """Render the full game screen using cursor positioning."""
        floor = self.char['floor']
        dungeon = get_floor(floor)
        px, py = self.char['x'], self.char['y']
        facing = self.char['facing']
        tw, th = self.term_width, self.term_height

        await self.send(CLEAR)

        # Row 1: Header
        online = WORLD.player_count()
        fsize = len(dungeon)
        if is_overworld(floor):
            header = f" The Overworld ({fsize}x{fsize}) [{px},{py}]"
        else:
            header = f" Dungeon of Doom - Floor {floor + 1} ({fsize}x{fsize}) [{px},{py}]"
        right_info = f"{online} online  {tw}x{th}"
        pad = tw - len(header) - len(right_info) - 2
        await self.move_to(1, 1)
        await self.send(color(header, CYAN) + ' ' * max(1, pad) + color(right_info, DIM))

        # Row 2: Character info + nearby players
        others_here = WORLD.get_players_at(floor, px, py, self.char['name'])
        await self.move_to(2, 1)
        info = f" {self.char['name']} Lv.{self.char['level']} {self.char['class']}  Facing: {DIR_NAMES[facing]}"
        if others_here:
            names = ', '.join(s.char['name'] for s in others_here)
            info += color(f"  Party: {names}", GREEN)
        await self.send(info)

        # 3D viewport fills rows 3 through (th - 7)
        vw, vh = self.get_view_size()
        # Build visible mob list for 3D renderer
        vis_mobs = [(m['x'], m['y'], m['symbol'], m['name'])
                     for m in get_floor_monsters(floor) if m['alive']]
        view_3d = render_3d_view(dungeon, px, py, facing, vw, vh, floor, vis_mobs)
        map_radius = self.get_map_radius()
        other_players = WORLD.get_players_on_floor(floor, self.char['name'])
        minimap = render_minimap(dungeon, px, py, facing, map_radius, other_players, floor)

        view_lines = view_3d.split('\n')
        view_start_row = 3

        # The column where the minimap starts (right side of 3D view)
        map_col = vw + 6

        for i, vline in enumerate(view_lines):
            row = view_start_row + i
            if row >= th - 6:
                break
            await self.move_to(row, 2)
            await self.send(vline)

        # Draw minimap beside the 3D view, vertically centered
        map_start = view_start_row + max(0, (len(view_lines) - len(minimap)) // 2)
        for i, mline in enumerate(minimap):
            row = map_start + i
            if row >= th - 6:
                break
            await self.move_to(row, map_col)
            await self.send(mline)

        # Player direction indicators around minimap edges
        if other_players:
            map_h = len(minimap)
            map_w = map_radius * 2 + 1
            mid_row = map_start + map_h // 2
            mid_col = map_col + map_w // 2

            for pname, ox, oy, _ in other_players:
                dx = ox - px
                dy = oy - py
                # Skip if within minimap view already
                if abs(dx) <= map_radius and abs(dy) <= map_radius:
                    continue
                # Calculate angle and place indicator on minimap border
                angle = math.atan2(dy, dx)
                # Map angle to edge position
                indicator = pname[0].upper()
                dist = int(math.sqrt(dx*dx + dy*dy))
                label = f"{indicator}{dist}"

                if abs(dx) >= abs(dy):
                    # Left or right edge
                    if dx > 0:
                        # Right side
                        edge_row = mid_row + int(map_h/2 * dy / max(1, abs(dx)))
                        edge_row = max(map_start, min(map_start + map_h - 1, edge_row))
                        await self.move_to(edge_row, map_col + map_w + 1)
                        await self.send(color(label + ">", GREEN))
                    else:
                        # Left side
                        edge_row = mid_row + int(map_h/2 * dy / max(1, abs(dx)))
                        edge_row = max(map_start, min(map_start + map_h - 1, edge_row))
                        await self.move_to(edge_row, map_col - len(label) - 1)
                        await self.send(color("<" + label, GREEN))
                else:
                    # Top or bottom edge
                    if dy > 0:
                        # Bottom
                        edge_col = mid_col + int(map_w/2 * dx / max(1, abs(dy)))
                        edge_col = max(map_col, min(map_col + map_w - 1, edge_col))
                        await self.move_to(map_start + map_h, edge_col)
                        await self.send(color(label + "v", GREEN))
                    else:
                        # Top
                        edge_col = mid_col + int(map_w/2 * dx / max(1, abs(dy)))
                        edge_col = max(map_col, min(map_col + map_w - 1, edge_col))
                        await self.move_to(map_start - 1, edge_col)
                        await self.send(color(label + "^", GREEN))

        # Layout from viewport bottom down:
        # [viewport ends] -> [log area] -> [status 2 rows] -> [controls] -> [prompt]
        viewport_bottom = view_start_row + len(view_lines) + 1
        log_rows = self.get_log_rows()
        log_start = viewport_bottom

        # Draw log separator
        await self.move_to(log_start, 1)
        log_label = " -- Log "
        await self.send(color(log_label + '-' * max(0, tw - len(log_label) - 1), DIM))

        # Combine local messages with global log, newest at bottom
        log_display_rows = max(1, log_rows - 1)
        combined = []
        # Interleave: global log as background, local messages on top
        combined.extend(WORLD.global_log)
        combined.extend(self.message_log)
        # Deduplicate keeping order (messages might be in both)
        seen = set()
        unique = []
        for msg in combined:
            if msg not in seen:
                seen.add(msg)
                unique.append(msg)
        display_msgs = unique[-log_display_rows:]

        for i in range(log_display_rows):
            row = log_start + 1 + i
            if row >= th - 3:
                break
            await self.move_to(row, 1)
            if i < len(display_msgs):
                await self.send(f" {display_msgs[i]}")
            else:
                await self.send(color(" ~", DIM))  # empty log line marker
        self.message_log.clear()

        # Status rows
        status_row = th - 3
        hp_w = max(8, min(15, (tw - 40) // 3))
        mp_w = max(5, min(10, (tw - 40) // 4))
        hp_bar = self._bar(self.char['hp'], self.char['max_hp'], hp_w, GREEN)
        mp_bar = self._bar(self.char['mp'], self.char['max_mp'], mp_w, CYAN)

        await self.move_to(status_row, 1)
        status = f" HP:{hp_bar}  MP:{mp_bar}  Gold:{color(str(self.char['gold']), YELLOW)}  Pot:{self.char['potions']}"
        if self.char.get('poisoned'):
            status += color(" [POISON]", MAGENTA)
        hc_tag = color(" [HC]", RED) if self.char.get('hardcore', False) else ""
        await self.send(status + hc_tag)

        await self.move_to(status_row + 1, 1)
        await self.send(f" ATK:{self.get_atk()} DEF:{self.get_def()} SPD:{self.char['spd']} XP:{self.char['xp']}/{self.char['xp_next']}  {WEAPONS[self.char['weapon']]['name']} / {ARMOR[self.char['armor']]['name']}")

        # Controls at very bottom
        ctrl_row = th - 1
        await self.move_to(ctrl_row, 1)
        controls = f" {color('W', YELLOW)}Fwd {color('A', YELLOW)}Left {color('D', YELLOW)}Right {color('S', YELLOW)}Back {color('C', YELLOW)}har {color('T', YELLOW)}alk"
        if others_here:
            controls += f" {color('P', RED)}vP"
        controls += f" {color('Q', YELLOW)}uit"
        if self.is_gm:
            controls += color(" [/]GM", MAGENTA)

        current_tile = dungeon[py][px]
        if current_tile == 4:
            if floor == 0:
                controls += f" {color('<', GREEN)}Exit {color('H', YELLOW)}Shop"
            else:
                controls += f" {color('<', GREEN)}Up {color('H', YELLOW)}Shop"
        elif current_tile == 3:
            controls += f" {color('>', RED)}Down"
        elif current_tile == 6:
            controls += f" {color('R', CYAN)}Drink"
        elif current_tile == OW_DUNGEON:
            controls += f" {color('>', RED)}Enter"
        elif current_tile == OW_TOWN:
            controls += f" {color('H', YELLOW)}Shop"

        await self.send(controls)

        # Prompt on last row
        await self.move_to(th, 1)
        await self.send(" > ")

    async def main_loop(self):
        """Main exploration loop."""
        # Validate position on entry (catches old saves, wall spawns, etc)
        if validate_position(self.char):
            self.log(color("You were relocated to a safe position.", YELLOW))

        while self.running and self.char['hp'] > 0:
            floor = self.char['floor']
            dungeon = get_floor(floor)
            px, py = self.char['x'], self.char['y']
            facing = self.char['facing']

            # Mark explored
            key = f"{floor}_{px}_{py}"
            if 'explored' not in self.char:
                self.char['explored'] = {}
            self.char['explored'][key] = True

            await self.draw_game_screen()

            current_tile = dungeon[py][px]
            cmd = (await self.get_char("", redraw_on_resize=True)).lower()

            # On resize, just redraw
            if cmd == 'resize':
                continue

            if cmd == 'q':
                save_character(self.char)
                await self.send_line(color("\r\n Character saved. Farewell!", GREEN))
                await self.get_char()
                break

            elif cmd == 't':
                # Chat - switch to line input for the message
                await self.move_to(self.term_height, 1)
                await self.send("\033[2K")  # clear the line
                msg = await self.get_input(" Say: ")
                if msg.strip():
                    WORLD.chat(self.char['name'], msg.strip())
                continue

            elif cmd == '/' and self.is_gm:
                await self.gm_menu()
                continue

            elif cmd == 'p':
                # PvP - attack another player on same tile
                others_here = WORLD.get_players_at(floor, px, py, self.char['name'])
                if not others_here:
                    self.log("No one here to fight!")
                elif len(others_here) == 1:
                    killer = others_here[0].char['name']
                    await self.pvp_combat(others_here[0])
                    if self.char['hp'] <= 0:
                        await self.pvp_death(killer)
                else:
                    await self.move_to(self.term_height, 1)
                    await self.send("\033[2K")
                    for i, s in enumerate(others_here, 1):
                        await self.send(f" [{i}]{s.char['name']} ")
                    pick = await self.get_char(" Attack who? ")
                    try:
                        idx = int(pick) - 1
                        if 0 <= idx < len(others_here):
                            killer = others_here[idx].char['name']
                            await self.pvp_combat(others_here[idx])
                            if self.char['hp'] <= 0:
                                await self.pvp_death(killer)
                    except ValueError:
                        pass
                continue

            elif cmd == 'c':
                await self.character_screen()
                continue

            elif cmd == 'h' and current_tile in (4, OW_TOWN):
                await self.shop()
                continue

            elif cmd == 'r' and current_tile == 6:
                # Fountain
                roll = random.randint(1, 6)
                if roll <= 3:
                    heal = random.randint(10, 25)
                    self.char['hp'] = min(self.char['max_hp'], self.char['hp'] + heal)
                    self.log(color(f"Refreshing water! +{heal} HP", CYAN))
                elif roll == 4:
                    mp_restore = random.randint(5, 15)
                    self.char['mp'] = min(self.char['max_mp'], self.char['mp'] + mp_restore)
                    self.log(color(f"Mystical water! +{mp_restore} MP", CYAN))
                elif roll == 5:
                    self.char['poisoned'] = True
                    self.log(color("The water is tainted! You are poisoned!", MAGENTA))
                else:
                    self.log("The fountain has dried up.")
                    dungeon[py][px] = 0  # Remove fountain
                continue

            elif cmd == '>' and (current_tile == 3 or current_tile == OW_DUNGEON):
                if current_tile == OW_DUNGEON:
                    # Enter dungeon from overworld
                    # Save overworld position
                    self.char['ow_x'] = self.char['x']
                    self.char['ow_y'] = self.char['y']
                    self.char['floor'] = 0
                    sx, sy = get_floor_spawn(0)
                    self.char['x'] = sx
                    self.char['y'] = sy
                    self.log(color("You descend into the dungeon...", YELLOW))
                else:
                    # Go deeper in dungeon
                    if self.char['floor'] >= MAX_FLOOR:
                        self.log(color("You have reached the deepest depths.", RED))
                        continue
                    self.char['floor'] += 1
                    sx, sy = get_floor_spawn(self.char['floor'])
                    self.char['x'] = sx
                    self.char['y'] = sy
                    self.log(color(f"You descend to floor {self.char['floor']+1}...", YELLOW))
                save_character(self.char)
                continue

            elif cmd == '<' and current_tile == 4:
                if floor > 0:
                    self.char['floor'] -= 1
                    # Find stairs down on previous floor
                    prev_floor = get_floor(self.char['floor'])
                    for ry in range(len(prev_floor)):
                        for rx in range(len(prev_floor[0])):
                            if prev_floor[ry][rx] == 3:
                                self.char['x'] = rx
                                self.char['y'] = ry
                    validate_position(self.char)
                    self.log(color(f"You ascend to floor {self.char['floor']+1}...", GREEN))
                    save_character(self.char)
                elif floor == 0:
                    # Exit dungeon to overworld
                    self.char['floor'] = OVERWORLD_FLOOR
                    ox = self.char.get('ow_x', get_overworld_spawn()[0])
                    oy = self.char.get('ow_y', get_overworld_spawn()[1])
                    self.char['x'] = ox
                    self.char['y'] = oy
                    validate_position(self.char)  # make sure we're not in water/mountain
                    self.log(color("You emerge into the sunlight!", GREEN))
                    save_character(self.char)
                else:
                    self.log("You're already at the top!")
                continue

            # Movement
            new_x, new_y = px, py
            new_facing = facing

            if cmd == 'w':  # Forward
                new_x = px + DIR_DX[facing]
                new_y = py + DIR_DY[facing]
            elif cmd == 's':  # Turn around / back
                new_facing = (facing + 2) % 4
            elif cmd == 'a':  # Turn left
                new_facing = (facing - 1) % 4
            elif cmd == 'd':  # Turn right
                new_facing = (facing + 1) % 4
            else:
                continue

            self.char['facing'] = new_facing

            # Check if we can move there
            if cmd == 'w':
                target = dungeon[new_y][new_x] if 0 <= new_y < len(dungeon) and 0 <= new_x < len(dungeon[0]) else 1
                # Check blocking tiles
                blocked = False
                if is_tile_blocked(target, floor):
                    if target == OW_MOUNTAIN:
                        self.log("The mountain is too steep to climb!")
                    elif target == OW_WATER:
                        self.log("You can't swim across!")
                    else:
                        self.log("You bump into a wall!")
                    blocked = True
                if blocked:
                    pass
                else:
                    self.char['x'] = new_x
                    self.char['y'] = new_y

                    # Check for treasure
                    if target == 5:
                        t_key = f"{floor}_{new_x}_{new_y}"
                        if t_key not in self.char.get('treasures_found', []):
                            gold_found = random.randint(10, 50) * (floor + 1)
                            self.char['gold'] += gold_found
                            if 'treasures_found' not in self.char:
                                self.char['treasures_found'] = []
                            self.char['treasures_found'].append(t_key)

                            # Sometimes find items
                            roll = random.randint(1, 10)
                            if roll <= 2:
                                self.char['potions'] += 1
                                self.log(color(f"Found {gold_found} gold and a potion!", YELLOW))
                            else:
                                self.log(color(f"Found a chest with {gold_found} gold!", YELLOW))

                    # Overworld interactions
                    if target == OW_DUNGEON:
                        self.log(color("You see a dark dungeon entrance!", RED))
                    elif target == OW_TOWN:
                        self.log(color("You enter a town. [H] to visit the shop.", GREEN))
                    elif target == OW_FOREST:
                        if random.randint(1, 8) == 1:
                            self.log(color("The forest rustles ominously...", DIM))

                    # Check if we walked into a monster
                    mob = get_monster_at(floor, new_x, new_y)
                    if mob:
                        allies = WORLD.get_players_at(floor, new_x, new_y, self.char['name'])
                        ally_names = ', '.join(s.char['name'] for s in allies)
                        if allies:
                            WORLD.broadcast(f"{self.char['name']} and {ally_names} fight a {mob['name']}!", YELLOW, exclude=self)
                        result = await self.combat(mob, allies)
                        if result == 'dead':
                            WORLD.broadcast(f"{self.char['name']} has perished on floor {floor+1}!", RED)
                            await self.game_over()
                            if self.char.get('hardcore', False):
                                return
                            continue
                        elif result == 'victory':
                            kill_monster(mob)
                            if allies:
                                WORLD.broadcast(f"{self.char['name']}'s party slew a {mob['name']}!", GREEN, exclude=self)
                            else:
                                WORLD.broadcast(f"{self.char['name']} slew a {mob['name']} on floor {floor+1}!", GREEN, exclude=self)
                        save_character(self.char)

            # Poison tick
            if self.char.get('poisoned') and cmd == 'w':
                poison_dmg = random.randint(1, 3)
                self.char['hp'] -= poison_dmg
                # 15% chance to wear off each step
                if random.randint(1, 100) <= 15:
                    self.char['poisoned'] = False
                    self.log(color(f"Poison deals {poison_dmg} damage... but it wears off!", GREEN))
                else:
                    self.log(color(f"Poison deals {poison_dmg} damage!", MAGENTA))
                if self.char['hp'] <= 0:
                    await self.game_over()
                    if self.char.get('hardcore', False):
                        return
                    continue

            # Move monsters on this floor
            player_positions = [(self.char['x'], self.char['y'])]
            for s in WORLD.get_players_at(floor, -1, -1):  # won't match anyone
                pass
            # Gather all player positions on this floor
            for _, s in WORLD.sessions.items():
                if s.char and s.char['floor'] == floor and s != self:
                    player_positions.append((s.char['x'], s.char['y']))
            move_floor_monsters(floor, player_positions)

            # Check if a monster walked into us
            mob = get_monster_at(floor, self.char['x'], self.char['y'])
            if mob:
                self.log(color(f"A {mob['name']} ambushes you!", RED))
                allies = WORLD.get_players_at(floor, self.char['x'], self.char['y'], self.char['name'])
                result = await self.combat(mob, allies)
                if result == 'dead':
                    WORLD.broadcast(f"{self.char['name']} was slain by a {mob['name']}!", RED)
                    await self.game_over()
                    if self.char.get('hardcore', False):
                        return
                    continue
                elif result == 'victory':
                    kill_monster(mob)
                    WORLD.broadcast(f"{self.char['name']} slew a {mob['name']}!", GREEN, exclude=self)

            save_character(self.char)

    async def gm_pick_player(self, prompt="Pick player: "):
        return await _gm_pick_player(self, WORLD, prompt)

    async def gm_menu(self):
        await _gm_menu(self, WORLD)

    async def character_screen(self):
        """Show character status screen."""
        c = self.char
        await self.send(CLEAR)
        mode_str = color(" [HARDCORE]", RED) if c.get('hardcore', False) else color(" [NORMAL]", GREEN)
        await self.send_line(color("=======================================", CYAN))
        await self.send_line(color(f"  {c['name']} the {c['class']}", WHITE) + mode_str)
        await self.send_line(color("=======================================", CYAN))
        await self.send_line()
        await self.send_line(f"  Level:    {c['level']}")
        await self.send_line(f"  XP:       {c['xp']} / {c['xp_next']}")
        await self.send_line(f"  HP:       {c['hp']} / {c['max_hp']}")
        await self.send_line(f"  MP:       {c['mp']} / {c['max_mp']}")
        await self.send_line(f"  ATK:      {self.get_atk()} (base {c['base_atk']} + {WEAPONS[c['weapon']]['name']})")
        await self.send_line(f"  DEF:      {self.get_def()} (base {c['base_def']} + {ARMOR[c['armor']]['name']})")
        await self.send_line(f"  SPD:      {c['spd']}")
        await self.send_line(f"  Gold:     {c['gold']}")
        await self.send_line(f"  Potions:  {c['potions']}")
        await self.send_line(f"  Kills:    {c['kills']}")
        await self.send_line(f"  Floor:    {c['floor'] + 1}")
        if c.get('poisoned'):
            await self.send_line(color("  STATUS:   POISONED", MAGENTA))
        await self.send_line()
        spells = c.get('spells', [])
        if spells:
            await self.send_line(color("  Known Spells:", CYAN))
            for sp in spells:
                info = SPELLS[sp]
                await self.send_line(f"    {sp}: {info['desc']} (MP: {info['cost']})")
        await self.send_line()
        await self.get_char(color("  Press any key to return...", DIM))

    async def run(self):
        """Main entry point for a game session."""
        await self.io.negotiate()

        while self.running:
            choice = await self.title_screen()

            if choice == 'Q':
                await self.send_line(color("\nFarewell, adventurer!\n", CYAN))
                break

            elif choice == 'N':
                await self.create_character()
                WORLD.add_player(self)
                WORLD.broadcast(f"{self.char['name']} has entered the dungeon!", GREEN, exclude=self)
                await self.main_loop()
                WORLD.remove_player(self)

            elif choice == 'L':
                if await self.load_character_menu():
                    WORLD.add_player(self)
                    WORLD.broadcast(f"{self.char['name']} has returned to the dungeon!", GREEN, exclude=self)
                    await self.main_loop()
                    WORLD.remove_player(self)

        await self.io.close()


# ── Server ─────────────────────────────────────────────────────────
async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"[+] Connection from {addr} ({WORLD.player_count()} online)")
    session = GameSession(reader, writer)
    try:
        await session.run()
    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        print(f"[-] Error with {addr}: {e}")
    finally:
        WORLD.remove_player(session)
        print(f"[-] Disconnected: {addr} ({WORLD.player_count()} online)")
        try:
            writer.close()
        except Exception:
            pass


async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', PORT)
    addrs = ', '.join(str(s.getsockname()) for s in server.sockets)
    print(f"""
+---------------------------------------------------+
|        DUNGEON CRAWLER OF DOOM - BBS Server        |
+---------------------------------------------------+
|  Listening on: {addrs:36s}|
|  Connect: telnet localhost {PORT:<24d}|
+---------------------------------------------------+
""")
    async with server:
        await server.serve_forever()


async def local_play():
    """Run a single-player session locally — no telnet needed."""
    from dungeon.protocol.stdio import StdioAdapter
    adapter = StdioAdapter()
    session = GameSession(adapter=adapter)
    try:
        await session.run()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        WORLD.remove_player(session)


if __name__ == '__main__':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    try:
        if '--local' in sys.argv:
            asyncio.run(local_play())
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shut down.")
