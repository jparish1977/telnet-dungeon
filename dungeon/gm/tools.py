"""GM/admin tools - player management, monster editor, map editor, theme editor."""

import asyncio
from contextlib import suppress

from dungeon.config import (
    CSI, CLEAR, DIM, RESET, RED, GREEN, YELLOW, CYAN, WHITE, MAGENTA,
    color, COLOR_NAMES, BG_COLOR_NAMES,
    OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
)
from dungeon.items import WEAPONS, ARMOR
from dungeon.persistence import (
    save_character, load_character, list_saves,
    load_custom_monsters, save_custom_monsters,
    save_builtin_overrides, save_custom_floor,
    load_scene_themes, save_scene_themes,
)
from dungeon.floor import (
    get_floor, get_floor_spawn, set_floor,
    is_overworld, MAX_FLOOR,
)
from dungeon.monsters import (
    MONSTERS_BY_FLOOR, get_floor_monsters, get_monsters_for_floor,
)


async def gm_pick_player(session, world, prompt="Pick player: "):
    """Show numbered list of online players, return chosen session or None."""
    players = list(world.sessions.items())
    if not players:
        await session.send_line(color("  No players online.", DIM))
        await session.get_char("  Press any key...")
        return None
    for i, (name, s) in enumerate(players, 1):
        loc = f"F{s.char['floor']+1} ({s.char['x']},{s.char['y']})" if s.char else "?"
        gm_tag = color(" [GM]", MAGENTA) if s.is_gm else ""
        await session.send_line(f"  {color(f'[{i}]', YELLOW)} {name} Lv.{s.char['level'] if s.char else '?'} "
                               f"{loc}{gm_tag}")
    await session.send_line(f"  {color('[0]', YELLOW)} Cancel")
    pick = await session.get_char(f"  {prompt}")
    with suppress(ValueError):
        idx = int(pick) - 1
        if 0 <= idx < len(players):
            return players[idx][1]
    return None

async def _pick_floor(session, label="Floor"):
    """Prompt for a floor number. Returns int or None."""
    inp = await session.get_input(f"  {label} (0+ or -1=overworld): ")
    try:
        return int(inp)
    except ValueError:
        return None


async def gm_menu(session, world):
    """Full GM/moderator menu. Works with or without a character loaded."""
    has_char = session.char is not None
    while True:
        await session.send(CLEAR)
        await session.send_line(color("=== GAME MASTER MENU ===", MAGENTA))
        if not has_char:
            await session.send_line(color("  (No character loaded — editor mode)", DIM))
        await session.send_line()
        if has_char:
            await session.send_line(f"  {color('[1]', YELLOW)} Teleport to player")
            await session.send_line(f"  {color('[2]', YELLOW)} Teleport player to me")
        await session.send_line(f"  {color('[3]', YELLOW)} Edit player stats")
        await session.send_line(f"  {color('[4]', YELLOW)} Edit player inventory")
        if has_char:
            await session.send_line(f"  {color('[5]', YELLOW)} Set player location")
        await session.send_line(f"  {color('[6]', YELLOW)} Kick player")
        await session.send_line(f"  {color('[7]', YELLOW)} Ban player")
        await session.send_line(f"  {color('[8]', YELLOW)} Unban player")
        await session.send_line(f"  {color('[9]', YELLOW)} Broadcast message")
        await session.send_line(f"  {color('[0]', YELLOW)} List all players")
        if has_char:
            await session.send_line(f"  {color('[F]', YELLOW)} Teleport to floor")
            await session.send_line(f"  {color('[R]', YELLOW)} Region teleport")
        await session.send_line(f"  {color('[M]', YELLOW)} Monster editor")
        await session.send_line(f"  {color('[E]', YELLOW)} Map tile editor")
        await session.send_line(f"  {color('[V]', YELLOW)} Viewport theme editor")
        await session.send_line(f"  {color('[B]', YELLOW)} Back")
        await session.send_line()

        choice = (await session.get_char("  GM> ")).upper()

        if choice == 'B':
            break

        elif choice == '1' and has_char:
            # Teleport TO a player
            await session.send_line()
            target = await gm_pick_player(session, world, "Go to: ")
            if target and target.char:
                session.char['floor'] = target.char['floor']
                session.char['x'] = target.char['x']
                session.char['y'] = target.char['y']
                session.log(color(f"Teleported to {target.char['name']}!", MAGENTA))
                save_character(session.char)
                break

        elif choice == '2' and has_char:
            # Teleport player TO me
            await session.send_line()
            target = await gm_pick_player(session, world, "Summon: ")
            if target and target.char:
                target.char['floor'] = session.char['floor']
                target.char['x'] = session.char['x']
                target.char['y'] = session.char['y']
                target.log(color(f"You were summoned by {session.char['name']}!", MAGENTA))
                target.notify_event.set()
                save_character(target.char)
                session.log(color(f"Summoned {target.char['name']}!", MAGENTA))

        elif choice == '3':
            # Edit player stats
            await session.send_line()
            target = await gm_pick_player(session, world, "Edit stats: ")
            if target and target.char:
                await session.send(CLEAR)
                c = target.char
                await session.send_line(color(f"=== EDIT {c['name']} ===", MAGENTA))
                await session.send_line(f"  [1] HP:     {c['hp']}/{c['max_hp']}")
                await session.send_line(f"  [2] MP:     {c['mp']}/{c['max_mp']}")
                await session.send_line(f"  [3] ATK:    {c['base_atk']}")
                await session.send_line(f"  [4] DEF:    {c['base_def']}")
                await session.send_line(f"  [5] SPD:    {c['spd']}")
                await session.send_line(f"  [6] Level:  {c['level']}")
                await session.send_line(f"  [7] XP:     {c['xp']}")
                await session.send_line(f"  [8] Poison: {c.get('poisoned', False)}")
                await session.send_line("  [9] Full heal")
                await session.send_line("  [0] Cancel")
                stat = await session.get_char("  Stat: ")
                if stat == '9':
                    c['hp'] = c['max_hp']
                    c['mp'] = c['max_mp']
                    c['poisoned'] = False
                    target.log(color("You feel fully restored!", GREEN))
                    target.notify_event.set()
                    session.log(color(f"Healed {c['name']}!", GREEN))
                    save_character(c)
                elif stat == '8':
                    c['poisoned'] = not c.get('poisoned', False)
                    session.log(f"Poison toggled to {c['poisoned']}")
                    save_character(c)
                elif stat in ('1','2','3','4','5','6','7'):
                    keys = {'1': ('hp', 'max_hp'), '2': ('mp', 'max_mp'),
                            '3': ('base_atk',), '4': ('base_def',), '5': ('spd',),
                            '6': ('level',), '7': ('xp',)}
                    fields = keys[stat]
                    for field in fields:
                        if val := await session.get_input(f"  {field} = "):
                            with suppress(ValueError):
                                c[field] = int(val)
                    target.notify_event.set()
                    save_character(c)
                    session.log(color(f"Updated {c['name']}!", GREEN))

        elif choice == '4':
            # Edit inventory
            await session.send_line()
            target = await gm_pick_player(session, world, "Edit inventory: ")
            if target and target.char:
                await session.send(CLEAR)
                c = target.char
                await session.send_line(color(f"=== INVENTORY: {c['name']} ===", MAGENTA))
                await session.send_line(f"  [1] Gold:    {c['gold']}")
                await session.send_line(f"  [2] Potions: {c['potions']}")
                await session.send_line(f"  [3] Weapon:  {WEAPONS[c['weapon']]['name']} ({c['weapon']})")
                for i, w in enumerate(WEAPONS):
                    await session.send_line(f"       {i}: {w['name']}")
                await session.send_line(f"  [4] Armor:   {ARMOR[c['armor']]['name']} ({c['armor']})")
                for i, a in enumerate(ARMOR):
                    await session.send_line(f"       {i}: {a['name']}")
                await session.send_line("  [0] Cancel")
                item = await session.get_char("  Edit: ")
                if item in ('1','2','3','4'):
                    field = {'1': 'gold', '2': 'potions', '3': 'weapon', '4': 'armor'}[item]
                    if val := await session.get_input(f"  {field} = "):
                        with suppress(ValueError):
                            v = int(val)
                            if field == 'weapon' and 0 <= v < len(WEAPONS):
                                c['weapon'] = v
                            elif field == 'armor' and 0 <= v < len(ARMOR):
                                c['armor'] = v
                            elif field in ('gold', 'potions'):
                                c[field] = max(0, v)
                            target.notify_event.set()
                            save_character(c)
                            session.log(color(f"Updated {c['name']}'s {field}!", GREEN))

        elif choice == '5' and has_char:
            # Set player location
            await session.send_line()
            target = await gm_pick_player(session, world, "Move: ")
            if target and target.char:
                await session.send_line(f"  Current: Floor {target.char['floor']+1} "
                                       f"({target.char['x']},{target.char['y']})")
                if fl := await session.get_input("  Floor (0+): "):
                    if x := await session.get_input("  X: "):
                        if y := await session.get_input("  Y: "):
                            with suppress(ValueError):
                                fl, x, y = int(fl), int(x), int(y)
                                target_floor = get_floor(fl)
                                fsize = len(target_floor)
                                if fl >= 0 and 0 <= x < fsize and 0 <= y < fsize:
                                    if target_floor[y][x] != 1:
                                        target.char['floor'] = fl
                                        target.char['x'] = x
                                        target.char['y'] = y
                                        target.log(color(f"You were moved by {session.char['name']}!", MAGENTA))
                                        target.notify_event.set()
                                        save_character(target.char)
                                        session.log(color(f"Moved {target.char['name']}!", GREEN))
                                    else:
                                        session.log(color("That's inside a wall!", RED))
                                else:
                                    session.log(color("Out of bounds!", RED))

        elif choice == '6':
            # Kick
            await session.send_line()
            target = await gm_pick_player(session, world, "Kick: ")
            if target and target.char:
                name = target.char['name']
                reason = await session.get_input("  Reason: ") or "Kicked by GM"
                await world.kick_player(name, reason)
                session.log(color(f"Kicked {name}!", RED))

        elif choice == '7':
            # Ban
            await session.send_line()
            await session.send_line(color("  Online players:", WHITE))
            target = await gm_pick_player(session, world, "Ban: ")
            if target and target.char:
                name = target.char['name']
                world.ban_player(name)
                await world.kick_player(name, "You have been BANNED")
                session.log(color(f"Banned {name}!", RED))
            else:
                # Can also ban offline players by name
                await session.send_line()
                name = await session.get_input("  Ban name (offline): ")
                if name.strip():
                    world.ban_player(name.strip())
                    session.log(color(f"Banned {name.strip()}!", RED))

        elif choice == '8':
            # Unban
            if not world.banned:
                await session.send_line(color("  No banned players.", DIM))
                await session.get_char("  Press any key...")
            else:
                await session.send_line()
                for i, name in enumerate(world.banned, 1):
                    await session.send_line(f"  [{i}] {name}")
                await session.send_line("  [0] Cancel")
                pick = await session.get_char("  Unban: ")
                with suppress(ValueError):
                    if 0 <= (idx := int(pick) - 1) < len(world.banned):
                        name = world.banned[idx]
                        world.unban_player(name)
                        session.log(color(f"Unbanned {name}!", GREEN))

        elif choice == '9':
            # Broadcast
            await session.send_line()
            msg = await session.get_input("  Broadcast: ")
            if msg.strip():
                world.broadcast(f"[GM] {msg.strip()}", MAGENTA)

        elif choice == '0':
            # List all players
            await session.send(CLEAR)
            await session.send_line(color("=== ALL PLAYERS ===", MAGENTA))
            await session.send_line()
            await session.send_line(color("  ONLINE:", GREEN))
            for name, s in world.sessions.items():
                if s.char:
                    c = s.char
                    gm = color(" [GM]", MAGENTA) if s.is_gm else ""
                    await session.send_line(f"    {name} Lv.{c['level']} {c['class']} F{c['floor']+1} "
                                           f"({c['x']},{c['y']}) HP:{c['hp']}/{c['max_hp']} "
                                           f"Gold:{c['gold']}{gm}")
            await session.send_line()
            await session.send_line(color("  SAVED (offline):", DIM))
            for sname in list_saves():
                if sname not in [n.lower() for n in world.sessions]:
                    if sc := load_character(sname):
                        banned = color(" [BANNED]", RED) if world.is_banned(sc['name']) else ""
                        await session.send_line(f"    {sc['name']} Lv.{sc['level']} {sc['class']} "
                                               f"F{sc['floor']+1}{banned}")
            if world.banned:
                await session.send_line()
                await session.send_line(color(f"  BANNED: {', '.join(world.banned)}", RED))
            await session.send_line()
            await session.get_char(color("  Press any key...", DIM))

        elif choice == 'F' and has_char:
            # Teleport to floor
            await session.send_line()
            if fl_input := await session.get_input(f"  Floor number (1-{MAX_FLOOR+1}): "):
                with suppress(ValueError):
                    fl = int(fl_input) - 1  # display is 1-based
                    if 0 <= fl <= MAX_FLOOR:
                        session.char['floor'] = fl
                        sx, sy = get_floor_spawn(fl)
                        session.char['x'] = sx
                        session.char['y'] = sy
                        fsize = len(get_floor(fl))
                        session.log(color(f"Teleported to floor {fl+1} ({fsize}x{fsize})!", MAGENTA))
                        save_character(session.char)
                        break  # back to game
                    else:
                        session.log(color("Invalid floor!", RED))

        elif choice == 'R' and has_char:
            # Region teleport
            from dungeon.region import load_region_index, load_segment, get_segment_display_name
            from dungeon.floor import set_overworld
            idx = load_region_index()
            await session.send_line()
            await session.send_line(color("  Available regions:", WHITE))
            segments_with_towns = [seg for seg in idx.get('segments', []) if seg.get('towns')]
            # Also show all segments
            all_segs = idx.get('segments', [])
            for i, seg in enumerate(all_segs):
                towns = ', '.join(seg.get('towns', [])) or 'wilderness'
                grid = seg.get('grid', [0, 0])
                marker = " <--" if (grid[0] == session.char.get('region_col', 3)
                                    and grid[1] == session.char.get('region_row', 0)) else ""
                await session.send_line(f"  [{i+1:2d}] ({grid[0]},{grid[1]}) {towns}{marker}")
            await session.send_line()
            if pick := await session.get_input("  Teleport to #: "):
                with suppress(ValueError):
                    if 0 <= (idx_pick := int(pick) - 1) < len(all_segs):
                        seg = all_segs[idx_pick]
                        grid_pos = seg.get('grid', [0, 0])
                        if new_grid := load_segment(grid_pos[0], grid_pos[1]):
                            set_overworld(new_grid)
                            session.char['floor'] = -1  # overworld
                            session.char['region_col'] = grid_pos[0]
                            session.char['region_row'] = grid_pos[1]
                            # Spawn at center or town
                            size = len(new_grid)
                            sx, sy = size // 2, size // 2
                            for y in range(size):
                                for x in range(size):
                                    if new_grid[y][x] == 15:  # town
                                        sx, sy = x, y
                                        break
                                else:
                                    continue
                                break
                            session.char['x'] = sx
                            session.char['y'] = sy
                            zone = get_segment_display_name(grid_pos[0], grid_pos[1])
                            session.log(color(f"Teleported to {zone}!", MAGENTA))
                            save_character(session.char)
                            break
                        else:
                            session.log(color("Segment not found!", RED))

        elif choice == 'M':
            await gm_monster_editor(session, world)

        elif choice == 'E':
            floor = session.char['floor'] if has_char else 0
            await gm_scene_editor(session, world, floor)
            break  # back to game to see changes

        elif choice == 'V':
            floor = session.char['floor'] if has_char else 0
            await gm_viewport_theme_editor(session, floor)
            break

def _col_label(c):
    """Column label: 1-9 then a-z."""
    return str(c + 1) if c < 9 else chr(ord('a') + c - 9)

def _parse_col(ch):
    """Parse column label back to 0-based index."""
    if ch.isdigit() and ch != '0':
        return int(ch) - 1
    elif ch.isalpha():
        return ord(ch.lower()) - ord('a') + 9
    else:
        return -1

async def _draw_art_grid(session, art):
    """Draw the art with row numbers and column ruler."""
    # Find max width
    max_w = max((len(line) for line in art), default=0)
    max_w = max(max_w, 20)  # minimum grid width

    # Column ruler
    ruler = "    "
    for c in range(max_w):
        ruler += _col_label(c)
    await session.send_line(color(ruler, DIM))

    # Rows
    if art:
        for i, line in enumerate(art):
            padded = line.ljust(max_w)
            display = "".join(color('.', f"{CSI}90m") if ch == ' ' else color(ch, RED) for ch in padded)
            await session.send_line(f"  {color(f'{i+1:2d}', YELLOW)}{display}")
    else:
        await session.send_line(color("  (empty)", DIM))

async def edit_art_lines(session, current_art=None):
    """Interactive ASCII art editor with grid display. Returns new art list."""
    art = list(current_art) if current_art else []

    while True:
        await session.send_line()
        await session.send_line(color("  --- Art Editor ---", YELLOW))
        await _draw_art_grid(session, art)
        await session.send_line()
        await session.send_line(f"  {color('A', YELLOW)}dd  {color('E', YELLOW)}dit#  {color('D', YELLOW)}el#  "
                               f"{color('I', YELLOW)}ns#  {color('P', YELLOW)}lot(r,c,ch)  "
                               f"{color('R', YELLOW)}eplace  {color('Q', YELLOW)}done")

        cmd = (await session.get_char("  > ")).lower()

        if cmd == 'q':
            break
        elif cmd == 'a':
            line = await session.get_input("  new line> ", preserve_spaces=True)
            if line:
                art.append(line)
        elif cmd == 'e':
            if num := await session.get_input("  line #: "):
                with suppress(ValueError):
                    if 0 <= (idx := int(num) - 1) < len(art):
                        new_line = await session.get_input("  edit> ", preserve_spaces=True, prefill=art[idx])
                        if new_line is not None:
                            art[idx] = new_line
        elif cmd == 'd':
            if num := await session.get_input("  del #: "):
                with suppress(ValueError):
                    if 0 <= (idx := int(num) - 1) < len(art):
                        art.pop(idx)
        elif cmd == 'i':
            if num := await session.get_input("  insert before #: "):
                with suppress(ValueError):
                    if 0 <= (idx := int(num) - 1) <= len(art):
                        if line := await session.get_input("  new line> ", preserve_spaces=True):
                            art.insert(idx, line)
        elif cmd == 'p':
            # Plot/insert character at row,col
            if r_inp := await session.get_input("  row: "):
                if c_inp := await session.get_input("  col: "):
                    await session.send_line("  char: (type a key, or space for space)")
                    ch = await session.get_char("  ")
                    if ch == '\r':
                        ch = ' '  # enter = space
                    await session.send_line()
                    mode = await session.get_char("  [R]eplace or [I]nsert? ")
                    with suppress(ValueError, IndexError):
                        row = int(r_inp) - 1
                        col = int(c_inp) - 1 if c_inp.isdigit() else _parse_col(c_inp)
                        while len(art) <= row:
                            art.append("")
                        if len(art[row]) <= col:
                            art[row] = art[row].ljust(col + 1)
                        if mode.lower() == 'i':
                            art[row] = art[row][:col] + ch + art[row][col:]
                        else:
                            art[row] = art[row][:col] + ch + art[row][col + 1:]
        elif cmd == 'r':
            await session.send_line(color("  Enter all lines (blank to finish):", YELLOW))
            new_art = []
            while line := await session.get_input("  art> ", preserve_spaces=True):
                new_art.append(line)
            if new_art:
                art = new_art

    return art or None

async def gm_monster_editor(session, world):
    """Create, edit, and manage custom monsters."""
    while True:
        customs = load_custom_monsters()
        await session.send(CLEAR)
        await session.send_line(color("=== MONSTER EDITOR ===", MAGENTA))
        await session.send_line()
        await session.send_line(f"  {color('[N]', YELLOW)} New monster")
        await session.send_line(f"  {color('[E]', YELLOW)} Edit built-in monsters")
        if customs:
            await session.send_line(f"  {color('[L]', YELLOW)} List/edit custom ({len(customs)})")
            await session.send_line(f"  {color('[D]', YELLOW)} Delete a custom monster")
        await session.send_line(f"  {color('[S]', YELLOW)} Spawn monster here")
        await session.send_line(f"  {color('[B]', YELLOW)} Back")
        await session.send_line()

        ch = (await session.get_char("  > ")).upper()

        if ch == 'B':
            break

        elif ch == 'E':
            # Edit built-in monsters
            await session.send(CLEAR)
            await session.send_line(color("=== BUILT-IN MONSTERS ===", MAGENTA))
            await session.send_line()

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
                await session.send_line(f"  {color(f'[{i+1:2d}]', YELLOW)} F{fl+1} "
                                       f"{color(m['name'], WHITE):20s} HP={m['hp']:3d} ATK={m['atk']:2d} "
                                       f"DEF={m['def']:2d} XP={m['xp']:3d} G={m['gold']}")
                art = m.get('art') or default_arts.get(m['name'], ["  [?_?]"])
                for aline in art:
                    await session.send_line(color(f"       {aline}", RED))
            await session.send_line(f"\n  {color('[0]', YELLOW)} Back")
            if pick := await session.get_input("  Edit #: "):
                with suppress(ValueError, IndexError):
                    if 0 <= (idx := int(pick) - 1) < len(all_builtins):
                        fl, m = all_builtins[idx]
                        await session.send_line(color(f"\n  Editing {m['name']} (enter to keep current):", YELLOW))

                        new_name = await session.get_input(f"  Name [{m['name']}]: ")
                        if new_name.strip():
                            m['name'] = new_name.strip()
                        for field in ['hp', 'atk', 'def', 'xp', 'gold']:
                            val = await session.get_input(f"  {field.upper()} [{m[field]}]: ")
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
                        await session.send_line(color("  Current art:", DIM))
                        for aline in cur_art:
                            await session.send_line(color(f"    {aline}", RED))

                        edit_art = await session.get_input("  Edit art? (y/n): ")
                        if edit_art.lower() == 'y':
                            m['art'] = await edit_art_lines(session, cur_art)

                        save_builtin_overrides(MONSTERS_BY_FLOOR)
                        session.log(color(f"Updated {m['name']}! (saved)", GREEN))
            await session.get_char("  Press any key...")

        elif ch == 'N':
            await session.send(CLEAR)
            await session.send_line(color("=== CREATE MONSTER ===", MAGENTA))
            await session.send_line()
            name = await session.get_input("  Name: ")
            if not name.strip():
                continue
            name = name.strip()
            await session.send_line()
            try:
                hp = int(await session.get_input(f"  HP [{20}]: ") or "20")
                atk = int(await session.get_input(f"  ATK [{5}]: ") or "5")
                dfn = int(await session.get_input(f"  DEF [{2}]: ") or "2")
                xp = int(await session.get_input(f"  XP reward [{15}]: ") or "15")
                gold = int(await session.get_input(f"  Gold reward [{10}]: ") or "10")
                fl_input = await session.get_input("  Floor (-1=all): ")
                fl = int(fl_input) if fl_input.strip() else -1
            except ValueError:
                session.log(color("Invalid numbers!", RED))
                continue

            # ASCII art editor
            await session.send_line(color("\n  Now draw your monster:", YELLOW))
            art_lines = await edit_art_lines(session, )

            monster = {
                "name": name, "hp": hp, "atk": atk, "def": dfn,
                "xp": xp, "gold": gold, "floor": fl,
                "art": art_lines
            }
            customs.append(monster)
            save_custom_monsters(customs)

            # Preview
            await session.send_line()
            await session.send_line(color(f"  Created {name}!", GREEN))
            await session.send_line(f"  HP={hp} ATK={atk} DEF={dfn} XP={xp} Gold={gold} "
                                   f"Floor={'ALL' if fl==-1 else fl+1}")
            if art_lines:
                await session.send_line(color("  Art preview:", YELLOW))
                for aline in art_lines:
                    await session.send_line(color(f"        {aline}", RED))
            await session.get_char("  Press any key...")

        elif ch == 'L' and customs:
            await session.send(CLEAR)
            await session.send_line(color("=== CUSTOM MONSTERS ===", MAGENTA))
            await session.send_line()
            for i, m in enumerate(customs):
                fl_str = "ALL" if m.get('floor', -1) == -1 else f"F{m.get('floor', -1)+1}"
                await session.send_line(f"  {color(f'[{i+1}]', YELLOW)} {color(m['name'], WHITE)} "
                                       f"HP={m['hp']} ATK={m['atk']} DEF={m['def']} "
                                       f"XP={m['xp']} G={m['gold']} ({fl_str})")
                art = m.get('art', [])
                if art:
                    for aline in art:
                        await session.send_line(color(f"       {aline}", RED))
                else:
                    await session.send_line(color("       [no art]", DIM))
            await session.send_line()
            await session.send_line(f"  Pick a number to edit, or {color('[0]', YELLOW)} back")
            pick = await session.get_input("  > ")
            try:
                idx = int(pick) - 1
                if 0 <= idx < len(customs):
                    m = customs[idx]
                    await session.send_line(f"\n  Editing {m['name']} (enter to keep current):")
                    m['name'] = (await session.get_input(f"  Name [{m['name']}]: ")).strip() or m['name']
                    for field in ['hp', 'atk', 'def', 'xp', 'gold']:
                        val = await session.get_input(f"  {field.upper()} [{m[field]}]: ")
                        if val.strip():
                            m[field] = int(val)
                    fl_val = await session.get_input(f"  Floor [{m.get('floor', -1)}] (-1=all): ")
                    if fl_val.strip():
                        m['floor'] = int(fl_val)
                    # Edit art
                    edit_art = await session.get_input("  Edit art? (y/n): ")
                    if edit_art.lower() == 'y':
                        m['art'] = await edit_art_lines(session, m.get('art', []))
                    save_custom_monsters(customs)
                    session.log(color(f"Updated {m['name']}!", GREEN))
            except (ValueError, IndexError):
                pass
            await session.get_char("  Press any key...")

        elif ch == 'D' and customs:
            await session.send_line()
            for i, m in enumerate(customs):
                await session.send_line(f"  [{i+1}] {m['name']}")
            pick = await session.get_input("  Delete #: ")
            try:
                idx = int(pick) - 1
                if 0 <= idx < len(customs):
                    removed = customs.pop(idx)
                    save_custom_monsters(customs)
                    session.log(color(f"Deleted {removed['name']}!", RED))
            except (ValueError, IndexError):
                pass

        elif ch == 'S' and session.char:
            # Spawn any monster - requires a character (need position + floor)
            await session.send_line()
            all_spawnable = get_monsters_for_floor(session.char['floor'])
            all_spawnable = all_spawnable + customs
            for i, m in enumerate(all_spawnable):
                await session.send_line(f"  [{i+1}] {m['name']} HP={m['hp']} ATK={m['atk']}")
            pick = await session.get_input("  Spawn #: ")
            try:
                idx = int(pick) - 1
                if 0 <= idx < len(all_spawnable):
                    template = all_spawnable[idx]
                    mob = dict(template)
                    mob['max_hp'] = mob['hp']
                    mob['x'] = session.char['x']
                    mob['y'] = session.char['y']
                    mob['symbol'] = mob['name'][0].upper()
                    mob['alive'] = True
                    mob['respawn_timer'] = 0
                    floor_mobs = get_floor_monsters(session.char['floor'])
                    floor_mobs.append(mob)
                    session.log(color(f"Spawned {mob['name']} at [{mob['x']},{mob['y']}]!", GREEN))
            except (ValueError, IndexError):
                pass
        elif ch == 'S' and not session.char:
            await session.send_line(color("  Need a character to spawn monsters.", DIM))
            await session.get_char("  Press any key...")

async def gm_viewport_theme_editor(session, floor=0):
    """Edit the 3D viewport colors and textures for floors."""
    themes = load_scene_themes()
    floor_key = str(floor)

    # Current theme elements
    elements = ['wall', 'brick', 'side', 'frame', 'edge', 'ceil', 'floor']
    bg_elements = ['sky_bg', 'ground_bg', 'wall_bg', 'water_bg']

    # Load current overrides or defaults
    if floor_key not in themes:
        themes[floor_key] = {}

    while True:
        await session.send(CLEAR)
        await session.send_line(color(f"=== VIEWPORT THEME - Floor {floor+1 if floor >= 0 else 'Overworld'} "
                                     f"===", MAGENTA))
        await session.send_line()

        # Show color preview for each element
        await session.send_line(color("  Foreground colors:", WHITE))
        for i, elem in enumerate(elements):
            cur = themes[floor_key].get(elem, "default")
            code = COLOR_NAMES.get(cur, "37")
            preview = f"{CSI}{code}m{'###'}{RESET}"
            await session.send_line(f"  {color(f'[{i+1}]', YELLOW)} {elem:8s} = {preview} ({cur})")

        await session.send_line()
        await session.send_line(color("  Background colors:", WHITE))
        for i, elem in enumerate(bg_elements):
            cur = themes[floor_key].get(elem, "default")
            code = BG_COLOR_NAMES.get(cur, "")
            preview = f"{CSI}{code}m{'   '}{RESET}" if code else f"{DIM}none{RESET}"
            ltr = chr(ord('a') + i)
            await session.send_line(f"  {color(f'[{ltr}]', YELLOW)} {elem:10s} = {preview} ({cur})")

        await session.send_line()

        # Color palette reference
        await session.send_line(color("  Available colors:", DIM))
        palette = "  "
        for name, code in COLOR_NAMES.items():
            palette += f" {CSI}{code}m{name[:4]}{RESET}"
        await session.send_line(palette)

        await session.send_line()
        await session.send_line(
            f"  {color('[<]', CYAN)} Prev floor  {color('[>]', CYAN)} Next floor  "
            f"{color('[P]', YELLOW)} Preview  {color('[S]', YELLOW)} Save  "
            f"{color('[R]', YELLOW)} Reset  {color('[Q]', YELLOW)} Back"
        )

        cmd = (await session.get_char("  > ")).lower()

        if cmd == 'q':
            break

        elif cmd in ('<', ','):
            floor = max(-1, floor - 1)
            floor_key = str(floor)
            if floor_key not in themes:
                themes[floor_key] = {}
            continue

        elif cmd in ('>', '.'):
            floor = min(MAX_FLOOR, floor + 1)
            floor_key = str(floor)
            if floor_key not in themes:
                themes[floor_key] = {}
            continue

        elif cmd in '1234567':
            idx = int(cmd) - 1
            elem = elements[idx]
            await session.send_line()
            await session.send_line(f"  Colors: {', '.join(COLOR_NAMES.keys())}")
            val = await session.get_input(f"  {elem} color: ")
            if val.strip() in COLOR_NAMES:
                themes[floor_key][elem] = val.strip()

        elif cmd in 'abcd':
            idx = ord(cmd) - ord('a')
            elem = bg_elements[idx]
            await session.send_line()
            await session.send_line(f"  BG Colors: {', '.join(BG_COLOR_NAMES.keys())}")
            val = await session.get_input(f"  {elem} bg color: ")
            if val.strip() in BG_COLOR_NAMES:
                themes[floor_key][elem] = val.strip()

        elif cmd == 'p':
            # Preview - show a sample viewport render
            await session.send_line()
            # Apply current theme temporarily and render
            await session.send_line(color("  (Return to game to see full preview)", DIM))
            await session.get_char("  Press any key...")

        elif cmd == 's':
            save_scene_themes(themes)
            session.log(color("Theme saved!", GREEN))
            await session.send_line(color("\n  Theme saved to scene_themes.json!", GREEN))
            await session.get_char("  Press any key...")

        elif cmd == 'r':
            if floor_key in themes:
                del themes[floor_key]
            themes[floor_key] = {}
            save_scene_themes(themes)
            session.log(color("Theme reset to default!", YELLOW))

def _tile_render(t, is_ow_floor):
    """Render a single tile as colored character with background."""
    mapping = ({
        OW_GRASS:    f"{CSI}92;42m.{RESET}",
        OW_FOREST:   f"{CSI}97;42mT{RESET}",
        OW_MOUNTAIN: f"{CSI}97;100m^{RESET}",
        OW_WATER:    f"{CSI}97;44m~{RESET}",
        OW_ROAD:     f"{CSI}93;43m={RESET}",
        OW_TOWN:     f"{CSI}93;45m@{RESET}",
        OW_DUNGEON:  f"{CSI}97;41mD{RESET}",
    } if is_ow_floor else {
        0: f"{CSI}37m.{RESET}",
        1: f"{CSI}97;100m#{RESET}",
        2: f"{CSI}96;40m+{RESET}",
        3: f"{CSI}91;40m>{RESET}",
        4: f"{CSI}92;40m<{RESET}",
        5: f"{CSI}93;43m${RESET}",
        6: f"{CSI}96;44m~{RESET}",
    })
    return mapping.get(t, f"{CSI}90m?{RESET}")

async def gm_scene_editor(session, world, floor=0):
    """Full-screen visual tile editor with cursor."""
    dungeon = get_floor(floor)
    size = len(dungeon)
    if session.char:
        cx, cy = session.char['x'], session.char['y']
    else:
        cx, cy = size // 2, size // 2
    is_ow_floor = is_overworld(floor)

    tile_names = ({
        OW_GRASS: "Grass", OW_FOREST: "Forest", OW_MOUNTAIN: "Mount",
        OW_WATER: "Water", OW_ROAD: "Road", OW_TOWN: "Town",
        OW_DUNGEON: "Dung.E",
    } if is_ow_floor else {
        0: "Floor", 1: "Wall", 2: "Door", 3: "StairsD",
        4: "StairsU", 5: "Treas", 6: "Fount",
    })

    if is_ow_floor:
        brushes = [OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON]
    else:
        brushes = [0, 1, 2, 3, 4, 5, 6]

    brush_idx = 0
    painting = False
    needs_full_redraw = True

    tw, th = session.term_width, session.term_height
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
            await session.send(CLEAR)

            # Row 1: Header
            await session.move_to(1, 1)
            paint_str = color("PAINT ON", GREEN) if painting else color("paint off", DIM)
            cur_tile = dungeon[cy][cx] if 0 <= cy < size and 0 <= cx < size else -1
            await session.send(color(" SCENE EDITOR", MAGENTA) +
                f"  [{cx},{cy}] {tile_names.get(cur_tile, '?')}  " +
                f"Brush: {_tile_render(brush, is_ow_floor)} {tile_names.get(brush, '?')}  " +
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
                        row_str += _tile_render(dungeon[my][mx], is_ow_floor)
                    else:
                        row_str += f"{CSI}90m {RESET}"
                await session.move_to(2 + vr, 1)
                await session.send(row_str)

            # Brush palette row
            await session.move_to(th - 1, 1)
            palette = " "
            for i, b in enumerate(brushes):
                sel = f"{CSI}7m" if i == brush_idx else ""
                palette += f" {sel}{i+1}:{_tile_render(b, is_ow_floor)}{tile_names.get(b, '?')[:5]}{RESET}"
            await session.send(palette)

            # Help row
            await session.move_to(th, 1)
            await session.send(f" {color('WASD', YELLOW)}move {color('P', YELLOW)}aint "
                             f"{color('1-7', YELLOW)}brush {color('F', YELLOW)}ill "
                             f"{color('G', YELLOW)}rid {color('<>', CYAN)}floor "
                             f"{color('X', YELLOW)}save {color('Q', YELLOW)}uit")

            needs_full_redraw = False
        else:
            # Incremental: just update header, old cursor pos, new cursor pos
            # Header
            await session.move_to(1, 1)
            await session.send("\033[2K")
            cur_tile = dungeon[cy][cx] if 0 <= cy < size and 0 <= cx < size else -1
            paint_str = color("PAINT ON", GREEN) if painting else color("paint off", DIM)
            await session.send(color(" SCENE EDITOR", MAGENTA) +
                f"  [{cx},{cy}] {tile_names.get(cur_tile, '?')}  " +
                f"Brush: {_tile_render(brush, is_ow_floor)} {tile_names.get(brush, '?')}  " +
                paint_str)

        cmd = (await session.get_char("")).lower()

        old_cx, old_cy = cx, cy

        if cmd == 'q':
            break

        elif cmd in ('<', ','):
            # Previous floor
            floor = max(-1, floor - 1)
            dungeon = get_floor(floor)
            size = len(dungeon)
            is_ow_floor = is_overworld(floor)
            cx = min(cx, size - 1)
            cy = min(cy, size - 1)
            if is_ow_floor:
                brushes = [OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON]
                tile_names = {
                    OW_GRASS: "Grass", OW_FOREST: "Forest", OW_MOUNTAIN: "Mount",
                    OW_WATER: "Water", OW_ROAD: "Road", OW_TOWN: "Town",
                    OW_DUNGEON: "Dung.E",
                }
            else:
                brushes = [0, 1, 2, 3, 4, 5, 6]
                tile_names = {
                    0: "Floor", 1: "Wall", 2: "Door", 3: "StairsD",
                    4: "StairsU", 5: "Treas", 6: "Fount",
                }
            brush_idx = 0
            needs_full_redraw = True
            continue

        elif cmd in ('>', '.'):
            # Next floor
            floor = min(MAX_FLOOR, floor + 1)
            dungeon = get_floor(floor)
            size = len(dungeon)
            is_ow_floor = is_overworld(floor)
            cx = min(cx, size - 1)
            cy = min(cy, size - 1)
            if is_ow_floor:
                brushes = [OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON]
                tile_names = {
                    OW_GRASS: "Grass", OW_FOREST: "Forest", OW_MOUNTAIN: "Mount",
                    OW_WATER: "Water", OW_ROAD: "Road", OW_TOWN: "Town",
                    OW_DUNGEON: "Dung.E",
                }
            else:
                brushes = [0, 1, 2, 3, 4, 5, 6]
                tile_names = {
                    0: "Floor", 1: "Wall", 2: "Door", 3: "StairsD",
                    4: "StairsU", 5: "Treas", 6: "Fount",
                }
            brush_idx = 0
            needs_full_redraw = True
            continue

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
                    await session.move_to(scr_oy, scr_ox)
                    await session.send(_tile_render(dungeon[old_cy][old_cx], is_ow_floor))
                # Draw new cursor
                scr_nx = cx - cam_x + 1
                scr_ny = cy - cam_y + 2
                if 1 <= scr_nx <= map_cols and 2 <= scr_ny <= map_rows + 1:
                    await session.move_to(scr_ny, scr_nx)
                    await session.send(f"{CSI}30;107m@{RESET}")

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
            await session.move_to(1, 1)
            await session.send("\033[2K")
            if new_size_str := await session.get_input(f" New size (current {size}, max 256): "):
                with suppress(ValueError):
                    new_size = int(new_size_str)
                    new_size = max(8, min(256, new_size))
                    if new_size != size:
                        # Create new grid, copy old data
                        fill = brushes[0]  # fill new space with first brush tile
                        new_grid = [[fill for _ in range(new_size)] for _ in range(new_size)]
                        # Border with walls/water
                        border_tile = OW_WATER if is_ow_floor else 1
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
            needs_full_redraw = True

        elif cmd == 'x':
            if is_ow_floor:
                global _overworld
                _overworld = dungeon
                save_custom_floor(-1, dungeon)
            else:
                set_floor(floor, dungeon)
                save_custom_floor(floor, dungeon)
            # Flash save confirmation
            await session.move_to(1, tw - 10)
            await session.send(color(" SAVED! ", f"{CSI}30;102m"))
            await asyncio.sleep(0.5)
            needs_full_redraw = True

    if session.char:
        session.char['x'] = cx
        session.char['y'] = cy
        save_character(session.char)

