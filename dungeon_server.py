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



class World:
    """Shared state for all connected players."""
    def __init__(self):
        self.sessions = {}       # name -> GameSession
        self.global_log = []     # recent global messages
        self.max_log = 50
        self.banned = load_bans()  # list of banned character names (lowercase)

    def add_player(self, session):
        if session.char:
            self.sessions[session.char['name']] = session

    def remove_player(self, session):
        if session.char and session.char['name'] in self.sessions:
            self.broadcast(f"{session.char['name']} has left the dungeon.", MAGENTA, exclude=session)
            del self.sessions[session.char['name']]

    def get_players_on_floor(self, floor, exclude_name=None):
        """Get list of (name, x, y, facing) for all players on a floor."""
        players = []
        for name, s in self.sessions.items():
            if s.char and s.char['floor'] == floor and name != exclude_name:
                players.append((name, s.char['x'], s.char['y'], s.char['facing']))
        return players

    def get_players_at(self, floor, x, y, exclude_name=None):
        """Get sessions of players at a specific tile."""
        result = []
        for name, s in self.sessions.items():
            if (s.char and s.char['floor'] == floor
                    and s.char['x'] == x and s.char['y'] == y
                    and name != exclude_name):
                result.append(s)
        return result

    def broadcast(self, msg, msg_color=WHITE, exclude=None):
        """Send a message to all connected players."""
        formatted = color(msg, msg_color)
        self.global_log.append(formatted)
        if len(self.global_log) > self.max_log:
            self.global_log.pop(0)
        for name, s in self.sessions.items():
            if s != exclude:
                s.message_log.append(formatted)
                s.notify_event.set()

    def chat(self, sender, msg):
        """Broadcast a chat message from a player."""
        formatted = f"{color(sender, YELLOW)}: {msg}"
        self.global_log.append(formatted)
        if len(self.global_log) > self.max_log:
            self.global_log.pop(0)
        for name, s in self.sessions.items():
            s.message_log.append(formatted)
            s.notify_event.set()

    def player_count(self):
        return len(self.sessions)

    def is_banned(self, name):
        return name.lower() in self.banned

    def ban_player(self, name):
        lname = name.lower()
        if lname not in self.banned:
            self.banned.append(lname)
            save_bans(self.banned)

    def unban_player(self, name):
        lname = name.lower()
        if lname in self.banned:
            self.banned.remove(lname)
            save_bans(self.banned)

    async def kick_player(self, name, reason="Kicked by GM"):
        if name in self.sessions:
            s = self.sessions[name]
            try:
                await s.send_line(color(f"\r\n*** {reason} ***", RED))
                s.running = False
                await s.io.close()
            except Exception:
                pass
            self.broadcast(f"{name} was kicked: {reason}", RED)
            if name in self.sessions:
                del self.sessions[name]
            return True
        return False


WORLD = World()


# ── Game Session ───────────────────────────────────────────────────
class GameSession:
    def __init__(self, reader, writer):
        self.io = TelnetAdapter(reader, writer)
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
        await self.send(CLEAR)
        w = self.term_width

        # Use big ASCII art only if terminal is wide enough
        if w >= 72:
            await self.send_line(color("=" * min(w - 2, 68), CYAN))
            await self.send_line()
            await self.send_line(color("  ____  _   _ _   _  ____ _____ ___  _   _", RED))
            await self.send_line(color(" |  _ \\| | | | \\ | |/ ___| ____/ _ \\| \\ | |", RED))
            await self.send_line(color(" | | | | | | |  \\| | |  _|  _|| | | |  \\| |", YELLOW))
            await self.send_line(color(" | |_| | |_| | |\\  | |_| | |__| |_| | |\\  |", YELLOW))
            await self.send_line(color(" |____/ \\___/|_| \\_|\\____|_____\\___/|_| \\_|", GREEN))
            await self.send_line()
        else:
            await self.send_line(color("=" * min(w - 2, 40), CYAN))
            await self.send_line()
            await self.send_line(color("     D U N G E O N", RED))
            await self.send_line()

        await self.send_line(color("   +===================================+", MAGENTA))
        await self.send_line(color("   | C R A W L E R   o f   D O O M    |", MAGENTA))
        await self.send_line(color("   +===================================+", MAGENTA))
        await self.send_line()
        await self.send_line(color("=" * min(w - 2, 68), CYAN))
        await self.send_line()
        await self.send_line(color("  A Wizardry-Style Dungeon Crawler", DIM))
        online = WORLD.player_count()
        if online > 0:
            await self.send_line(f"  {color(f'{online} adventurer{"s" if online != 1 else ""} online', GREEN)}")
        await self.send_line(f"  {color(f'Terminal: {self.term_width}x{self.term_height}', DIM)}")
        await self.send_line()
        await self.send_line(f"  {color('[N]', YELLOW)} New Character")
        await self.send_line(f"  {color('[L]', YELLOW)} Load Character")
        await self.send_line(f"  {color('[G]', DIM)} GM Login")
        await self.send_line(f"  {color('[Q]', YELLOW)} Quit")
        await self.send_line()

        while True:
            choice = (await self.get_char("Your choice: ")).upper()
            if choice in ('N', 'L', 'Q'):
                await self.send_line()
                return choice
            if choice == 'G':
                await self.send_line()
                pw = await self.get_input("GM Password: ")
                if pw == GM_PASSWORD:
                    self.is_gm = True
                    await self.send_line(color("GM access granted! Use [/] in-game for GM menu.", GREEN))
                else:
                    await self.send_line(color("Wrong password.", RED))
                await self.get_char("Press any key...")
                return 'G'  # re-show title

    async def create_character(self):
        await self.send(CLEAR)
        await self.send_line(color("=== CHARACTER CREATION ===", CYAN))
        await self.send_line()

        # Name
        name = ""
        while not name or len(name) > 16:
            name = await self.get_input("Enter thy name (max 16 chars): ")
            if not name:
                await self.send_line("A hero must have a name!")
            elif WORLD.is_banned(name):
                await self.send_line(color("That name is banned!", RED))
                name = ""

        await self.send_line()
        await self.send_line(color("Choose thy class:", YELLOW))
        await self.send_line()
        for i, (cls, stats) in enumerate(CLASSES.items(), 1):
            await self.send_line(f"  {color(f'[{i}]', YELLOW)} {color(cls, WHITE)} - {stats['desc']}")
            await self.send_line(f"      HP:{stats['hp']} MP:{stats['mp']} ATK:{stats['atk']} DEF:{stats['def']} SPD:{stats['spd']}")
        await self.send_line()

        cls_choice = 0
        class_names = list(CLASSES.keys())
        while cls_choice < 1 or cls_choice > 4:
            inp = await self.get_char("Class (1-4): ")
            try:
                cls_choice = int(inp)
            except ValueError:
                pass

        chosen_class = class_names[cls_choice - 1]
        stats = CLASSES[chosen_class]

        # Game mode
        await self.send_line()
        await self.send_line(color("Choose thy fate:", YELLOW))
        await self.send_line(f"  {color('[1]', YELLOW)} {color('NORMAL', GREEN)} - Respawn on death, keep your save")
        await self.send_line(f"  {color('[2]', YELLOW)} {color('HARDCORE', RED)} - Permadeath! Save erased on death. +50% XP & gold")
        await self.send_line()
        hardcore = False
        while True:
            mode = await self.get_char("Mode (1-2): ")
            if mode == '2':
                hardcore = True
                await self.send_line(color("\r\n  You have chosen the path of no return!", RED))
                break
            elif mode == '1':
                await self.send_line(color("\r\n  A wise choice. Death is but a setback.", GREEN))
                break

        # Roll bonus stats
        await self.send_line()
        await self.send_line(color("Rolling bonus stats...", DIM))
        bonus = random.randint(1, 6) + random.randint(1, 6) + random.randint(1, 6)
        await self.send_line(f"  Bonus points: {color(str(bonus), GREEN)}")

        self.char = {
            "name": name,
            "class": chosen_class,
            "level": 1,
            "xp": 0,
            "xp_next": 100,
            "hp": stats["hp"] + bonus,
            "max_hp": stats["hp"] + bonus,
            "mp": stats["mp"] + (bonus // 2 if stats["mp"] > 0 else 0),
            "max_mp": stats["mp"] + (bonus // 2 if stats["mp"] > 0 else 0),
            "base_atk": stats["atk"],
            "base_def": stats["def"],
            "spd": stats["spd"] + random.randint(0, 2),
            "gold": 50,
            "weapon": 0,   # index into WEAPONS
            "armor": 0,    # index into ARMOR
            "potions": 3,
            "floor": OVERWORLD_FLOOR,
            "x": get_overworld_spawn()[0],
            "y": get_overworld_spawn()[1],
            "facing": SOUTH,
            "explored": {},
            "treasures_found": [],
            "poisoned": False,
            "kills": 0,
            "hardcore": hardcore,
        }

        save_character(self.char)

        await self.send_line()
        await self.send_line(color(f"{name} the {chosen_class} enters the dungeon!", GREEN))
        await self.send_line(color("Press any key to begin...", DIM))
        await self.get_char()

    async def load_character_menu(self):
        saves = list_saves()
        if not saves:
            await self.send_line(color("No saved characters found!", RED))
            await self.send_line()
            return False

        await self.send(CLEAR)
        await self.send_line(color("=== LOAD CHARACTER ===", CYAN))
        await self.send_line()
        for i, name in enumerate(saves, 1):
            char = load_character(name)
            if char:
                mode_tag = color(" [HC]", RED) if char.get('hardcore', False) else ""
                await self.send_line(f"  {color(f'[{i}]', YELLOW)} {char['name']} - Lv.{char['level']} {char['class']} (Floor {char['floor']+1}){mode_tag}")
        await self.send_line()

        while True:
            inp = await self.get_char(f"Choose (1-{len(saves)}, 0=back): ")
            if inp == '0':
                return False
            try:
                idx = int(inp) - 1
                if 0 <= idx < len(saves):
                    self.char = load_character(saves[idx])
                    if self.char:
                        # Check if banned
                        if WORLD.is_banned(self.char['name']):
                            await self.send_line(color(f"\r\n{self.char['name']} is BANNED!", RED))
                            self.char = None
                            await self.get_char("Press any key...")
                            return False
                        # Check if already logged in
                        if self.char['name'] in WORLD.sessions:
                            await self.send_line(color(f"\r\n{self.char['name']} is already logged in!", RED))
                            self.char = None
                            await self.get_char("Press any key...")
                            return False
                        # Fix up dead characters from old saves
                    if self.char['hp'] <= 0:
                        self.char['hp'] = self.char['max_hp'] // 2
                        self.char['floor'] = OVERWORLD_FLOOR
                        self.char['x'] = get_overworld_spawn()[0]
                        self.char['y'] = get_overworld_spawn()[1]
                        self.char['poisoned'] = False
                        save_character(self.char)
                        await self.send_line(color(f"\r\n{self.char['name']} was found unconscious at the entrance...", YELLOW))
                    else:
                        await self.send_line(color(f"\r\nWelcome back, {self.char['name']}!", GREEN))
                    await self.get_char("Press any key...")
                    return True
            except ValueError:
                pass

        await self.send_line(color("Invalid choice.", RED))
        return False

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
        """Run a turn-based combat encounter. allies = list of other GameSessions on same tile."""
        monster = dict(monster_template)
        # Scale monster HP up for party fights
        if allies:
            monster['hp'] = int(monster['hp'] * (1 + 0.5 * len(allies)))
        monster['max_hp'] = monster['hp']
        self.combat_shield_bonus = 0

        await self.send(CLEAR)
        await self.send_line(color("=======================================", RED))
        await self.send_line(color(f"  A {monster['name']} appears!", RED))
        await self.send_line(color("=======================================", RED))
        await self.send_line()

        # Monster ASCII art (simple)
        arts = {
            "Giant Rat":    ["  (\\_/)", "  (o.o)", "  (> <)"],
            "Kobold":       ["  /\\_/\\", " ( o.o)", "  > ^ <"],
            "Skeleton":     ["   _||_", "  /o  o\\", "  |_/\\_|", "   /||\\"],
            "Giant Spider": [" /\\(oo)/\\", "//\\\\||//\\\\"],
            "Zombie":       ["  [x_x]", "  /|  |\\", "  / \\/ \\"],
            "Demon Lord":   [" _/\\_/\\_", "( O  O )", " \\    /", "  \\||/", "  /||\\ ", " / || \\"],
        }
        # Custom art from monster dict takes priority
        if 'art' in monster and monster['art']:
            art = monster['art']
        else:
            art = arts.get(monster['name'], ["  [?_?]", "  /| |\\"])
        for line in art:
            await self.send_line(color(f"        {line}", RED))
        await self.send_line()

        fled = False
        while monster['hp'] > 0 and self.char['hp'] > 0 and not fled:
            # Status
            hp_bar = self._bar(self.char['hp'], self.char['max_hp'], 15, GREEN)
            mp_bar = self._bar(self.char['mp'], self.char['max_mp'], 10, CYAN)
            m_bar = self._bar(monster['hp'], monster['max_hp'], 15, RED)

            await self.send_line(f"  {color(self.char['name'], WHITE)} HP:{hp_bar} MP:{mp_bar}")
            await self.send_line(f"  {color(monster['name'], RED)}  HP:{m_bar}")
            await self.send_line()

            # Player actions
            await self.send_line(f"  {color('[A]', YELLOW)}ttack  {color('[S]', YELLOW)}pell  {color('[P]', YELLOW)}otion  {color('[F]', YELLOW)}lee")
            action = (await self.get_char("  Action: ")).upper()

            player_dmg = 0
            player_acted = True

            if action == 'A':
                # Attack
                atk = self.get_atk()
                roll = random.randint(1, 20)
                if roll == 20:
                    player_dmg = atk * 2
                    self.log(color("CRITICAL HIT!", YELLOW))
                elif roll + self.char['spd'] > 8:
                    player_dmg = max(1, atk - monster['def'] // 2 + random.randint(-2, 2))
                else:
                    self.log("Your attack misses!")
                    player_dmg = 0

                if player_dmg > 0:
                    monster['hp'] -= player_dmg
                    self.log(f"You hit {monster['name']} for {color(str(player_dmg), GREEN)} damage!")

            elif action == 'S':
                spells = self.char.get('spells', [])
                if not spells:
                    self.log(color("You don't know any spells!", RED))
                    player_acted = False
                else:
                    await self.send_line()
                    for i, sp in enumerate(spells, 1):
                        info = SPELLS[sp]
                        await self.send_line(f"    {color(f'[{i}]', YELLOW)} {sp} - {info['desc']} (MP: {info['cost']})")
                    await self.send_line(f"    {color('[0]', YELLOW)} Cancel")
                    sp_choice = await self.get_char("    Spell: ")
                    try:
                        si = int(sp_choice)
                        if si == 0:
                            player_acted = False
                        elif 1 <= si <= len(spells):
                            spell_name = spells[si - 1]
                            spell = SPELLS[spell_name]
                            if self.char['mp'] >= spell['cost']:
                                self.char['mp'] -= spell['cost']
                                if spell_name == 'HEAL':
                                    heal = random.randint(15, 25)
                                    self.char['hp'] = min(self.char['max_hp'], self.char['hp'] + heal)
                                    self.log(color(f"You heal for {heal} HP!", GREEN))
                                elif spell_name == 'FIREBALL':
                                    dmg = random.randint(12, 20)
                                    monster['hp'] -= dmg
                                    self.log(color(f"Fireball hits for {dmg} damage!", YELLOW))
                                elif spell_name == 'SHIELD':
                                    self.combat_shield_bonus = 5
                                    self.log(color("A magical shield surrounds you! +5 DEF", CYAN))
                                elif spell_name == 'LIGHTNING':
                                    dmg = random.randint(20, 35)
                                    monster['hp'] -= dmg
                                    self.log(color(f"Lightning strikes for {dmg} damage!", YELLOW))
                                elif spell_name == 'CURE':
                                    self.char['poisoned'] = False
                                    self.log(color("Poison cured!", GREEN))
                            else:
                                self.log(color("Not enough MP!", RED))
                                player_acted = False
                        else:
                            player_acted = False
                    except ValueError:
                        player_acted = False

            elif action == 'P':
                if self.char['potions'] > 0:
                    self.char['potions'] -= 1
                    heal = random.randint(10, 20)
                    self.char['hp'] = min(self.char['max_hp'], self.char['hp'] + heal)
                    self.log(color(f"You drink a potion! +{heal} HP ({self.char['potions']} left)", GREEN))
                else:
                    self.log(color("No potions left!", RED))
                    player_acted = False

            elif action == 'F':
                flee_chance = 40 + self.char['spd'] * 3
                if self.char['class'] == 'THIEF':
                    flee_chance += 20
                if random.randint(1, 100) <= flee_chance:
                    self.log("You flee from combat!")
                    fled = True
                    continue
                else:
                    self.log(color("Can't escape!", RED))

            else:
                player_acted = False

            # Ally attacks (co-op)
            if monster['hp'] > 0 and player_acted and allies:
                for ally in allies:
                    if ally.char and ally.char['hp'] > 0:
                        a_atk = ally.char['base_atk'] + WEAPONS[ally.char['weapon']]['atk']
                        a_roll = random.randint(1, 20)
                        if a_roll == 20:
                            a_dmg = a_atk * 2
                            self.log(color(f"{ally.char['name']} CRITS!", YELLOW))
                        elif a_roll + ally.char['spd'] > 8:
                            a_dmg = max(1, a_atk - monster['def'] // 2 + random.randint(-2, 2))
                        else:
                            a_dmg = 0
                        if a_dmg > 0:
                            monster['hp'] -= a_dmg
                            self.log(f"{color(ally.char['name'], GREEN)} hits for {color(str(a_dmg), GREEN)}!")
                        if monster['hp'] <= 0:
                            break

            # Monster turn
            if monster['hp'] > 0 and player_acted:
                m_roll = random.randint(1, 20)
                if m_roll == 20:
                    m_dmg = monster['atk'] * 2
                    self.log(color(f"{monster['name']} lands a CRITICAL HIT!", RED))
                elif m_roll + 5 > 8:
                    m_dmg = max(1, monster['atk'] - self.get_def() // 2 + random.randint(-2, 2))
                else:
                    m_dmg = 0
                    self.log(f"{monster['name']}'s attack misses!")

                if m_dmg > 0:
                    self.char['hp'] -= m_dmg
                    self.log(f"{monster['name']} hits you for {color(str(m_dmg), RED)} damage!")

                # Chance of poison on certain monsters
                if monster['name'] in ('Giant Spider', 'Ghoul') and random.randint(1, 4) == 1:
                    self.char['poisoned'] = True
                    self.log(color("You've been poisoned!", MAGENTA))

            # Show combat log
            await self.send(CLEAR)
            await self.send_line(color("=== COMBAT ===", RED))
            await self.send_line()
            for art_line in art:
                await self.send_line(color(f"        {art_line}", RED))
            await self.send_line()
            for msg in self.message_log:
                await self.send_line(f"  {msg}")
            await self.send_line()

        self.combat_shield_bonus = 0

        if self.char['hp'] <= 0:
            return 'dead'
        elif fled:
            return 'fled'
        else:
            # Victory! Share XP/gold with allies
            xp_gain = monster['xp']
            gold_gain = monster['gold']
            if self.char.get('hardcore', False):
                xp_gain = int(xp_gain * 1.5)
                gold_gain = int(gold_gain * 1.5)
            self.char['xp'] += xp_gain
            self.char['gold'] += gold_gain
            self.char['kills'] += 1
            hc_tag = color(" [HC]", RED) if self.char.get('hardcore', False) else ""
            self.log(color(f"Victory! +{xp_gain} XP, +{gold_gain} gold", GREEN) + hc_tag)
            await self.check_level_up()
            # Allies also get XP and gold
            if allies:
                for ally in allies:
                    if ally.char and ally.char['hp'] > 0:
                        ally.char['xp'] += monster['xp']
                        ally.char['gold'] += monster['gold']
                        ally.char['kills'] += 1
                        ally.log(color(f"Party victory! +{monster['xp']} XP, +{monster['gold']} gold", GREEN))
                        save_character(ally.char)
            return 'victory'

    def _bar(self, cur, max_val, width, bar_color):
        if max_val == 0:
            return f"{color('N/A', DIM)}"
        filled = int((cur / max_val) * width) if max_val > 0 else 0
        filled = max(0, min(width, filled))
        bar = '#' * filled + '-' * (width - filled)
        return f"{bar_color}{bar}{RESET} {cur}/{max_val}"

    async def shop(self):
        """Visit the shop at the entrance."""
        while True:
            await self.send(CLEAR)
            await self.send_line(color("=== YE OLDE SHOPPE ===", YELLOW))
            await self.send_line()
            await self.send_line(f"  Gold: {color(str(self.char['gold']), YELLOW)}")
            await self.send_line(f"  Current Weapon: {WEAPONS[self.char['weapon']]['name']}")
            await self.send_line(f"  Current Armor:  {ARMOR[self.char['armor']]['name']}")
            await self.send_line()
            await self.send_line(f"  {color('[W]', YELLOW)}eapons  {color('[A]', YELLOW)}rmor  {color('[P]', YELLOW)}otions  {color('[L]', YELLOW)}eave")

            choice = (await self.get_char("  Choice: ")).upper()

            if choice == 'W':
                await self.send_line()
                await self.send_line(color("  WEAPONS:", WHITE))
                for i, w in enumerate(WEAPONS):
                    owned = " (equipped)" if i == self.char['weapon'] else ""
                    price = f"{w['price']}g" if w['price'] > 0 else "---"
                    await self.send_line(f"    [{i+1}] {w['name']:20s} ATK+{w['atk']:2d}  {price}{owned}")
                await self.send_line()
                inp = await self.get_char("    Buy (0=cancel): ")
                try:
                    idx = int(inp) - 1
                    if 0 <= idx < len(WEAPONS):
                        w = WEAPONS[idx]
                        if idx <= self.char['weapon']:
                            self.log("You already have equal or better!")
                        elif self.char['gold'] >= w['price']:
                            self.char['gold'] -= w['price']
                            self.char['weapon'] = idx
                            self.log(color(f"Bought {w['name']}!", GREEN))
                        else:
                            self.log(color("Not enough gold!", RED))
                except ValueError:
                    pass

            elif choice == 'A':
                await self.send_line()
                await self.send_line(color("  ARMOR:", WHITE))
                for i, a in enumerate(ARMOR):
                    owned = " (equipped)" if i == self.char['armor'] else ""
                    price = f"{a['price']}g" if a['price'] > 0 else "---"
                    await self.send_line(f"    [{i+1}] {a['name']:20s} DEF+{a['def']:2d}  {price}{owned}")
                await self.send_line()
                inp = await self.get_char("    Buy (0=cancel): ")
                try:
                    idx = int(inp) - 1
                    if 0 <= idx < len(ARMOR):
                        a = ARMOR[idx]
                        if idx <= self.char['armor']:
                            self.log("You already have equal or better!")
                        elif self.char['gold'] >= a['price']:
                            self.char['gold'] -= a['price']
                            self.char['armor'] = idx
                            self.log(color(f"Bought {a['name']}!", GREEN))
                        else:
                            self.log(color("Not enough gold!", RED))
                except ValueError:
                    pass

            elif choice == 'P':
                price = 25
                await self.send_line(f"\n  Potions: {price}g each. You have {self.char['potions']}.")
                inp = await self.get_input(f"  How many? ")
                try:
                    qty = int(inp)
                    cost = qty * price
                    if cost <= self.char['gold'] and qty > 0:
                        self.char['gold'] -= cost
                        self.char['potions'] += qty
                        self.log(color(f"Bought {qty} potions!", GREEN))
                    elif qty > 0:
                        self.log(color("Not enough gold!", RED))
                except ValueError:
                    pass

            elif choice == 'L':
                break

            # Show messages
            for msg in self.message_log:
                await self.send_line(f"  {msg}")
            self.message_log.clear()

    async def game_over(self):
        is_hardcore = self.char.get('hardcore', False)

        await self.send(CLEAR)
        await self.send_line()

        if is_hardcore:
            await self.send_line(color("  +-------------------------------+", RED))
            await self.send_line(color("  |     T H O U   H A S T        |", RED))
            await self.send_line(color("  |        P E R I S H E D        |", RED))
            await self.send_line(color("  |       [HARDCORE DEATH]        |", RED))
            await self.send_line(color("  +-------------------------------+", RED))
            await self.send_line()
            await self.send_line(f"  {self.char['name']} the {self.char['class']}")
            await self.send_line(f"  Level {self.char['level']} - {self.char['kills']} kills")
            await self.send_line(f"  Reached floor {self.char['floor'] + 1}")
            await self.send_line()

            # Delete save on death (permadeath!)
            delete_save(self.char['name'])
            await self.send_line(color("  Your save has been erased forever.", RED))
            await self.send_line(color("  This is the path you chose.", DIM))
            await self.send_line()
            await self.get_char(color("  Press any key...", DIM))
        else:
            await self.send_line(color("  +-------------------------------+", RED))
            await self.send_line(color("  |     Y O U   D I E D          |", RED))
            await self.send_line(color("  +-------------------------------+", RED))
            await self.send_line()
            await self.send_line(f"  {self.char['name']} the {self.char['class']}")
            await self.send_line(f"  Slain on floor {self.char['floor'] + 1}")
            await self.send_line()
            death_msgs = [
                "  The dungeon claims another soul... temporarily.",
                "  You see a light... it's the entrance. You're back.",
                "  A mysterious force drags you to safety.",
                "  The rats will feast tonight, but not on you.",
                "  Death is just a minor inconvenience around here.",
            ]
            await self.send_line(color(random.choice(death_msgs), YELLOW))
            await self.send_line()

            # Respawn at overworld town, half HP, lose some gold
            gold_lost = self.char['gold'] // 5
            self.char['gold'] -= gold_lost
            self.char['hp'] = self.char['max_hp'] // 2
            self.char['floor'] = OVERWORLD_FLOOR
            self.char['x'] = get_overworld_spawn()[0]
            self.char['y'] = get_overworld_spawn()[1]
            self.char['facing'] = SOUTH
            self.char['poisoned'] = False
            save_character(self.char)

            await self.send_line(color(f"  Lost {gold_lost} gold. Respawning at entrance...", DIM))
            await self.send_line()
            await self.get_char(color("  Press any key to try again...", DIM))

    async def pvp_death(self, killer_name):
        """Death by PvP - no permadeath, respawn at entrance with trash talk."""
        taunts = [
            f"  {killer_name} mopped the floor with you.",
            f"  {killer_name} sent you back to the shadow realm.",
            f"  {killer_name} didn't even break a sweat.",
            f"  Maybe try fighting a rat first next time.",
            f"  {killer_name} says: 'git gud'",
            f"  Your ancestors are embarrassed.",
            f"  {killer_name} is now wearing your dignity as a hat.",
            f"  Even the kobolds are laughing at you.",
            f"  {killer_name} killed you. Go eat their children.",
            f"  That was painful to watch. And you LIVED it.",
        ]

        await self.send(CLEAR)
        await self.send_line()
        await self.send_line(color("  +-------------------------------+", RED))
        await self.send_line(color("  |     S L A I N   I N   P V P   |", RED))
        await self.send_line(color("  +-------------------------------+", RED))
        await self.send_line()
        await self.send_line(color(f"  Killed by: {killer_name}", RED))
        await self.send_line()
        await self.send_line(color(random.choice(taunts), YELLOW))
        await self.send_line()
        await self.send_line(color("  You lost 25% of your gold.", DIM))
        await self.send_line()

        # Respawn at overworld town, half HP
        self.char['hp'] = self.char['max_hp'] // 2
        self.char['floor'] = OVERWORLD_FLOOR
        self.char['x'] = get_overworld_spawn()[0]
        self.char['y'] = get_overworld_spawn()[1]
        self.char['facing'] = SOUTH
        self.char['poisoned'] = False
        save_character(self.char)

        await self.send_line(color("  Respawning at dungeon entrance...", GREEN))
        await self.send_line()
        await self.get_char(color("  Press any key to get back in there...", DIM))

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
        """Show numbered list of online players, return chosen session or None."""
        players = list(WORLD.sessions.items())
        if not players:
            await self.send_line(color("  No players online.", DIM))
            await self.get_char("  Press any key...")
            return None
        for i, (name, s) in enumerate(players, 1):
            loc = f"F{s.char['floor']+1} ({s.char['x']},{s.char['y']})" if s.char else "?"
            gm_tag = color(" [GM]", MAGENTA) if s.is_gm else ""
            await self.send_line(f"  {color(f'[{i}]', YELLOW)} {name} Lv.{s.char['level'] if s.char else '?'} {loc}{gm_tag}")
        await self.send_line(f"  {color('[0]', YELLOW)} Cancel")
        pick = await self.get_char(f"  {prompt}")
        try:
            idx = int(pick) - 1
            if 0 <= idx < len(players):
                return players[idx][1]
        except ValueError:
            pass
        return None

    async def gm_menu(self):
        """Full GM/moderator menu."""
        while True:
            await self.send(CLEAR)
            await self.send_line(color("=== GAME MASTER MENU ===", MAGENTA))
            await self.send_line()
            await self.send_line(f"  {color('[1]', YELLOW)} Teleport to player")
            await self.send_line(f"  {color('[2]', YELLOW)} Teleport player to me")
            await self.send_line(f"  {color('[3]', YELLOW)} Edit player stats")
            await self.send_line(f"  {color('[4]', YELLOW)} Edit player inventory")
            await self.send_line(f"  {color('[5]', YELLOW)} Set player location")
            await self.send_line(f"  {color('[6]', YELLOW)} Kick player")
            await self.send_line(f"  {color('[7]', YELLOW)} Ban player")
            await self.send_line(f"  {color('[8]', YELLOW)} Unban player")
            await self.send_line(f"  {color('[9]', YELLOW)} Broadcast message")
            await self.send_line(f"  {color('[0]', YELLOW)} List all players")
            await self.send_line(f"  {color('[F]', YELLOW)} Teleport to floor")
            await self.send_line(f"  {color('[M]', YELLOW)} Monster editor")
            await self.send_line(f"  {color('[E]', YELLOW)} Map tile editor")
            await self.send_line(f"  {color('[V]', YELLOW)} Viewport theme editor")
            await self.send_line(f"  {color('[B]', YELLOW)} Back to game")
            await self.send_line()

            choice = (await self.get_char("  GM> ")).upper()

            if choice == 'B':
                break

            elif choice == '1':
                # Teleport TO a player
                await self.send_line()
                target = await self.gm_pick_player("Go to: ")
                if target and target.char:
                    self.char['floor'] = target.char['floor']
                    self.char['x'] = target.char['x']
                    self.char['y'] = target.char['y']
                    self.log(color(f"Teleported to {target.char['name']}!", MAGENTA))
                    save_character(self.char)
                    break

            elif choice == '2':
                # Teleport player TO me
                await self.send_line()
                target = await self.gm_pick_player("Summon: ")
                if target and target.char:
                    target.char['floor'] = self.char['floor']
                    target.char['x'] = self.char['x']
                    target.char['y'] = self.char['y']
                    target.log(color(f"You were summoned by {self.char['name']}!", MAGENTA))
                    target.notify_event.set()
                    save_character(target.char)
                    self.log(color(f"Summoned {target.char['name']}!", MAGENTA))

            elif choice == '3':
                # Edit player stats
                await self.send_line()
                target = await self.gm_pick_player("Edit stats: ")
                if target and target.char:
                    await self.send(CLEAR)
                    c = target.char
                    await self.send_line(color(f"=== EDIT {c['name']} ===", MAGENTA))
                    await self.send_line(f"  [1] HP:     {c['hp']}/{c['max_hp']}")
                    await self.send_line(f"  [2] MP:     {c['mp']}/{c['max_mp']}")
                    await self.send_line(f"  [3] ATK:    {c['base_atk']}")
                    await self.send_line(f"  [4] DEF:    {c['base_def']}")
                    await self.send_line(f"  [5] SPD:    {c['spd']}")
                    await self.send_line(f"  [6] Level:  {c['level']}")
                    await self.send_line(f"  [7] XP:     {c['xp']}")
                    await self.send_line(f"  [8] Poison: {c.get('poisoned', False)}")
                    await self.send_line(f"  [9] Full heal")
                    await self.send_line(f"  [0] Cancel")
                    stat = await self.get_char("  Stat: ")
                    if stat == '9':
                        c['hp'] = c['max_hp']
                        c['mp'] = c['max_mp']
                        c['poisoned'] = False
                        target.log(color("You feel fully restored!", GREEN))
                        target.notify_event.set()
                        self.log(color(f"Healed {c['name']}!", GREEN))
                        save_character(c)
                    elif stat == '8':
                        c['poisoned'] = not c.get('poisoned', False)
                        self.log(f"Poison toggled to {c['poisoned']}")
                        save_character(c)
                    elif stat in ('1','2','3','4','5','6','7'):
                        keys = {'1': ('hp', 'max_hp'), '2': ('mp', 'max_mp'),
                                '3': ('base_atk',), '4': ('base_def',), '5': ('spd',),
                                '6': ('level',), '7': ('xp',)}
                        fields = keys[stat]
                        for field in fields:
                            val = await self.get_input(f"  {field} = ")
                            try:
                                c[field] = int(val)
                            except ValueError:
                                pass
                        target.notify_event.set()
                        save_character(c)
                        self.log(color(f"Updated {c['name']}!", GREEN))

            elif choice == '4':
                # Edit inventory
                await self.send_line()
                target = await self.gm_pick_player("Edit inventory: ")
                if target and target.char:
                    await self.send(CLEAR)
                    c = target.char
                    await self.send_line(color(f"=== INVENTORY: {c['name']} ===", MAGENTA))
                    await self.send_line(f"  [1] Gold:    {c['gold']}")
                    await self.send_line(f"  [2] Potions: {c['potions']}")
                    await self.send_line(f"  [3] Weapon:  {WEAPONS[c['weapon']]['name']} ({c['weapon']})")
                    for i, w in enumerate(WEAPONS):
                        await self.send_line(f"       {i}: {w['name']}")
                    await self.send_line(f"  [4] Armor:   {ARMOR[c['armor']]['name']} ({c['armor']})")
                    for i, a in enumerate(ARMOR):
                        await self.send_line(f"       {i}: {a['name']}")
                    await self.send_line(f"  [0] Cancel")
                    item = await self.get_char("  Edit: ")
                    if item in ('1','2','3','4'):
                        field = {'1': 'gold', '2': 'potions', '3': 'weapon', '4': 'armor'}[item]
                        val = await self.get_input(f"  {field} = ")
                        try:
                            v = int(val)
                            if field == 'weapon' and 0 <= v < len(WEAPONS):
                                c['weapon'] = v
                            elif field == 'armor' and 0 <= v < len(ARMOR):
                                c['armor'] = v
                            elif field in ('gold', 'potions'):
                                c[field] = max(0, v)
                            target.notify_event.set()
                            save_character(c)
                            self.log(color(f"Updated {c['name']}'s {field}!", GREEN))
                        except ValueError:
                            pass

            elif choice == '5':
                # Set player location
                await self.send_line()
                target = await self.gm_pick_player("Move: ")
                if target and target.char:
                    await self.send_line(f"  Current: Floor {target.char['floor']+1} ({target.char['x']},{target.char['y']})")
                    fl = await self.get_input("  Floor (0+): ")
                    x = await self.get_input("  X: ")
                    y = await self.get_input("  Y: ")
                    try:
                        fl, x, y = int(fl), int(x), int(y)
                        target_floor = get_floor(fl)
                        fsize = len(target_floor)
                        if fl >= 0 and 0 <= x < fsize and 0 <= y < fsize:
                            if target_floor[y][x] != 1:
                                target.char['floor'] = fl
                                target.char['x'] = x
                                target.char['y'] = y
                                target.log(color(f"You were moved by {self.char['name']}!", MAGENTA))
                                target.notify_event.set()
                                save_character(target.char)
                                self.log(color(f"Moved {target.char['name']}!", GREEN))
                            else:
                                self.log(color("That's inside a wall!", RED))
                        else:
                            self.log(color("Out of bounds!", RED))
                    except ValueError:
                        pass

            elif choice == '6':
                # Kick
                await self.send_line()
                target = await self.gm_pick_player("Kick: ")
                if target and target.char:
                    name = target.char['name']
                    reason = await self.get_input("  Reason: ")
                    if not reason:
                        reason = "Kicked by GM"
                    await WORLD.kick_player(name, reason)
                    self.log(color(f"Kicked {name}!", RED))

            elif choice == '7':
                # Ban
                await self.send_line()
                await self.send_line(color("  Online players:", WHITE))
                target = await self.gm_pick_player("Ban: ")
                if target and target.char:
                    name = target.char['name']
                    WORLD.ban_player(name)
                    await WORLD.kick_player(name, "You have been BANNED")
                    self.log(color(f"Banned {name}!", RED))
                else:
                    # Can also ban offline players by name
                    await self.send_line()
                    name = await self.get_input("  Ban name (offline): ")
                    if name.strip():
                        WORLD.ban_player(name.strip())
                        self.log(color(f"Banned {name.strip()}!", RED))

            elif choice == '8':
                # Unban
                if not WORLD.banned:
                    await self.send_line(color("  No banned players.", DIM))
                    await self.get_char("  Press any key...")
                else:
                    await self.send_line()
                    for i, name in enumerate(WORLD.banned, 1):
                        await self.send_line(f"  [{i}] {name}")
                    await self.send_line(f"  [0] Cancel")
                    pick = await self.get_char("  Unban: ")
                    try:
                        idx = int(pick) - 1
                        if 0 <= idx < len(WORLD.banned):
                            name = WORLD.banned[idx]
                            WORLD.unban_player(name)
                            self.log(color(f"Unbanned {name}!", GREEN))
                    except ValueError:
                        pass

            elif choice == '9':
                # Broadcast
                await self.send_line()
                msg = await self.get_input("  Broadcast: ")
                if msg.strip():
                    WORLD.broadcast(f"[GM] {msg.strip()}", MAGENTA)

            elif choice == '0':
                # List all players
                await self.send(CLEAR)
                await self.send_line(color("=== ALL PLAYERS ===", MAGENTA))
                await self.send_line()
                await self.send_line(color("  ONLINE:", GREEN))
                for name, s in WORLD.sessions.items():
                    if s.char:
                        c = s.char
                        gm = color(" [GM]", MAGENTA) if s.is_gm else ""
                        await self.send_line(f"    {name} Lv.{c['level']} {c['class']} F{c['floor']+1} ({c['x']},{c['y']}) HP:{c['hp']}/{c['max_hp']} Gold:{c['gold']}{gm}")
                await self.send_line()
                await self.send_line(color("  SAVED (offline):", DIM))
                for sname in list_saves():
                    if sname not in [n.lower() for n in WORLD.sessions]:
                        sc = load_character(sname)
                        if sc:
                            banned = color(" [BANNED]", RED) if WORLD.is_banned(sc['name']) else ""
                            await self.send_line(f"    {sc['name']} Lv.{sc['level']} {sc['class']} F{sc['floor']+1}{banned}")
                if WORLD.banned:
                    await self.send_line()
                    await self.send_line(color(f"  BANNED: {', '.join(WORLD.banned)}", RED))
                await self.send_line()
                await self.get_char(color("  Press any key...", DIM))

            elif choice == 'F':
                # Teleport to floor
                await self.send_line()
                fl_input = await self.get_input(f"  Floor number (1-{MAX_FLOOR+1}): ")
                try:
                    fl = int(fl_input) - 1  # display is 1-based
                    if 0 <= fl <= MAX_FLOOR:
                        self.char['floor'] = fl
                        sx, sy = get_floor_spawn(fl)
                        self.char['x'] = sx
                        self.char['y'] = sy
                        fsize = len(get_floor(fl))
                        self.log(color(f"Teleported to floor {fl+1} ({fsize}x{fsize})!", MAGENTA))
                        save_character(self.char)
                        break  # back to game
                    else:
                        self.log(color("Invalid floor!", RED))
                except ValueError:
                    pass

            elif choice == 'M':
                await self.gm_monster_editor()

            elif choice == 'E':
                await self.gm_scene_editor()
                break  # back to game to see changes

            elif choice == 'V':
                await self.gm_viewport_theme_editor()
                break

    def _col_label(self, c):
        """Column label: 1-9 then a-z."""
        if c < 9:
            return str(c + 1)
        return chr(ord('a') + c - 9)

    def _parse_col(self, ch):
        """Parse column label back to 0-based index."""
        if ch.isdigit() and ch != '0':
            return int(ch) - 1
        if ch.isalpha():
            return ord(ch.lower()) - ord('a') + 9
        return -1

    async def _draw_art_grid(self, art):
        """Draw the art with row numbers and column ruler."""
        # Find max width
        max_w = max((len(line) for line in art), default=0)
        max_w = max(max_w, 20)  # minimum grid width

        # Column ruler
        ruler = "    "
        for c in range(max_w):
            ruler += self._col_label(c)
        await self.send_line(color(ruler, DIM))

        # Rows
        if art:
            for i, line in enumerate(art):
                padded = line.ljust(max_w)
                display = ""
                for ch in padded:
                    if ch == ' ':
                        display += color('.', f"{CSI}90m")
                    else:
                        display += color(ch, RED)
                await self.send_line(f"  {color(f'{i+1:2d}', YELLOW)}{display}")
        else:
            await self.send_line(color("  (empty)", DIM))

    async def edit_art_lines(self, current_art=None):
        """Interactive ASCII art editor with grid display. Returns new art list."""
        art = list(current_art) if current_art else []

        while True:
            await self.send_line()
            await self.send_line(color("  --- Art Editor ---", YELLOW))
            await self._draw_art_grid(art)
            await self.send_line()
            await self.send_line(f"  {color('A', YELLOW)}dd  {color('E', YELLOW)}dit#  {color('D', YELLOW)}el#  {color('I', YELLOW)}ns#  {color('P', YELLOW)}lot(r,c,ch)  {color('R', YELLOW)}eplace  {color('Q', YELLOW)}done")

            cmd = (await self.get_char("  > ")).lower()

            if cmd == 'q':
                break
            elif cmd == 'a':
                line = await self.get_input("  new line> ", preserve_spaces=True)
                if line:
                    art.append(line)
            elif cmd == 'e':
                num = await self.get_input("  line #: ")
                try:
                    idx = int(num) - 1
                    if 0 <= idx < len(art):
                        new_line = await self.get_input("  edit> ", preserve_spaces=True, prefill=art[idx])
                        if new_line or new_line == '':
                            art[idx] = new_line
                except ValueError:
                    pass
            elif cmd == 'd':
                num = await self.get_input("  del #: ")
                try:
                    idx = int(num) - 1
                    if 0 <= idx < len(art):
                        art.pop(idx)
                except ValueError:
                    pass
            elif cmd == 'i':
                num = await self.get_input("  insert before #: ")
                try:
                    idx = int(num) - 1
                    if 0 <= idx <= len(art):
                        line = await self.get_input("  new line> ", preserve_spaces=True)
                        if line:
                            art.insert(idx, line)
                except ValueError:
                    pass
            elif cmd == 'p':
                # Plot/insert character at row,col
                r_inp = await self.get_input("  row: ")
                c_inp = await self.get_input("  col: ")
                await self.send_line("  char: (type a key, or space for space)")
                ch = await self.get_char("  ")
                if ch == '\r':
                    ch = ' '  # enter = space
                await self.send_line()
                mode = await self.get_char("  [R]eplace or [I]nsert? ")
                try:
                    row = int(r_inp) - 1
                    col = self._parse_col(c_inp) if not c_inp.isdigit() else int(c_inp) - 1
                    while len(art) <= row:
                        art.append("")
                    if len(art[row]) <= col:
                        art[row] = art[row].ljust(col + 1)
                    if mode.lower() == 'i':
                        art[row] = art[row][:col] + ch + art[row][col:]
                    else:
                        art[row] = art[row][:col] + ch + art[row][col + 1:]
                except (ValueError, IndexError):
                    pass
            elif cmd == 'r':
                await self.send_line(color("  Enter all lines (blank to finish):", YELLOW))
                new_art = []
                while True:
                    line = await self.get_input("  art> ", preserve_spaces=True)
                    if not line:
                        break
                    new_art.append(line)
                if new_art:
                    art = new_art

        return art if art else None

    async def gm_monster_editor(self):
        """Create, edit, and manage custom monsters."""
        while True:
            customs = load_custom_monsters()
            await self.send(CLEAR)
            await self.send_line(color("=== MONSTER EDITOR ===", MAGENTA))
            await self.send_line()
            await self.send_line(f"  {color('[N]', YELLOW)} New monster")
            await self.send_line(f"  {color('[E]', YELLOW)} Edit built-in monsters")
            if customs:
                await self.send_line(f"  {color('[L]', YELLOW)} List/edit custom ({len(customs)})")
                await self.send_line(f"  {color('[D]', YELLOW)} Delete a custom monster")
            await self.send_line(f"  {color('[S]', YELLOW)} Spawn monster here")
            await self.send_line(f"  {color('[B]', YELLOW)} Back")
            await self.send_line()

            ch = (await self.get_char("  > ")).upper()

            if ch == 'B':
                break

            elif ch == 'E':
                # Edit built-in monsters
                await self.send(CLEAR)
                await self.send_line(color("=== BUILT-IN MONSTERS ===", MAGENTA))
                await self.send_line()

                # Gather all built-in monsters across floors
                all_builtins = []
                for fl, mlist in sorted(MONSTERS_BY_FLOOR.items()):
                    for m in mlist:
                        all_builtins.append((fl, m))

                default_arts = {
                    "Giant Rat":    ["  (\\_/)", "  (o.o)", "  (> <)"],
                    "Kobold":       ["  /\\_/\\", " ( o.o)", "  > ^ <"],
                    "Skeleton":     ["   _||_", "  /o  o\\", "  |_/\\_|", "   /||\\"],
                    "Giant Spider": [" /\\(oo)/\\", "//\\\\||//\\\\"],
                    "Zombie":       ["  [x_x]", "  /|  |\\", "  / \\/ \\"],
                    "Demon Lord":   [" _/\\_/\\_", "( O  O )", " \\    /", "  \\||/"],
                }
                for i, (fl, m) in enumerate(all_builtins):
                    await self.send_line(f"  {color(f'[{i+1:2d}]', YELLOW)} F{fl+1} {color(m['name'], WHITE):20s} HP={m['hp']:3d} ATK={m['atk']:2d} DEF={m['def']:2d} XP={m['xp']:3d} G={m['gold']}")
                    art = m.get('art') or default_arts.get(m['name'], ["  [?_?]"])
                    for aline in art:
                        await self.send_line(color(f"       {aline}", RED))
                await self.send_line(f"\n  {color('[0]', YELLOW)} Back")
                pick = await self.get_input("  Edit #: ")
                try:
                    idx = int(pick) - 1
                    if 0 <= idx < len(all_builtins):
                        fl, m = all_builtins[idx]
                        await self.send_line(color(f"\n  Editing {m['name']} (enter to keep current):", YELLOW))

                        new_name = await self.get_input(f"  Name [{m['name']}]: ")
                        if new_name.strip():
                            m['name'] = new_name.strip()
                        for field in ['hp', 'atk', 'def', 'xp', 'gold']:
                            val = await self.get_input(f"  {field.upper()} [{m[field]}]: ")
                            if val.strip():
                                m[field] = int(val)

                        # Show current art
                        arts = {
                            "Giant Rat":    ["  (\\_/)", "  (o.o)", "  (> <)"],
                            "Kobold":       ["  /\\_/\\", " ( o.o)", "  > ^ <"],
                            "Skeleton":     ["   _||_", "  /o  o\\", "  |_/\\_|", "   /||\\"],
                            "Giant Spider": [" /\\(oo)/\\", "//\\\\||//\\\\"],
                            "Zombie":       ["  [x_x]", "  /|  |\\", "  / \\/ \\"],
                            "Demon Lord":   [" _/\\_/\\_", "( O  O )", " \\    /", "  \\||/", "  /||\\ ", " / || \\"],
                        }
                        cur_art = m.get('art') or arts.get(m['name'], ["  [?_?]"])
                        await self.send_line(color("  Current art:", DIM))
                        for aline in cur_art:
                            await self.send_line(color(f"    {aline}", RED))

                        edit_art = await self.get_input("  Edit art? (y/n): ")
                        if edit_art.lower() == 'y':
                            m['art'] = await self.edit_art_lines(cur_art)

                        save_builtin_overrides(MONSTERS_BY_FLOOR)
                        self.log(color(f"Updated {m['name']}! (saved)", GREEN))
                except (ValueError, IndexError):
                    pass
                await self.get_char("  Press any key...")

            elif ch == 'N':
                await self.send(CLEAR)
                await self.send_line(color("=== CREATE MONSTER ===", MAGENTA))
                await self.send_line()
                name = await self.get_input("  Name: ")
                if not name.strip():
                    continue
                name = name.strip()
                await self.send_line()
                try:
                    hp = int(await self.get_input(f"  HP [{20}]: ") or "20")
                    atk = int(await self.get_input(f"  ATK [{5}]: ") or "5")
                    dfn = int(await self.get_input(f"  DEF [{2}]: ") or "2")
                    xp = int(await self.get_input(f"  XP reward [{15}]: ") or "15")
                    gold = int(await self.get_input(f"  Gold reward [{10}]: ") or "10")
                    fl_input = await self.get_input("  Floor (-1=all): ")
                    fl = int(fl_input) if fl_input.strip() else -1
                except ValueError:
                    self.log(color("Invalid numbers!", RED))
                    continue

                # ASCII art editor
                await self.send_line(color("\n  Now draw your monster:", YELLOW))
                art_lines = await self.edit_art_lines()

                monster = {
                    "name": name, "hp": hp, "atk": atk, "def": dfn,
                    "xp": xp, "gold": gold, "floor": fl,
                    "art": art_lines
                }
                customs.append(monster)
                save_custom_monsters(customs)

                # Preview
                await self.send_line()
                await self.send_line(color(f"  Created {name}!", GREEN))
                await self.send_line(f"  HP={hp} ATK={atk} DEF={dfn} XP={xp} Gold={gold} Floor={'ALL' if fl==-1 else fl+1}")
                if art_lines:
                    await self.send_line(color("  Art preview:", YELLOW))
                    for aline in art_lines:
                        await self.send_line(color(f"        {aline}", RED))
                await self.get_char("  Press any key...")

            elif ch == 'L' and customs:
                await self.send(CLEAR)
                await self.send_line(color("=== CUSTOM MONSTERS ===", MAGENTA))
                await self.send_line()
                for i, m in enumerate(customs):
                    fl_str = "ALL" if m.get('floor', -1) == -1 else f"F{m.get('floor', -1)+1}"
                    await self.send_line(f"  {color(f'[{i+1}]', YELLOW)} {color(m['name'], WHITE)} HP={m['hp']} ATK={m['atk']} DEF={m['def']} XP={m['xp']} G={m['gold']} ({fl_str})")
                    art = m.get('art', [])
                    if art:
                        for aline in art:
                            await self.send_line(color(f"       {aline}", RED))
                    else:
                        await self.send_line(color("       [no art]", DIM))
                await self.send_line()
                await self.send_line(f"  Pick a number to edit, or {color('[0]', YELLOW)} back")
                pick = await self.get_input("  > ")
                try:
                    idx = int(pick) - 1
                    if 0 <= idx < len(customs):
                        m = customs[idx]
                        await self.send_line(f"\n  Editing {m['name']} (enter to keep current):")
                        m['name'] = (await self.get_input(f"  Name [{m['name']}]: ")).strip() or m['name']
                        for field in ['hp', 'atk', 'def', 'xp', 'gold']:
                            val = await self.get_input(f"  {field.upper()} [{m[field]}]: ")
                            if val.strip():
                                m[field] = int(val)
                        fl_val = await self.get_input(f"  Floor [{m.get('floor', -1)}] (-1=all): ")
                        if fl_val.strip():
                            m['floor'] = int(fl_val)
                        # Edit art
                        edit_art = await self.get_input("  Edit art? (y/n): ")
                        if edit_art.lower() == 'y':
                            m['art'] = await self.edit_art_lines(m.get('art', []))
                        save_custom_monsters(customs)
                        self.log(color(f"Updated {m['name']}!", GREEN))
                except (ValueError, IndexError):
                    pass
                await self.get_char("  Press any key...")

            elif ch == 'D' and customs:
                await self.send_line()
                for i, m in enumerate(customs):
                    await self.send_line(f"  [{i+1}] {m['name']}")
                pick = await self.get_input("  Delete #: ")
                try:
                    idx = int(pick) - 1
                    if 0 <= idx < len(customs):
                        removed = customs.pop(idx)
                        save_custom_monsters(customs)
                        self.log(color(f"Deleted {removed['name']}!", RED))
                except (ValueError, IndexError):
                    pass

            elif ch == 'S':
                # Spawn any monster - built-in + custom
                await self.send_line()
                all_spawnable = get_monsters_for_floor(self.char['floor'])
                all_spawnable = all_spawnable + customs
                for i, m in enumerate(all_spawnable):
                    await self.send_line(f"  [{i+1}] {m['name']} HP={m['hp']} ATK={m['atk']}")
                pick = await self.get_input("  Spawn #: ")
                try:
                    idx = int(pick) - 1
                    if 0 <= idx < len(all_spawnable):
                        template = all_spawnable[idx]
                        mob = dict(template)
                        mob['max_hp'] = mob['hp']
                        mob['x'] = self.char['x']
                        mob['y'] = self.char['y']
                        mob['symbol'] = mob['name'][0].upper()
                        mob['alive'] = True
                        mob['respawn_timer'] = 0
                        floor_mobs = get_floor_monsters(self.char['floor'])
                        floor_mobs.append(mob)
                        self.log(color(f"Spawned {mob['name']} at [{mob['x']},{mob['y']}]!", GREEN))
                except (ValueError, IndexError):
                    pass

    async def gm_viewport_theme_editor(self):
        """Edit the 3D viewport colors and textures for floors."""
        floor = self.char['floor']
        themes = load_scene_themes()
        floor_key = str(floor)

        # Current theme elements
        elements = ['wall', 'brick', 'side', 'frame', 'edge', 'ceil', 'floor']
        bg_elements = ['sky_bg', 'ground_bg', 'wall_bg', 'water_bg']

        # Load current overrides or defaults
        if floor_key not in themes:
            themes[floor_key] = {}

        while True:
            await self.send(CLEAR)
            await self.send_line(color(f"=== VIEWPORT THEME - Floor {floor+1 if floor >= 0 else 'Overworld'} ===", MAGENTA))
            await self.send_line()

            # Show color preview for each element
            await self.send_line(color("  Foreground colors:", WHITE))
            color_list = list(COLOR_NAMES.keys())
            for i, elem in enumerate(elements):
                cur = themes[floor_key].get(elem, "default")
                code = COLOR_NAMES.get(cur, "37")
                preview = f"{CSI}{code}m{'###'}{RESET}"
                await self.send_line(f"  {color(f'[{i+1}]', YELLOW)} {elem:8s} = {preview} ({cur})")

            await self.send_line()
            await self.send_line(color("  Background colors:", WHITE))
            for i, elem in enumerate(bg_elements):
                cur = themes[floor_key].get(elem, "default")
                code = BG_COLOR_NAMES.get(cur, "")
                if code:
                    preview = f"{CSI}{code}m{'   '}{RESET}"
                else:
                    preview = f"{DIM}none{RESET}"
                ltr = chr(ord('a') + i)
                await self.send_line(f"  {color(f'[{ltr}]', YELLOW)} {elem:10s} = {preview} ({cur})")

            await self.send_line()

            # Color palette reference
            await self.send_line(color("  Available colors:", DIM))
            palette = "  "
            for name, code in COLOR_NAMES.items():
                palette += f" {CSI}{code}m{name[:4]}{RESET}"
            await self.send_line(palette)

            await self.send_line()
            await self.send_line(f"  {color('[P]', YELLOW)} Preview  {color('[S]', YELLOW)} Save  {color('[R]', YELLOW)} Reset  {color('[Q]', YELLOW)} Back")

            cmd = (await self.get_char("  > ")).lower()

            if cmd == 'q':
                break

            elif cmd in '1234567':
                idx = int(cmd) - 1
                elem = elements[idx]
                await self.send_line()
                await self.send_line(f"  Colors: {', '.join(COLOR_NAMES.keys())}")
                val = await self.get_input(f"  {elem} color: ")
                if val.strip() in COLOR_NAMES:
                    themes[floor_key][elem] = val.strip()

            elif cmd in 'abcd':
                idx = ord(cmd) - ord('a')
                elem = bg_elements[idx]
                await self.send_line()
                await self.send_line(f"  BG Colors: {', '.join(BG_COLOR_NAMES.keys())}")
                val = await self.get_input(f"  {elem} bg color: ")
                if val.strip() in BG_COLOR_NAMES:
                    themes[floor_key][elem] = val.strip()

            elif cmd == 'p':
                # Preview - show a sample viewport render
                await self.send_line()
                # Apply current theme temporarily and render
                await self.send_line(color("  (Return to game to see full preview)", DIM))
                await self.get_char("  Press any key...")

            elif cmd == 's':
                save_scene_themes(themes)
                self.log(color("Theme saved!", GREEN))
                await self.send_line(color("\n  Theme saved to scene_themes.json!", GREEN))
                await self.get_char("  Press any key...")

            elif cmd == 'r':
                if floor_key in themes:
                    del themes[floor_key]
                save_scene_themes(themes)
                self.log(color("Theme reset to default!", YELLOW))

    def _tile_render(self, t, is_ow_floor):
        """Render a single tile as colored character with background."""
        BG_B = f"{CSI}44m"
        BG_G = f"{CSI}42m"
        BG_DK = f"{CSI}100m"
        BG_Y = f"{CSI}43m"
        BG_C = f"{CSI}46m"
        BG_R = f"{CSI}41m"
        if is_ow_floor:
            mapping = {
                OW_GRASS:    f"{CSI}92;42m.{RESET}",
                OW_FOREST:   f"{CSI}97;42mT{RESET}",
                OW_MOUNTAIN: f"{CSI}97;100m^{RESET}",
                OW_WATER:    f"{CSI}97;44m~{RESET}",
                OW_ROAD:     f"{CSI}93;43m={RESET}",
                OW_TOWN:     f"{CSI}93;45m@{RESET}",
                OW_DUNGEON:  f"{CSI}97;41mD{RESET}",
            }
            return mapping.get(t, f"{CSI}90m?{RESET}")
        else:
            mapping = {
                0: f"{CSI}37m.{RESET}",
                1: f"{CSI}97;100m#{RESET}",
                2: f"{CSI}96;40m+{RESET}",
                3: f"{CSI}91;40m>{RESET}",
                4: f"{CSI}92;40m<{RESET}",
                5: f"{CSI}93;43m${RESET}",
                6: f"{CSI}96;44m~{RESET}",
            }
            return mapping.get(t, f"{CSI}90m?{RESET}")

    async def gm_scene_editor(self):
        """Full-screen visual tile editor with cursor."""
        floor = self.char['floor']
        dungeon = get_floor(floor)
        size = len(dungeon)
        cx, cy = self.char['x'], self.char['y']
        is_ow_floor = is_overworld(floor)

        tile_names = {
            0: "Floor", 1: "Wall", 2: "Door", 3: "StairsD",
            4: "StairsU", 5: "Treas", 6: "Fount",
        }
        if is_ow_floor:
            tile_names = {
                OW_GRASS: "Grass", OW_FOREST: "Forest", OW_MOUNTAIN: "Mount",
                OW_WATER: "Water", OW_ROAD: "Road", OW_TOWN: "Town",
                OW_DUNGEON: "Dung.E",
            }

        if is_ow_floor:
            brushes = [OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON]
        else:
            brushes = [0, 1, 2, 3, 4, 5, 6]

        brush_idx = 0
        painting = False
        needs_full_redraw = True

        tw, th = self.term_width, self.term_height
        # Map viewport: fills most of the screen
        map_rows = th - 4  # reserve: header(1) + status(1) + brushes(1) + help(1)
        map_cols = tw - 2

        # Camera offset (top-left corner of viewport in map coords)
        cam_x = max(0, cx - map_cols // 2)
        cam_y = max(0, cy - map_rows // 2)

        def clamp_camera():
            nonlocal cam_x, cam_y
            cam_x = max(0, min(size - map_cols, cam_x))
            cam_y = max(0, min(size - map_rows, cam_y))

        clamp_camera()

        while True:
            brush = brushes[brush_idx]

            if needs_full_redraw:
                await self.send(CLEAR)

                # Row 1: Header
                await self.move_to(1, 1)
                paint_str = color("PAINT ON", GREEN) if painting else color("paint off", DIM)
                cur_tile = dungeon[cy][cx] if 0 <= cy < size and 0 <= cx < size else -1
                await self.send(color(f" SCENE EDITOR", MAGENTA) +
                    f"  [{cx},{cy}] {tile_names.get(cur_tile, '?')}  " +
                    f"Brush: {self._tile_render(brush, is_ow_floor)} {tile_names.get(brush, '?')}  " +
                    paint_str +
                    f"  Floor {floor+1 if floor >= 0 else 'OW'} ({size}x{size})")

                # Draw full map viewport
                for vr in range(map_rows):
                    my = cam_y + vr
                    row_str = ""
                    for vc in range(map_cols):
                        mx = cam_x + vc
                        if mx == cx and my == cy:
                            row_str += f"{CSI}30;107m@{RESET}"  # cursor: black on white
                        elif 0 <= mx < size and 0 <= my < size:
                            row_str += self._tile_render(dungeon[my][mx], is_ow_floor)
                        else:
                            row_str += f"{CSI}90m {RESET}"
                    await self.move_to(2 + vr, 1)
                    await self.send(row_str)

                # Brush palette row
                await self.move_to(th - 1, 1)
                palette = " "
                for i, b in enumerate(brushes):
                    sel = f"{CSI}7m" if i == brush_idx else ""
                    palette += f" {sel}{i+1}:{self._tile_render(b, is_ow_floor)}{tile_names.get(b, '?')[:5]}{RESET}"
                await self.send(palette)

                # Help row
                await self.move_to(th, 1)
                await self.send(f" {color('WASD', YELLOW)}move {color('P', YELLOW)}aint {color('1-7', YELLOW)}brush {color('F', YELLOW)}ill {color('G', YELLOW)}rid size {color('X', YELLOW)}save {color('Q', YELLOW)}uit")

                needs_full_redraw = False
            else:
                # Incremental: just update header, old cursor pos, new cursor pos
                # Header
                await self.move_to(1, 1)
                await self.send("\033[2K")
                cur_tile = dungeon[cy][cx] if 0 <= cy < size and 0 <= cx < size else -1
                paint_str = color("PAINT ON", GREEN) if painting else color("paint off", DIM)
                await self.send(color(f" SCENE EDITOR", MAGENTA) +
                    f"  [{cx},{cy}] {tile_names.get(cur_tile, '?')}  " +
                    f"Brush: {self._tile_render(brush, is_ow_floor)} {tile_names.get(brush, '?')}  " +
                    paint_str)

            cmd = (await self.get_char("")).lower()

            old_cx, old_cy = cx, cy

            if cmd == 'q':
                break

            elif cmd in ('w', 'a', 's', 'd'):
                dx = {'a': -1, 'd': 1}.get(cmd, 0)
                dy = {'w': -1, 's': 1}.get(cmd, 0)
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < size and 0 <= ny < size:
                    cx, cy = nx, ny
                    if painting:
                        dungeon[cy][cx] = brush

                # Scroll camera if cursor near edge
                margin = 3
                if cx - cam_x < margin:
                    cam_x = max(0, cx - margin)
                    needs_full_redraw = True
                elif cx - cam_x >= map_cols - margin:
                    cam_x = min(size - map_cols, cx - map_cols + margin + 1)
                    needs_full_redraw = True
                if cy - cam_y < margin:
                    cam_y = max(0, cy - margin)
                    needs_full_redraw = True
                elif cy - cam_y >= map_rows - margin:
                    cam_y = min(size - map_rows, cy - map_rows + margin + 1)
                    needs_full_redraw = True

                if not needs_full_redraw:
                    # Just update old and new cursor cells
                    # Redraw old position
                    scr_ox = old_cx - cam_x + 1
                    scr_oy = old_cy - cam_y + 2
                    if 1 <= scr_ox <= map_cols and 2 <= scr_oy <= map_rows + 1:
                        await self.move_to(scr_oy, scr_ox)
                        await self.send(self._tile_render(dungeon[old_cy][old_cx], is_ow_floor))
                    # Draw new cursor
                    scr_nx = cx - cam_x + 1
                    scr_ny = cy - cam_y + 2
                    if 1 <= scr_nx <= map_cols and 2 <= scr_ny <= map_rows + 1:
                        await self.move_to(scr_ny, scr_nx)
                        await self.send(f"{CSI}30;107m@{RESET}")

            elif cmd == 'p':
                painting = not painting
                if painting:
                    dungeon[cy][cx] = brush
                    needs_full_redraw = True

            elif cmd in '1234567':
                brush_idx = int(cmd) - 1
                if brush_idx >= len(brushes):
                    brush_idx = len(brushes) - 1
                needs_full_redraw = True  # update palette highlight

            elif cmd == 'f':
                # Flood fill from cursor position
                target_tile = dungeon[cy][cx]
                if target_tile != brush:
                    stack = [(cx, cy)]
                    visited = set()
                    count = 0
                    while stack and count < 5000:
                        fx, fy = stack.pop()
                        if (fx, fy) in visited:
                            continue
                        if not (0 <= fx < size and 0 <= fy < size):
                            continue
                        if dungeon[fy][fx] != target_tile:
                            continue
                        visited.add((fx, fy))
                        dungeon[fy][fx] = brush
                        count += 1
                        stack.extend([(fx+1,fy),(fx-1,fy),(fx,fy+1),(fx,fy-1)])
                needs_full_redraw = True

            elif cmd == 'g':
                # Resize grid
                await self.move_to(1, 1)
                await self.send("\033[2K")
                new_size_str = await self.get_input(f" New size (current {size}, max 256): ")
                try:
                    new_size = int(new_size_str)
                    new_size = max(8, min(256, new_size))
                    if new_size != size:
                        # Create new grid, copy old data
                        fill = brushes[0]  # fill new space with first brush tile
                        new_grid = [[fill for _ in range(new_size)] for _ in range(new_size)]
                        # Border with walls/water
                        border_tile = 1 if not is_ow_floor else OW_WATER
                        for i in range(new_size):
                            new_grid[0][i] = border_tile
                            new_grid[new_size-1][i] = border_tile
                            new_grid[i][0] = border_tile
                            new_grid[i][new_size-1] = border_tile
                        # Copy existing data
                        for y in range(min(size, new_size)):
                            for x in range(min(size, new_size)):
                                new_grid[y][x] = dungeon[y][x]
                        dungeon = new_grid
                        size = new_size
                        # Clamp cursor
                        cx = min(cx, size - 2)
                        cy = min(cy, size - 2)
                        cam_x = max(0, cx - map_cols // 2)
                        cam_y = max(0, cy - map_rows // 2)
                except ValueError:
                    pass
                needs_full_redraw = True

            elif cmd == 'x':
                if is_ow_floor:
                    global _overworld
                    _overworld = dungeon
                    save_custom_floor(-1, dungeon)
                else:
                    _generated_floors[floor] = dungeon
                    save_custom_floor(floor, dungeon)
                # Flash save confirmation
                await self.move_to(1, tw - 10)
                await self.send(color(" SAVED! ", f"{CSI}30;102m"))
                await asyncio.sleep(0.5)
                needs_full_redraw = True

        self.char['x'] = cx
        self.char['y'] = cy
        save_character(self.char)

    async def pvp_combat(self, target):
        """PvP duel - attacker controls their actions, defender auto-fights.
        Can't take over another player's input stream, so defender is AI-controlled."""
        my_name = self.char['name']
        t_name = target.char['name']

        WORLD.broadcast(f"{my_name} attacks {t_name}!", RED)
        target.log(color(f"{my_name} is attacking you!", RED))
        target.notify_event.set()

        self.combat_shield_bonus = 0
        fled = False

        while self.char['hp'] > 0 and target.char['hp'] > 0 and not fled:
            await self.send(CLEAR)
            await self.send_line(color("=== PVP DUEL ===", RED))
            await self.send_line()
            my_hp = self._bar(self.char['hp'], self.char['max_hp'], 12, GREEN)
            t_hp = self._bar(target.char['hp'], target.char['max_hp'], 12, RED)
            await self.send_line(f"  {color(my_name, GREEN)} HP:{my_hp}")
            await self.send_line(f"  {color(t_name, RED)}  HP:{t_hp}")
            await self.send_line()

            # Show combat log
            for msg in self.message_log[-4:]:
                await self.send_line(f"  {msg}")
            self.message_log.clear()
            await self.send_line()

            await self.send_line(f"  {color('[A]', YELLOW)}ttack  {color('[P]', YELLOW)}otion  {color('[F]', YELLOW)}lee")
            action = (await self.get_char("  Action: ")).upper()

            player_acted = True

            if action == 'F':
                flee_chance = 30 + self.char['spd'] * 3
                if random.randint(1, 100) <= flee_chance:
                    self.log("You fled the duel!")
                    target.log(f"{my_name} fled from the duel!")
                    target.notify_event.set()
                    WORLD.broadcast(f"{my_name} fled from {t_name}!", YELLOW)
                    fled = True
                    continue
                else:
                    self.log(color("Can't escape!", RED))

            elif action == 'P':
                if self.char['potions'] > 0:
                    self.char['potions'] -= 1
                    heal = random.randint(10, 20)
                    self.char['hp'] = min(self.char['max_hp'], self.char['hp'] + heal)
                    self.log(color(f"Drank a potion! +{heal} HP", GREEN))
                else:
                    self.log(color("No potions!", RED))
                    player_acted = False

            elif action == 'A':
                my_atk = self.get_atk()
                t_def = target.char['base_def'] + ARMOR[target.char['armor']]['def']
                roll = random.randint(1, 20)
                if roll == 20:
                    dmg = my_atk * 2
                    self.log(color("CRITICAL HIT!", YELLOW))
                elif roll + self.char['spd'] > 8:
                    dmg = max(1, my_atk - t_def // 2 + random.randint(-2, 2))
                else:
                    dmg = 0
                    self.log("Your attack misses!")
                if dmg > 0:
                    target.char['hp'] -= dmg
                    self.log(f"You hit {t_name} for {color(str(dmg), GREEN)} damage!")
                    target.log(f"{my_name} hits you for {color(str(dmg), RED)} damage!")
                    target.notify_event.set()
            else:
                player_acted = False

            # Defender auto-attacks back
            if target.char['hp'] > 0 and player_acted:
                t_atk = target.char['base_atk'] + WEAPONS[target.char['weapon']]['atk']
                my_def = self.get_def()
                roll = random.randint(1, 20)
                if roll == 20:
                    dmg = t_atk * 2
                    self.log(color(f"{t_name} lands a CRITICAL HIT!", RED))
                elif roll + target.char['spd'] > 8:
                    dmg = max(1, t_atk - my_def // 2 + random.randint(-2, 2))
                else:
                    dmg = 0
                    self.log(f"{t_name}'s counter-attack misses!")
                if dmg > 0:
                    self.char['hp'] -= dmg
                    self.log(f"{t_name} hits you for {color(str(dmg), RED)} damage!")
                    target.log(f"You counter-attack {my_name} for {color(str(dmg), GREEN)} damage!")
                    target.notify_event.set()

        if fled:
            return

        # Determine winner/loser
        if self.char['hp'] <= 0:
            winner, loser = target, self
        else:
            winner, loser = self, target

        # Winner gets some of loser's gold
        spoils = loser.char['gold'] // 4
        winner.char['gold'] += spoils
        loser.char['gold'] -= spoils
        winner.char['kills'] += 1

        winner.log(color(f"Defeated {loser.char['name']}! +{spoils} gold!", GREEN))
        loser.log(color(f"Defeated by {winner.char['name']}! Lost {spoils} gold!", RED))
        winner.notify_event.set()
        loser.notify_event.set()
        WORLD.broadcast(f"{winner.char['name']} defeated {loser.char['name']} in PvP!", RED)

        save_character(winner.char)
        save_character(loser.char)

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


if __name__ == '__main__':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shut down.")
