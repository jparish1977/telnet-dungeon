"""Game session logic - main loop, screen rendering, character screen."""

import asyncio
import math
import random

from dungeon.config import (
    CLEAR, DIM, RED, GREEN, YELLOW, CYAN, WHITE, MAGENTA,
    color, OW_DUNGEON, OW_TOWN, OW_FOREST, OW_MOUNTAIN, OW_WATER,
    OVERWORLD_FLOOR,
)
from dungeon.items import WEAPONS, ARMOR, SPELLS, DIR_NAMES, DIR_DX, DIR_DY
from dungeon.persistence import save_character
from dungeon.floor import (
    get_floor, get_floor_spawn, get_overworld_spawn,
    is_tile_blocked, is_overworld, MAX_FLOOR,
)
from dungeon.monsters import (
    get_floor_monsters, get_monster_at, kill_monster, move_floor_monsters,
)
from dungeon.character import validate_position
from dungeon.renderer_3d import render_3d_view
from dungeon.renderer_minimap import render_minimap
from dungeon.combat import _bar


async def draw_game_screen(session, world):
    """Render the game screen using differential updates (only send changed cells)."""
    floor = session.char['floor']
    dungeon = get_floor(floor)
    px, py = session.char['x'], session.char['y']
    facing = session.char['facing']
    tw, th = session.term_width, session.term_height

    # Row 1: Header
    online = world.player_count()
    fsize = len(dungeon)
    if is_overworld(floor):
        header = f" The Overworld ({fsize}x{fsize}) [{px},{py}]"
    else:
        header = f" Dungeon of Doom - Floor {floor + 1} ({fsize}x{fsize}) [{px},{py}]"
    right_info = f"{online} online  {tw}x{th}"
    pad = tw - len(header) - len(right_info) - 2
    await session.send_at(1, 1, color(header, CYAN) + ' ' * max(1, pad) + color(right_info, DIM))

    # Row 2: Character info + nearby players
    others_here = world.get_players_at(floor, px, py, session.char['name'])
    info = f" {session.char['name']} Lv.{session.char['level']} {session.char['class']}  Facing: {DIR_NAMES[facing]}"
    if others_here:
        names = ', '.join(s.char['name'] for s in others_here)
        info += color(f"  Party: {names}", GREEN)
    await session.send_at(2, 1, info)

    # 3D viewport fills rows 3 through (th - 7)
    vw, vh = session.get_view_size()
    # Build visible mob list for 3D renderer
    vis_mobs = [(m['x'], m['y'], m['symbol'], m['name'])
                 for m in get_floor_monsters(floor) if m['alive']]
    view_3d = render_3d_view(dungeon, px, py, facing, vw, vh, floor, vis_mobs)
    map_radius = session.get_map_radius()
    other_players = world.get_players_on_floor(floor, session.char['name'])
    minimap = render_minimap(dungeon, px, py, facing, map_radius, other_players, floor)

    view_lines = view_3d.split('\n')
    view_start_row = 3

    # The column where the minimap starts (right side of 3D view)
    map_col = vw + 6

    for i, vline in enumerate(view_lines):
        row = view_start_row + i
        if row >= th - 6:
            break
        await session.send_at(row, 2, vline)

    # Draw minimap beside the 3D view, vertically centered
    map_start = view_start_row + max(0, (len(view_lines) - len(minimap)) // 2)
    for i, mline in enumerate(minimap):
        row = map_start + i
        if row >= th - 6:
            break
        await session.send_at(row, map_col, mline)

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
            # Place indicator on minimap border
            indicator = pname[0].upper()
            dist = int(math.sqrt(dx*dx + dy*dy))
            label = f"{indicator}{dist}"

            if abs(dx) >= abs(dy):
                # Left or right edge
                if dx > 0:
                    # Right side
                    edge_row = mid_row + int(map_h/2 * dy / max(1, abs(dx)))
                    edge_row = max(map_start, min(map_start + map_h - 1, edge_row))
                    await session.send_at(edge_row, map_col + map_w + 1, color(label + ">", GREEN))
                else:
                    # Left side
                    edge_row = mid_row + int(map_h/2 * dy / max(1, abs(dx)))
                    edge_row = max(map_start, min(map_start + map_h - 1, edge_row))
                    await session.send_at(edge_row, map_col - len(label) - 1, color("<" + label, GREEN))
            else:
                # Top or bottom edge
                if dy > 0:
                    # Bottom
                    edge_col = mid_col + int(map_w/2 * dx / max(1, abs(dy)))
                    edge_col = max(map_col, min(map_col + map_w - 1, edge_col))
                    await session.send_at(map_start + map_h, edge_col, color(label + "v", GREEN))
                else:
                    # Top
                    edge_col = mid_col + int(map_w/2 * dx / max(1, abs(dy)))
                    edge_col = max(map_col, min(map_col + map_w - 1, edge_col))
                    await session.send_at(map_start - 1, edge_col, color(label + "^", GREEN))

    # Layout from viewport bottom down:
    # [viewport ends] -> [log area] -> [status 2 rows] -> [controls] -> [prompt]
    viewport_bottom = view_start_row + len(view_lines) + 1
    log_rows = session.get_log_rows()
    log_start = viewport_bottom

    # Draw log separator
    log_label = " -- Log "
    await session.send_at(log_start, 1, color(log_label + '-' * max(0, tw - len(log_label) - 1), DIM))

    # Combine local messages with global log, newest at bottom
    log_display_rows = max(1, log_rows - 1)
    combined = []
    combined.extend(world.global_log)
    combined.extend(session.message_log)
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
        if i < len(display_msgs):
            await session.send_at(row, 1, f" {display_msgs[i]}")
        else:
            await session.send_at(row, 1, color(" ~", DIM))
    session.message_log.clear()

    # Status rows
    status_row = th - 3
    hp_w = max(8, min(15, (tw - 40) // 3))
    mp_w = max(5, min(10, (tw - 40) // 4))
    hp_bar = _bar(session.char['hp'], session.char['max_hp'], hp_w, GREEN)
    mp_bar = _bar(session.char['mp'], session.char['max_mp'], mp_w, CYAN)

    status = f" HP:{hp_bar}  MP:{mp_bar}  Gold:{color(str(session.char['gold']), YELLOW)}  Pot:{session.char['potions']}"
    if session.char.get('poisoned'):
        status += color(" [POISON]", MAGENTA)
    hc_tag = color(" [HC]", RED) if session.char.get('hardcore', False) else ""
    await session.send_at(status_row, 1, status + hc_tag)

    await session.send_at(status_row + 1, 1, f" ATK:{session.get_atk()} DEF:{session.get_def()} SPD:{session.char['spd']} XP:{session.char['xp']}/{session.char['xp_next']}  {WEAPONS[session.char['weapon']]['name']} / {ARMOR[session.char['armor']]['name']}")

    # Controls at very bottom
    ctrl_row = th - 1
    controls = f" {color('W', YELLOW)}Fwd {color('A', YELLOW)}Left {color('D', YELLOW)}Right {color('S', YELLOW)}Back {color('C', YELLOW)}har {color('T', YELLOW)}alk"
    if others_here:
        controls += f" {color('P', RED)}vP"
    controls += f" {color('Q', YELLOW)}uit"
    if session.is_gm:
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

    await session.send_at(ctrl_row, 1, controls)

    # Prompt on last row
    await session.send_at(th, 1, " > ")



async def run_main_loop(session, world):
    """Main exploration loop."""
    # Validate position on entry (catches old saves, wall spawns, etc)
    if validate_position(session.char):
        session.log(color("You were relocated to a safe position.", YELLOW))
    # Force full draw on first frame
    session.invalidate_frame()
    await session.send(CLEAR)

    while session.running and session.char['hp'] > 0:
        floor = session.char['floor']
        dungeon = get_floor(floor)
        px, py = session.char['x'], session.char['y']
        facing = session.char['facing']

        # Mark explored
        key = f"{floor}_{px}_{py}"
        if 'explored' not in session.char:
            session.char['explored'] = {}
        session.char['explored'][key] = True

        await session.draw_game_screen()

        current_tile = dungeon[py][px]
        cmd = (await session.get_char("", redraw_on_resize=True)).lower()

        # On resize, force full redraw
        if cmd == 'resize':
            session.invalidate_frame()
            await session.send(CLEAR)
            continue

        # Handle incoming PvP challenge response
        if cmd == 'y' and hasattr(session, '_pvp_challenge_from'):
            challenger = session._pvp_challenge_from
            session._pvp_response = True
            session.log(color("Challenge accepted! Prepare to fight!", GREEN))
            challenger.log(color(f"{session.char['name']} accepted your challenge!", GREEN))
            challenger.notify_event.set()
            continue
        elif cmd == 'n' and hasattr(session, '_pvp_challenge_from'):
            challenger = session._pvp_challenge_from
            session._pvp_response = False
            del session._pvp_challenge_from
            session.log(color("Challenge declined.", DIM))
            challenger.log(color(f"{session.char['name']} declined your challenge.", DIM))
            challenger.notify_event.set()
            continue

        if cmd == 'q':
            save_character(session.char)
            await session.send_line(color("\r\n Character saved. Farewell!", GREEN))
            await session.get_char()
            break

        elif cmd == 't':
            # Chat - switch to line input for the message
            await session.move_to(session.term_height, 1)
            await session.send("\033[2K")  # clear the line
            msg = await session.get_input(" Say: ")
            if msg.strip():
                world.chat(session.char['name'], msg.strip())
            continue

        elif cmd == '/' and session.is_gm:
            await session.gm_menu()
            continue

        elif cmd == 'p':
            # PvP - challenge another player on same tile
            others_here = world.get_players_at(floor, px, py, session.char['name'])
            if not others_here:
                session.log("No one here to fight!")
            else:
                # Pick target
                target = None
                if len(others_here) == 1:
                    target = others_here[0]
                else:
                    await session.move_to(session.term_height, 1)
                    await session.send("\033[2K")
                    for i, s in enumerate(others_here, 1):
                        await session.send(f" [{i}]{s.char['name']} ")
                    pick = await session.get_char(" Challenge who? ")
                    try:
                        idx = int(pick) - 1
                        if 0 <= idx < len(others_here):
                            target = others_here[idx]
                    except ValueError:
                        pass

                if target:
                    # Send challenge to target
                    my_name = session.char['name']
                    t_name = target.char['name']

                    # Set pending challenge on target
                    target._pvp_challenge_from = session
                    target.log(color(f"{my_name} challenges you to a duel! Press [Y] to accept or [N] to decline.", YELLOW))
                    target.notify_event.set()

                    session.log(color(f"Challenge sent to {t_name}. Waiting...", YELLOW))

                    # Wait for response (poll for up to 15 seconds)
                    accepted = False
                    for _ in range(30):
                        await asyncio.sleep(0.5)
                        if hasattr(target, '_pvp_response'):
                            accepted = target._pvp_response
                            del target._pvp_response
                            del target._pvp_challenge_from
                            break
                    else:
                        # Timeout
                        if hasattr(target, '_pvp_challenge_from'):
                            del target._pvp_challenge_from
                        session.log(color(f"{t_name} didn't respond. Challenge expired.", DIM))

                    if accepted:
                        world.broadcast(f"{my_name} vs {t_name} - FIGHT!", RED)
                        await session.pvp_combat(target)
                        if session.char['hp'] <= 0:
                            await session.pvp_death(t_name)
                    elif hasattr(target, '_pvp_response'):
                        del target._pvp_response
            continue

        elif cmd == 'c':
            await session.character_screen()
            continue

        elif cmd == 'h' and current_tile in (4, OW_TOWN):
            await session.shop()
            continue

        elif cmd == 'r' and current_tile == 6:
            # Fountain
            roll = random.randint(1, 6)
            if roll <= 3:
                heal = random.randint(10, 25)
                session.char['hp'] = min(session.char['max_hp'], session.char['hp'] + heal)
                session.log(color(f"Refreshing water! +{heal} HP", CYAN))
            elif roll == 4:
                mp_restore = random.randint(5, 15)
                session.char['mp'] = min(session.char['max_mp'], session.char['mp'] + mp_restore)
                session.log(color(f"Mystical water! +{mp_restore} MP", CYAN))
            elif roll == 5:
                session.char['poisoned'] = True
                session.log(color("The water is tainted! You are poisoned!", MAGENTA))
            else:
                session.log("The fountain has dried up.")
                dungeon[py][px] = 0  # Remove fountain
            continue

        elif cmd == '>' and (current_tile == 3 or current_tile == OW_DUNGEON):
            if current_tile == OW_DUNGEON:
                # Enter dungeon from overworld
                # Save overworld position
                session.char['ow_x'] = session.char['x']
                session.char['ow_y'] = session.char['y']
                session.char['floor'] = 0
                sx, sy = get_floor_spawn(0)
                session.char['x'] = sx
                session.char['y'] = sy
                session.log(color("You descend into the dungeon...", YELLOW))
            else:
                # Go deeper in dungeon
                if session.char['floor'] >= MAX_FLOOR:
                    session.log(color("You have reached the deepest depths.", RED))
                    continue
                session.char['floor'] += 1
                sx, sy = get_floor_spawn(session.char['floor'])
                session.char['x'] = sx
                session.char['y'] = sy
                session.log(color(f"You descend to floor {session.char['floor']+1}...", YELLOW))
            save_character(session.char)
            continue

        elif cmd == '<' and current_tile == 4:
            if floor > 0:
                session.char['floor'] -= 1
                # Find stairs down on previous floor
                prev_floor = get_floor(session.char['floor'])
                for ry in range(len(prev_floor)):
                    for rx in range(len(prev_floor[0])):
                        if prev_floor[ry][rx] == 3:
                            session.char['x'] = rx
                            session.char['y'] = ry
                validate_position(session.char)
                session.log(color(f"You ascend to floor {session.char['floor']+1}...", GREEN))
                save_character(session.char)
            elif floor == 0:
                # Exit dungeon to overworld
                session.char['floor'] = OVERWORLD_FLOOR
                ox = session.char.get('ow_x', get_overworld_spawn()[0])
                oy = session.char.get('ow_y', get_overworld_spawn()[1])
                session.char['x'] = ox
                session.char['y'] = oy
                validate_position(session.char)  # make sure we're not in water/mountain
                session.log(color("You emerge into the sunlight!", GREEN))
                save_character(session.char)
            else:
                session.log("You're already at the top!")
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

        session.char['facing'] = new_facing

        # Check if we can move there
        if cmd == 'w':
            target = dungeon[new_y][new_x] if 0 <= new_y < len(dungeon) and 0 <= new_x < len(dungeon[0]) else 1
            # Check blocking tiles
            blocked = False
            if is_tile_blocked(target, floor):
                if target == OW_MOUNTAIN:
                    session.log("The mountain is too steep to climb!")
                elif target == OW_WATER:
                    session.log("You can't swim across!")
                else:
                    session.log("You bump into a wall!")
                blocked = True
            if blocked:
                # Don't full-redraw, just show the message in the log area
                if session.message_log:
                    vw, vh = session.get_view_size()
                    viewport_bottom = 3 + vh + 2 + 1
                    await session.move_to(viewport_bottom, 1)
                    await session.send("\033[2K")
                    await session.send(f" {session.message_log[-1]}")
                    session.message_log.clear()
                    await session.move_to(session.term_height, 1)
                    await session.send(" > ")
                continue
            else:
                session.char['x'] = new_x
                session.char['y'] = new_y

                # Check for treasure
                if target == 5:
                    t_key = f"{floor}_{new_x}_{new_y}"
                    if t_key not in session.char.get('treasures_found', []):
                        gold_found = random.randint(10, 50) * (floor + 1)
                        session.char['gold'] += gold_found
                        if 'treasures_found' not in session.char:
                            session.char['treasures_found'] = []
                        session.char['treasures_found'].append(t_key)

                        # Sometimes find items
                        roll = random.randint(1, 10)
                        if roll <= 2:
                            session.char['potions'] += 1
                            session.log(color(f"Found {gold_found} gold and a potion!", YELLOW))
                        else:
                            session.log(color(f"Found a chest with {gold_found} gold!", YELLOW))

                # Overworld interactions
                if target == OW_DUNGEON:
                    session.log(color("You see a dark dungeon entrance!", RED))
                elif target == OW_TOWN:
                    session.log(color("You enter a town. [H] to visit the shop.", GREEN))
                elif target == OW_FOREST:
                    if random.randint(1, 8) == 1:
                        session.log(color("The forest rustles ominously...", DIM))

                # Check if we walked into a monster
                mob = get_monster_at(floor, new_x, new_y)
                if mob:
                    allies = world.get_players_at(floor, new_x, new_y, session.char['name'])
                    ally_names = ', '.join(s.char['name'] for s in allies)
                    if allies:
                        world.broadcast(f"{session.char['name']} and {ally_names} fight a {mob['name']}!", YELLOW, exclude=session)
                    result = await session.combat(mob, allies)
                    if result == 'dead':
                        world.broadcast(f"{session.char['name']} has perished on floor {floor+1}!", RED)
                        await session.game_over()
                        if session.char.get('hardcore', False):
                            return
                        continue
                    elif result == 'victory':
                        kill_monster(mob)
                        if allies:
                            world.broadcast(f"{session.char['name']}'s party slew a {mob['name']}!", GREEN, exclude=session)
                        else:
                            world.broadcast(f"{session.char['name']} slew a {mob['name']} on floor {floor+1}!", GREEN, exclude=session)
                    save_character(session.char)

        # Poison tick
        if session.char.get('poisoned') and cmd == 'w':
            poison_dmg = random.randint(1, 3)
            session.char['hp'] -= poison_dmg
            # 15% chance to wear off each step
            if random.randint(1, 100) <= 15:
                session.char['poisoned'] = False
                session.log(color(f"Poison deals {poison_dmg} damage... but it wears off!", GREEN))
            else:
                session.log(color(f"Poison deals {poison_dmg} damage!", MAGENTA))
            if session.char['hp'] <= 0:
                await session.game_over()
                if session.char.get('hardcore', False):
                    return
                continue

        # Move monsters on this floor
        player_positions = [(session.char['x'], session.char['y'])]
        for s in world.get_players_at(floor, -1, -1):  # won't match anyone
            pass
        # Gather all player positions on this floor
        for _, s in world.sessions.items():
            if s.char and s.char['floor'] == floor and s != session:
                player_positions.append((s.char['x'], s.char['y']))
        move_floor_monsters(floor, player_positions)

        # Check if a monster walked into us
        mob = get_monster_at(floor, session.char['x'], session.char['y'])
        if mob:
            session.log(color(f"A {mob['name']} ambushes you!", RED))
            allies = world.get_players_at(floor, session.char['x'], session.char['y'], session.char['name'])
            result = await session.combat(mob, allies)
            if result == 'dead':
                world.broadcast(f"{session.char['name']} was slain by a {mob['name']}!", RED)
                await session.game_over()
                if session.char.get('hardcore', False):
                    return
                continue
            elif result == 'victory':
                kill_monster(mob)
                world.broadcast(f"{session.char['name']} slew a {mob['name']}!", GREEN, exclude=session)

        save_character(session.char)



async def character_screen(session):
    """Show character status screen."""
    c = session.char
    await session.send(CLEAR)
    mode_str = color(" [HARDCORE]", RED) if c.get('hardcore', False) else color(" [NORMAL]", GREEN)
    await session.send_line(color("=======================================", CYAN))
    await session.send_line(color(f"  {c['name']} the {c['class']}", WHITE) + mode_str)
    await session.send_line(color("=======================================", CYAN))
    await session.send_line()
    await session.send_line(f"  Level:    {c['level']}")
    await session.send_line(f"  XP:       {c['xp']} / {c['xp_next']}")
    await session.send_line(f"  HP:       {c['hp']} / {c['max_hp']}")
    await session.send_line(f"  MP:       {c['mp']} / {c['max_mp']}")
    await session.send_line(f"  ATK:      {session.get_atk()} (base {c['base_atk']} + {WEAPONS[c['weapon']]['name']})")
    await session.send_line(f"  DEF:      {session.get_def()} (base {c['base_def']} + {ARMOR[c['armor']]['name']})")
    await session.send_line(f"  SPD:      {c['spd']}")
    await session.send_line(f"  Gold:     {c['gold']}")
    await session.send_line(f"  Potions:  {c['potions']}")
    await session.send_line(f"  Kills:    {c['kills']}")
    await session.send_line(f"  Floor:    {c['floor'] + 1}")
    if c.get('poisoned'):
        await session.send_line(color("  STATUS:   POISONED", MAGENTA))
    await session.send_line()
    spells = c.get('spells', [])
    if spells:
        await session.send_line(color("  Known Spells:", CYAN))
        for sp in spells:
            info = SPELLS[sp]
            await session.send_line(f"    {sp}: {info['desc']} (MP: {info['cost']})")
    await session.send_line()
    await session.get_char(color("  Press any key to return...", DIM))

