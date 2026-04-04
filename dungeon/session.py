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
from dungeon.region import try_zone_transition, get_segment_display_name, get_current_segment
from dungeon.quests import (
    get_visible_entrances, get_all_visible_npcs,
    run_npc_dialog, get_quest_stage,
    set_quest_stage, apply_quest_rewards, has_quest_flag,
    apply_all_active_mods,
)
from dungeon.trading import run_direct_trade


async def show_full_map(session, dungeon, floor_num, quest_entrances=None, quest_npcs=None):
    """Full-screen scrollable map view with zoom levels."""
    from dungeon.config import (
        CSI, CLEAR, RESET,
        OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
    )
    from dungeon.monsters import get_floor_monsters
    from dungeon.region import (
        load_region_index, load_segment, get_current_segment, get_segment_display_name,
    )

    size = len(dungeon)
    px, py = session.char['x'], session.char['y']
    tw, th = session.term_width, session.term_height
    map_rows = th - 3
    map_cols = tw - 2

    # Zoom: 1 = 1:1, 2 = 1:2 (each char = 2x2 tiles), etc
    zoom = 1
    world_view = False

    # Build lookup sets for current segment
    qe_set = {(e[0], e[1]) for e in (quest_entrances or [])}
    npc_set = {(n['x'], n['y']): n['symbol'] for n in (quest_npcs or [])}
    mob_set = {(m['x'], m['y']): m['symbol'] for m in get_floor_monsters(floor_num) if m['alive']}

    tile_render = {
        0: ('.', '37'), 1: ('#', '90'), 2: ('+', '36'), 3: ('>', '31'),
        4: ('<', '32'), 5: ('$', '93'), 6: ('~', '36'),
        OW_GRASS: ('.', '32'), OW_FOREST: ('T', '32'), OW_MOUNTAIN: ('^', '37'),
        OW_WATER: ('~', '34'), OW_ROAD: ('=', '33'), OW_TOWN: ('@', '93'),
        OW_DUNGEON: ('D', '31'), 17: ('>', '95'),  # portal
    }

    # Camera in tile coords
    cam_x = max(0, px - map_cols // 2)
    cam_y = max(0, py - map_rows // 2)

    while True:
        await session.send(CLEAR)
        await session.move_to(1, 1)

        if world_view:
            # World map: stitch all segments, heavily downsampled
            idx = load_region_index()
            n_cols = idx.get('cols', 6)
            n_rows = idx.get('rows', 8)
            seg_size = 128
            # Each segment gets a few chars
            chars_per_seg_x = max(1, map_cols // n_cols)
            chars_per_seg_y = max(1, map_rows // n_rows)
            tiles_per_char_x = seg_size // chars_per_seg_x
            tiles_per_char_y = seg_size // chars_per_seg_y

            cur_col, cur_row = get_current_segment(session.char)
            zone = get_segment_display_name(cur_col, cur_row)
            await session.send(color(f" WORLD MAP - {zone}  +/-=zoom M/Q=close", CYAN))

            # Render top-to-bottom (row n_rows-1 is north = top)
            for vr in range(min(map_rows, n_rows * chars_per_seg_y)):
                seg_row = n_rows - 1 - (vr // chars_per_seg_y)
                local_y = (vr % chars_per_seg_y) * tiles_per_char_y
                row_str = ""
                for vc in range(min(map_cols, n_cols * chars_per_seg_x)):
                    seg_col = vc // chars_per_seg_x
                    local_x = (vc % chars_per_seg_x) * tiles_per_char_x

                    # Player marker
                    if seg_col == cur_col and seg_row == cur_row:
                        # Check if player is in this chunk
                        px_chunk = px // tiles_per_char_x
                        py_chunk = py // tiles_per_char_y
                        if (vc % chars_per_seg_x) == px_chunk and (vr % chars_per_seg_y) == py_chunk:
                            row_str += f"{CSI}30;107m@{RESET}"
                            continue

                    # Sample tile from segment
                    seg = load_segment(seg_col, seg_row)
                    if seg and 0 <= local_y < len(seg) and 0 <= local_x < len(seg[0]):
                        t = seg[local_y][local_x]
                        ch, code = tile_render.get(t, ('.', '90'))
                        row_str += f"{CSI}{code}m{ch}{RESET}"
                    else:
                        row_str += " "
                await session.move_to(2 + vr, 1)
                await session.send(row_str)

            # Town labels
            label_row = 2 + min(map_rows, n_rows * chars_per_seg_y) + 1
            if label_row < th:
                await session.move_to(label_row, 1)
                labels = "".join(color(f" {seg['towns'][0]}", YELLOW)
                               for seg in idx.get('segments', []) if seg.get('towns'))
                await session.send(labels[:tw-2])

        else:
            # Normal map with zoom
            zone_col, zone_row = get_current_segment(session.char)
            zone = get_segment_display_name(zone_col, zone_row)
            zoom_label = f"x{zoom}" if zoom > 1 else "1:1"
            await session.send(color(
                f" MAP - {zone} [{px},{py}] zoom:{zoom_label}  WASD=scroll +/-=zoom Z=world M/Q=close",
                CYAN))

            total_size = size  # could expand for multi-segment view at zoom > 4

            for vr in range(map_rows):
                my = cam_y + vr * zoom
                row_str = ""
                for vc in range(map_cols):
                    mx = cam_x + vc * zoom

                    # At zoom > 1, sample the dominant tile in the area
                    tmx, tmy = (mx, my) if zoom == 1 else (mx + zoom // 2, my + zoom // 2)

                    if tmx == px and tmy == py and zoom == 1:
                        row_str += f"{CSI}30;107m@{RESET}"
                    elif zoom == 1 and (tmx, tmy) in npc_set:
                        row_str += f"{CSI}96m{npc_set[(tmx, tmy)]}{RESET}"
                    elif zoom == 1 and (tmx, tmy) in qe_set:
                        row_str += f"{CSI}95m?{RESET}"
                    elif zoom == 1 and (tmx, tmy) in mob_set:
                        row_str += f"{CSI}91m{mob_set[(tmx, tmy)]}{RESET}"
                    elif 0 <= tmx < total_size and 0 <= tmy < total_size:
                        t = dungeon[tmy][tmx] if tmy < len(dungeon) and tmx < len(dungeon[0]) else 13
                        ch, code = tile_render.get(t, ('?', '90'))
                        # Player marker at any zoom
                        if zoom > 1 and mx <= px < mx + zoom and my <= py < my + zoom:
                            row_str += f"{CSI}30;107m@{RESET}"
                        else:
                            row_str += f"{CSI}{code}m{ch}{RESET}"
                    else:
                        row_str += " "
                await session.move_to(2 + vr, 1)
                await session.send(row_str)

        # Legend at bottom
        legend_row = th - 1
        await session.move_to(legend_row, 1)
        await session.send(
            f" {CSI}30;107m@{RESET}You"
            f" {CSI}93m@{RESET}Town"
            f" {CSI}33m={RESET}Road"
            f" {CSI}32m.{RESET}Grass"
            f" {CSI}32mT{RESET}Forest"
            f" {CSI}37m^{RESET}Mt"
            f" {CSI}34m~{RESET}Water"
            f" {CSI}31mD{RESET}Dungeon"
            f" {CSI}96mG{RESET}NPC"
            f" {CSI}95m?{RESET}Quest"
        )

        cmd = (await session.get_char("")).lower()
        if cmd in ('q', 'm', '\x1b'):
            break
        scroll = max(1, 5 * zoom)
        if cmd == 'w':
            cam_y = max(0, cam_y - scroll)
        elif cmd == 's':
            max_cam = max(0, size * zoom - map_rows * zoom)
            cam_y = min(max_cam, cam_y + scroll)
        elif cmd == 'a':
            cam_x = max(0, cam_x - scroll)
        elif cmd == 'd':
            max_cam = max(0, size * zoom - map_cols * zoom)
            cam_x = min(max_cam, cam_x + scroll)
        elif cmd in ('+', '='):
            zoom = min(8, zoom * 2)
            cam_x = max(0, px - (map_cols * zoom) // 2)
            cam_y = max(0, py - (map_rows * zoom) // 2)
        elif cmd == '-':
            zoom = max(1, zoom // 2)
            cam_x = max(0, px - (map_cols * zoom) // 2)
            cam_y = max(0, py - (map_rows * zoom) // 2)
        elif cmd == 'z':
            world_view = not world_view


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
        col, row = get_current_segment(session.char)
        zone_name = get_segment_display_name(col, row)
        header = f" {zone_name} ({fsize}x{fsize}) [{px},{py}]"
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
    # Quest data for minimap
    quest_entrances = get_visible_entrances(session.char, floor)
    quest_npcs = get_all_visible_npcs(session.char, floor)
    minimap = render_minimap(
        dungeon, px, py, facing, map_radius, other_players, floor,
        quest_markers=[(e[0], e[1], '?', MAGENTA) for e in quest_entrances]
                    + [(n['x'], n['y'], n['symbol'], CYAN) for n in quest_npcs],
    )

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
                edge_col = mid_col + int(map_w/2 * dx / max(1, abs(dy)))
                edge_col = max(map_col, min(map_col + map_w - 1, edge_col))
                if dy > 0:
                    # Bottom
                    await session.send_at(map_start + map_h, edge_col, color(f"{label}v", GREEN))
                else:
                    # Top
                    await session.send_at(map_start - 1, edge_col, color(f"{label}^", GREEN))

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

    status = f" HP:{hp_bar}  MP:{mp_bar}  Gold:{color(str(session.char['gold']), YELLOW)}  "
    f"Pot:{session.char['potions']}"
    if session.char.get('poisoned'):
        status += color(" [POISON]", MAGENTA)
    hc_tag = color(" [HC]", RED) if session.char.get('hardcore', False) else ""
    await session.send_at(status_row, 1, status + hc_tag)

    await session.send_at(status_row + 1, 1, f" ATK:{session.get_atk()} DEF:{session.get_def()} "
                                               f"SPD:{session.char['spd']} XP:{session.char['xp']}/"
                                               f"{session.char['xp_next']}  "
                                               f"{WEAPONS[session.char['weapon']]['name']} / "
                                               f"{ARMOR[session.char['armor']]['name']}")

    # Controls at very bottom
    ctrl_row = th - 1
    controls = f" {color('W', YELLOW)}Fwd {color('A', YELLOW)}Left {color('D', YELLOW)}Right "
    f"{color('S', YELLOW)}Back {color('C', YELLOW)}har {color('T', YELLOW)}alk "
    f"{color('M', YELLOW)}ap"
    if others_here:
        controls += f" {color('E', YELLOW)}xch {color('P', RED)}vP"
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

    # Quest entrance at current position
    for qe in quest_entrances:
        if qe[0] == px and qe[1] == py:
            label = qe[3].get('label', 'Quest Dungeon')
            controls += f" {color('>', MAGENTA)}{label}"
            break

    # Quest NPC nearby (on current tile)
    for npc in quest_npcs:
        if npc['x'] == px and npc['y'] == py:
            controls += f" {color('[N]', CYAN)}{npc['name']}"
            break

    await session.send_at(ctrl_row, 1, controls)

    # Prompt on last row
    await session.send_at(th, 1, " > ")



async def run_main_loop(session, world):
    """Main exploration loop."""
    # Load correct region segment on login
    if session.char.get('floor') == OVERWORLD_FLOOR:
        from dungeon.region import load_segment, get_current_segment, get_segment_display_name
        from dungeon.floor import set_overworld
        col, row = get_current_segment(session.char)
        seg = load_segment(col, row)
        if seg:
            set_overworld(seg)

    # Apply quest map modifications for any active quests
    apply_all_active_mods(session.char)
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
        # Quest data for this tick
        quest_entrances = get_visible_entrances(session.char, floor)
        quest_npcs = get_all_visible_npcs(session.char, floor)
        cmd = (await session.get_char("", redraw_on_resize=True)).lower()

        # On resize, force full redraw
        if cmd == 'resize':
            session.invalidate_frame()
            await session.send(CLEAR)
            continue

        # Handle incoming trade response
        if cmd == 'y' and hasattr(session, '_trade_pending'):
            session._trade_response = True
            session.log(color("Trade accepted!", GREEN))
            continue
        elif cmd == 'n' and hasattr(session, '_trade_pending'):
            session._trade_response = False
            session.log(color("Trade declined.", DIM))
            del session._trade_pending
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

        elif cmd == 'n':
            # Talk to quest NPC on current tile
            for npc in quest_npcs:
                if npc['x'] == px and npc['y'] == py:
                    quest_id = npc.get('quest_id')
                    await run_npc_dialog(session, npc, quest_id)
                    # Check if quest just completed (returned to Ginger with both cats)
                    if (quest_id and has_quest_flag(session.char, quest_id, 'bookeater_found')
                            and npc.get('location') == 'town'
                            and get_quest_stage(session.char, quest_id) != 'complete'):
                        set_quest_stage(session.char, quest_id, 'complete')
                        msgs = apply_quest_rewards(session.char, quest_id)
                        for msg in msgs:
                            await session.send_line(msg)
                        await session.get_char(color("  (press any key)", DIM))
                    session.invalidate_frame()
                    break
            else:
                session.log("No one to talk to here.")
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
                    target.log(color(f"{my_name} challenges you to a duel! Press [Y] to accept or "
                                   f"[N] to decline.", YELLOW))
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

        elif cmd == 'e':
            # Trading - only available with other players on same tile
            others_here = world.get_players_at(floor, px, py, session.char['name'])
            if not others_here:
                session.log("No one here to trade with!")
            elif len(others_here) == 1:
                # Only one other player - trade with them
                target = others_here[0]
                await run_direct_trade(session, target, world)
                session.invalidate_frame()
            else:
                # Multiple players - let user choose
                await session.move_to(session.term_height, 1)
                await session.send("\033[2K")  # clear the line
                for i, s in enumerate(others_here, 1):
                    await session.send(f" [{i}]{s.char['name']} ")
                pick = await session.get_char(" Trade with who? (0=cancel): ")
                try:
                    idx = int(pick) - 1
                    if 0 <= idx < len(others_here):
                        target = others_here[idx]
                        await run_direct_trade(session, target, world)
                        session.invalidate_frame()
                except ValueError:
                    pass
            continue

        elif cmd == 'm':
            await show_full_map(session, dungeon, floor, quest_entrances, quest_npcs)
            session.invalidate_frame()
            await session.send(CLEAR)
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

        elif cmd == '>':
            # Check for quest entrance first
            quest_entrance = None
            for qe in quest_entrances:
                if qe[0] == px and qe[1] == py:
                    quest_entrance = qe
                    break
            if quest_entrance:
                _qx, _qy, quest_id, ent_data = quest_entrance
                target_floor = ent_data.get('target_floor', 'gyre_1')
                label = ent_data.get('label', 'Quest Dungeon')
                # Save return position
                session.char['quest_return_floor'] = floor
                session.char['quest_return_x'] = px
                session.char['quest_return_y'] = py
                # Enter quest dungeon (use quest floor ID as a string-keyed floor)
                # For now, map quest floors to high floor numbers to avoid collision
                quest_floor_map = {
                    'gyre_1': 90000,
                    'gyre_2': 90001,
                }
                qfloor = quest_floor_map.get(target_floor, 90000)
                session.char['floor'] = qfloor
                sx, sy = get_floor_spawn(qfloor)
                session.char['x'] = sx
                session.char['y'] = sy
                session.log(color(f"You enter {label}...", MAGENTA))
                session.invalidate_frame()
                save_character(session.char)
                continue

            if not (current_tile == 3 or current_tile == OW_DUNGEON):
                continue
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
            # Check if we're in a quest dungeon
            if floor >= 90000:
                ret_floor = session.char.get('quest_return_floor', OVERWORLD_FLOOR)
                ret_x = session.char.get('quest_return_x', 1)
                ret_y = session.char.get('quest_return_y', 1)
                session.char['floor'] = ret_floor
                session.char['x'] = ret_x
                session.char['y'] = ret_y
                validate_position(session.char)
                session.log(color("You leave the quest dungeon...", GREEN))
                session.invalidate_frame()
                save_character(session.char)
                continue
            elif floor > 0:
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
            map_size = len(dungeon)

            # Check for zone transition (walking off edge OR into border of overworld)
            at_edge = (not (0 <= new_y < map_size and 0 <= new_x < map_size)
                       or (is_overworld(floor) and (new_y <= 0 or new_y >= map_size - 1
                           or new_x <= 0 or new_x >= map_size - 1)))
            if at_edge:
                # Translate border positions to out-of-bounds for the transition logic
                trans_x = -1 if new_x <= 0 else (map_size if new_x >= map_size - 1 else new_x)
                trans_y = -1 if new_y <= 0 else (map_size if new_y >= map_size - 1 else new_y)
                transitioned, new_grid = try_zone_transition(session.char, trans_x, trans_y, map_size)
                if transitioned and new_grid:
                    # Swap the overworld to the new segment
                    from dungeon.floor import set_overworld
                    set_overworld(new_grid)
                    col, row = get_current_segment(session.char)
                    zone_name = get_segment_display_name(col, row)
                    session.log(color(f"Entering {zone_name}...", CYAN))
                    session.invalidate_frame()
                    await session.send(CLEAR)
                    save_character(session.char)
                    continue
                else:
                    session.log("You can't go any further.")
                    continue

            target = dungeon[new_y][new_x]
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
                        effective_floor = min(floor, 50) if floor < 90000 else 5
                        gold_found = random.randint(10, 50) * (effective_floor + 1)
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

                # Check if we walked into a quest NPC
                for npc in quest_npcs:
                    if npc['x'] == new_x and npc['y'] == new_y:
                        await run_npc_dialog(session, npc, npc.get('quest_id'))
                        session.invalidate_frame()
                        break

                # Check if we walked into a monster
                mob = get_monster_at(floor, new_x, new_y)
                if mob:
                    allies = world.get_players_at(floor, new_x, new_y, session.char['name'])
                    ally_names = ', '.join(s.char['name'] for s in allies)
                    if allies:
                        world.broadcast(f"{session.char['name']} and {ally_names} fight a {mob['name']}!",
                                      YELLOW, exclude=session)
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
                            world.broadcast(f"{session.char['name']}'s party slew a {mob['name']}!",
                                          GREEN, exclude=session)
                        else:
                            world.broadcast(f"{session.char['name']} slew a {mob['name']} on floor {floor+1}!",
                                          GREEN, exclude=session)
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

