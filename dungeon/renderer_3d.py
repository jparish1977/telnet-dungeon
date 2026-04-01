"""Wizardry-style first-person 3D viewport renderer."""

from dungeon.config import (
    CSI, DIM, RESET, GREEN, YELLOW, CYAN,
    color, COLOR_NAMES, BG_COLOR_NAMES,
    OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
    OVERWORLD_FLOOR,
)
from dungeon.items import DIR_DX, DIR_DY
from dungeon.monsters import get_floor_monsters
from dungeon.persistence import load_scene_themes


def render_3d_view(dungeon, px, py, facing, vw=40, vh=15, floor_num=0, visible_mobs=None):
    """Render a Wizardry-style first-person wireframe view.
    visible_mobs is list of (x, y, symbol, name) for monsters on this floor."""
    lines = []
    W, H = vw, vh

    # Initialize viewport with spaces
    view = [[' ' for _ in range(W)] for _ in range(H)]
    mob_mask = [[False for _ in range(W)] for _ in range(H)]  # tracks monster pixels

    is_ow = (floor_num == OVERWORLD_FLOOR)

    def get_raw_tile(fx, fy):
        if 0 <= fy < len(dungeon) and 0 <= fx < len(dungeon[0]):
            return dungeon[fy][fx]
        return 1

    def get_tile(fx, fy):
        if 0 <= fy < len(dungeon) and 0 <= fx < len(dungeon[0]):
            raw = dungeon[fy][fx]
            # Map overworld tiles to dungeon equivalents for 3D rendering
            if is_ow:
                if raw == OW_MOUNTAIN:
                    return 1  # render as wall
                elif raw == OW_WATER:
                    return 1  # render as wall
                elif raw == OW_FOREST:
                    return 0  # passable, open
                elif raw == OW_TOWN:
                    return 4  # like stairs up (has shop)
                elif raw == OW_DUNGEON:
                    return 3  # like stairs down (enter dungeon)
                elif raw == OW_ROAD:
                    return 0  # open
                elif raw == OW_GRASS:
                    return 0  # open
                else:
                    return 0
            return raw
        return 1  # out of bounds = wall

    def ahead(dist):
        """Get position 'dist' steps ahead in facing direction."""
        ax = px + DIR_DX[facing] * dist
        ay = py + DIR_DY[facing] * dist
        return ax, ay

    def left_of(x, y):
        """Get position to the left of (x,y) relative to facing."""
        ldir = (facing - 1) % 4
        return x + DIR_DX[ldir], y + DIR_DY[ldir]

    def right_of(x, y):
        """Get position to the right of (x,y) relative to facing."""
        rdir = (facing + 1) % 4
        return x + DIR_DX[rdir], y + DIR_DY[rdir]

    # Depth layers - scaled proportionally to viewport size
    def make_depths(W, H):
        layers = []
        for i in range(4):
            # Each layer shrinks inward proportionally
            frac = i / 4.0
            lc = int(W * frac * 0.4)
            rc = W - 1 - int(W * frac * 0.4)
            tr = int(H * frac * 0.35)
            br = H - 1 - int(H * frac * 0.35)
            layers.append((lc, rc, tr, br))
        return layers

    depths = make_depths(W, H)

    # Wall texture patterns by depth (closer = more detail)
    BRICK_CHARS = [
        # depth 0 (closest) - detailed brick
        lambda r, c: '|' if c % 4 == 0 else ('-' if r % 3 == 0 else ('#' if (r + c) % 5 == 0 else ':')),
        # depth 1
        lambda r, c: '-' if r % 3 == 0 else ('#' if c % 3 == 0 else ':'),
        # depth 2
        lambda r, c: '#' if (r + c) % 2 == 0 else ':',
        # depth 3 (farthest) - dim
        lambda r, c: '.' if (r + c) % 2 == 0 else ' ',
    ]

    SIDE_WALL_CHARS = [
        # depth 0 - closest, most detail
        lambda r, c: '|' if c % 2 == 0 else (':' if r % 2 == 0 else '.'),
        # depth 1
        lambda r, c: ':' if (r + c) % 2 == 0 else '.',
        # depth 2
        lambda r, c: '.' if (r + c) % 3 == 0 else ' ',
        # depth 3
        lambda r, c: '.',
    ]

    def draw_hline(row, c1, c2, ch='#'):
        for c in range(c1, c2+1):
            if 0 <= row < H and 0 <= c < W:
                view[row][c] = ch

    def draw_vline(col, r1, r2, ch='#'):
        for r in range(r1, r2+1):
            if 0 <= r < H and 0 <= col < W:
                view[r][col] = ch

    def fill_rect(r1, c1, r2, c2, ch):
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                if 0 <= r < H and 0 <= c < W:
                    view[r][c] = ch

    def fill_brick(r1, c1, r2, c2, depth_idx):
        """Fill with textured brick pattern based on depth."""
        pat = BRICK_CHARS[min(depth_idx, len(BRICK_CHARS)-1)]
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                if 0 <= r < H and 0 <= c < W:
                    view[r][c] = pat(r, c)

    def fill_side(r1, c1, r2, c2, depth_idx):
        """Fill side walls with textured pattern."""
        pat = SIDE_WALL_CHARS[min(depth_idx, len(SIDE_WALL_CHARS)-1)]
        for r in range(r1, r2+1):
            for c in range(c1, c2+1):
                if 0 <= r < H and 0 <= c < W:
                    view[r][c] = pat(r, c)

    # Draw from far to near
    for depth in range(3, -1, -1):
        lc, rc, tr, br = depths[depth]

        fx, fy = ahead(depth)
        front_tile = get_tile(fx, fy)
        lx, ly = left_of(fx, fy)
        rx, ry = right_of(fx, fy)
        left_tile = get_tile(lx, ly)
        right_tile = get_tile(rx, ry)

        # Draw left wall
        if left_tile == 1:
            raw_l = get_raw_tile(lx, ly) if is_ow else 1
            for r in range(tr, br+1):
                if 0 <= r < H and 0 <= lc < W:
                    view[r][lc] = '|'
            prev_lc = depths[depth-1][0] if depth > 0 else 0
            if is_ow and raw_l == OW_MOUNTAIN:
                # Mountain side
                for r in range(tr, br+1):
                    for c in range(prev_lc, lc):
                        if 0 <= r < H and 0 <= c < W:
                            view[r][c] = '^' if (r+c) % 3 == 0 else 'n'
            elif is_ow and raw_l == OW_WATER:
                for r in range(tr, br+1):
                    for c in range(prev_lc, lc):
                        if 0 <= r < H and 0 <= c < W:
                            view[r][c] = '~' if (r+c) % 2 == 0 else '-'
            else:
                fill_side(tr, prev_lc, br, lc-1, depth)
        elif left_tile == 2:  # door
            for r in range(tr, br+1):
                if 0 <= r < H and 0 <= lc < W:
                    view[r][lc] = '|'
            mid_r = (tr + br) // 2
            if 0 <= mid_r < H and 0 <= lc < W:
                view[mid_r][lc] = '+'

        # Draw right wall
        if right_tile == 1:
            raw_r = get_raw_tile(rx, ry) if is_ow else 1
            for r in range(tr, br+1):
                if 0 <= r < H and 0 <= rc < W:
                    view[r][rc] = '|'
            prev_rc = depths[depth-1][1] if depth > 0 else W-1
            if is_ow and raw_r == OW_MOUNTAIN:
                for r in range(tr, br+1):
                    for c in range(rc+1, prev_rc+1):
                        if 0 <= r < H and 0 <= c < W:
                            view[r][c] = '^' if (r+c) % 3 == 0 else 'n'
            elif is_ow and raw_r == OW_WATER:
                for r in range(tr, br+1):
                    for c in range(rc+1, prev_rc+1):
                        if 0 <= r < H and 0 <= c < W:
                            view[r][c] = '~' if (r+c) % 2 == 0 else '-'
            else:
                fill_side(tr, rc+1, br, prev_rc, depth)
        elif right_tile == 2:
            for r in range(tr, br+1):
                if 0 <= r < H and 0 <= rc < W:
                    view[r][rc] = '|'
            mid_r = (tr + br) // 2
            if 0 <= mid_r < H and 0 <= rc < W:
                view[mid_r][rc] = '+'

        # Draw front wall if blocked
        if front_tile == 1:
            raw = get_raw_tile(fx, fy) if is_ow else 1
            if is_ow and raw == OW_MOUNTAIN:
                # Mountain art
                mid_c = (lc + rc) // 2
                peak_r = tr + 1
                base_r = br
                # Draw mountain triangle
                for r in range(peak_r, base_r + 1):
                    progress = (r - peak_r) / max(1, base_r - peak_r)
                    half_w = int(progress * (rc - lc) // 2)
                    for c in range(mid_c - half_w, mid_c + half_w + 1):
                        if 0 <= r < H and 0 <= c < W:
                            if r == peak_r:
                                view[r][c] = 'A'
                            elif abs(c - mid_c) >= half_w - 1:
                                view[r][c] = '/'  if c < mid_c else '\\'
                            elif r < peak_r + 2:
                                view[r][c] = '*'  # snow cap
                            else:
                                view[r][c] = '^' if (r + c) % 3 == 0 else 'n'
            elif is_ow and raw == OW_WATER:
                # Water art
                for r in range(tr, br + 1):
                    for c in range(lc, rc + 1):
                        if 0 <= r < H and 0 <= c < W:
                            if (r + c) % 3 == 0:
                                view[r][c] = '~'
                            elif (r + c) % 3 == 1:
                                view[r][c] = '-'
                            else:
                                view[r][c] = '~'
            else:
                # Standard dungeon wall
                draw_hline(tr, lc, rc, '=')
                draw_hline(br, lc, rc, '=')
                draw_vline(lc, tr, br, '|')
                draw_vline(rc, tr, br, '|')
                fill_brick(tr+1, lc+1, br-1, rc-1, depth)
                if 0 <= tr < H and 0 <= lc < W:
                    view[tr][lc] = '+'
                if 0 <= tr < H and 0 <= rc < W:
                    view[tr][rc] = '+'
                if 0 <= br < H and 0 <= lc < W:
                    view[br][lc] = '+'
                if 0 <= br < H and 0 <= rc < W:
                    view[br][rc] = '+'
            break  # Can't see past a wall

        elif front_tile == 2:  # Door ahead
            draw_hline(tr, lc, rc, '=')
            draw_hline(br, lc, rc, '=')
            draw_vline(lc, tr, br, '|')
            draw_vline(rc, tr, br, '|')
            # Door frame
            door_l = lc + (rc - lc) // 3
            door_r = rc - (rc - lc) // 3
            door_t = tr + 2 if tr + 2 < br else tr + 1
            fill_rect(door_t, door_l, br, door_r, ' ')
            draw_vline(door_l, door_t, br, '[')
            draw_vline(door_r, door_t, br, ']')
            draw_hline(door_t, door_l, door_r, '-')
            # Door handle
            mid_r = (door_t + br) // 2
            if 0 <= mid_r < H and door_r - 1 >= 0 and door_r - 1 < W:
                view[mid_r][door_r - 1] = 'o'
            break

        elif front_tile in (3, 4):  # Stairs
            mid_c = (lc + rc) // 2
            mid_r = (tr + br) // 2
            avail = rc - lc  # width available

            if front_tile == 3:  # Stairs down
                if avail >= 16 and depth <= 1:
                    sprite = [
                        "  STAIRS DOWN  ",
                        " _____________ ",
                        " |  _______  | ",
                        " | |  ___  | | ",
                        " | | |   | | | ",
                        " | | | v | | | ",
                        " | | |___| | | ",
                        " | |_______| | ",
                        " |___________| ",
                    ]
                elif avail >= 8:
                    sprite = [
                        " _DOWN_ ",
                        "| ___  |",
                        "||   | |",
                        "|| v | |",
                        "||___| |",
                        "|______|",
                    ]
                else:
                    sprite = [" v ", "DOWN"]
            else:  # Stairs up + shop
                if avail >= 18 and depth <= 1:
                    sprite = [
                        "  STAIRS UP    ",
                        " _____________ ",
                        " |  _______  | ",
                        " | |  ___  | | ",
                        " | | | ^ | | | ",
                        " | | |___| | | ",
                        " | |_______| | ",
                        " |___________| ",
                        "  [H] = SHOP   ",
                    ]
                elif avail >= 8:
                    sprite = [
                        "  _UP_  ",
                        "| ___  |",
                        "|| ^ | |",
                        "||___| |",
                        "|______|",
                        " [SHOP] ",
                    ]
                else:
                    sprite = [" ^ ", " UP"]

            start_r = mid_r - len(sprite) // 2
            for si, sline in enumerate(sprite):
                sr = start_r + si
                sc = mid_c - len(sline) // 2
                for ci, ch in enumerate(sline):
                    cc = sc + ci
                    if 0 <= sr < H and 0 <= cc < W and ch != ' ':
                        view[sr][cc] = ch

        elif front_tile == 5:  # Treasure
            mid_c = (lc + rc) // 2
            mid_r = (tr + br) // 2
            avail = rc - lc

            if avail >= 14 and depth <= 1:
                sprite = [
                    "    ________    ",
                    "   /  $$$   \\   ",
                    "  / $ $$$ $  \\  ",
                    " /____________\\ ",
                    " |  TREASURE  | ",
                    " |   $$$$$    | ",
                    " |  $$ $$ $$  | ",
                    " |____________| ",
                ]
            elif avail >= 8:
                sprite = [
                    "  ____  ",
                    " / $$ \\ ",
                    "/______\\",
                    "|$$$$$$|",
                    "|______|",
                ]
            else:
                sprite = ["[$$$]"]

            start_r = mid_r - len(sprite) // 2 + 1
            for si, sline in enumerate(sprite):
                sr = start_r + si
                sc = mid_c - len(sline) // 2
                for ci, ch in enumerate(sline):
                    cc = sc + ci
                    if 0 <= sr < H and 0 <= cc < W and ch != ' ':
                        view[sr][cc] = ch

        elif front_tile == 6:  # Fountain
            mid_c = (lc + rc) // 2
            mid_r = (tr + br) // 2
            avail = rc - lc

            if avail >= 14 and depth <= 1:
                sprite = [
                    "      |       ",
                    "     ~~~      ",
                    "    ~~~~~     ",
                    "   ~~~~~~~    ",
                    "  \\  ~~~  /   ",
                    "   \\     /    ",
                    "    \\   /     ",
                    "   __\\_/___   ",
                    "  |  [R]  |   ",
                    "  |_______|   ",
                ]
            elif avail >= 8:
                sprite = [
                    "   |   ",
                    "  ~~~  ",
                    " ~~~~~ ",
                    "  \\ /  ",
                    " __V__ ",
                    "| [R] |",
                    "|_____|",
                ]
            else:
                sprite = [" ~ ", "{~}"]

            start_r = mid_r - len(sprite) // 2 + 1
            for si, sline in enumerate(sprite):
                sr = start_r + si
                sc = mid_c - len(sline) // 2
                for ci, ch in enumerate(sline):
                    cc = sc + ci
                    if 0 <= sr < H and 0 <= cc < W and ch != ' ':
                        view[sr][cc] = ch

    # Draw visible monsters in the 3D view (only if line of sight is clear)
    if visible_mobs:
        # Build lookup of mob positions
        mob_at = {}
        for mx, my, msym, mname in visible_mobs:
            mob_at[(mx, my)] = (msym, mname)

        # First, figure out max visible depth by walking forward until hitting a wall
        max_visible_depth = 0
        for d in range(4):
            fx, fy = ahead(d)
            tile = get_tile(fx, fy)
            if tile == 1:
                break  # wall blocks further view
            max_visible_depth = d
            if tile == 2:
                break  # door also blocks (can see the door tile but not past it)

        # Now draw monsters only at visible depths (near to far so near draws on top)
        for depth in range(max_visible_depth, -1, -1):
            lc_d, rc_d, tr_d, br_d = depths[depth]
            fx, fy = ahead(depth)

            # Check center, left, and right at this depth
            positions_to_check = [
                (fx, fy, 0),  # center
            ]
            lx, ly = left_of(fx, fy)
            rx, ry = right_of(fx, fy)
            positions_to_check.append((lx, ly, -1))  # left
            positions_to_check.append((rx, ry, 1))   # right

            for mx, my, side in positions_to_check:
                if (mx, my) in mob_at:
                    msym, mname = mob_at[(mx, my)]
                    # Don't draw on walls
                    if get_tile(mx, my) == 1:
                        continue

                    mid_c = (lc_d + rc_d) // 2
                    mid_r = (tr_d + br_d) // 2

                    # Offset for left/right
                    if side == -1:
                        mid_c = lc_d + (rc_d - lc_d) // 4
                    elif side == 1:
                        mid_c = rc_d - (rc_d - lc_d) // 4

                    # Get monster's actual art
                    default_arts = {
                        "Giant Rat":    ["  (\\_/)", "  (o.o)", "  (> <)"],
                        "Kobold":       ["  /\\_/\\", " ( o.o)", "  > ^ <"],
                        "Skeleton":     ["   _||_", "  /o  o\\", "  |_/\\_|", "   /||\\"],
                        "Giant Spider": [" /\\(oo)/\\", "//\\\\||//\\\\"],
                        "Zombie":       ["  [x_x]", "  /|  |\\", "  / \\/ \\"],
                        "Demon Lord":   [" _/\\_/\\_", "( O  O )", " \\    /", "  \\||/"],
                    }
                    # Check if mob has custom art (from visible_mobs we have name)
                    # Look up art from floor monsters
                    mob_art = None
                    for fm in get_floor_monsters(floor_num):
                        if fm['alive'] and fm['x'] == mx and fm['y'] == my:
                            mob_art = fm.get('art')
                            break
                    if not mob_art:
                        mob_art = default_arts.get(mname)
                    if not mob_art:
                        # Generic silhouettes - pick based on name hash for consistency
                        generic_arts = [
                            [" /\\_/\\ ", "( x.x )", " > ~ < ", "  / \\  "],
                            ["  _/|_ ", " /o  o\\", " | -- |", "  /||\\"],
                            ["  .--.  ", " (o  o) ", " /|  |\\ ", " / \\/ \\"],
                            ["  {__} ", " |o  o|", " | \\/ |", "  \\  / ", "   ||  "],
                            ["  /vv\\ ", " | ** |", " |    |", "  \\||/ "],
                        ]
                        mob_art = generic_arts[hash(mname) % len(generic_arts)]

                    # Scale art based on depth
                    if depth <= 1:
                        # Close - use full art
                        sprite = mob_art
                    elif depth == 2:
                        # Medium - use first 3 lines, truncated
                        sprite = [line[:8] for line in mob_art[:3]]
                    else:
                        # Far - just the symbol
                        sprite = [
                            f"\\{msym}/",
                            " | ",
                        ]

                    # Draw sprite centered at mid_c, mid_r
                    start_r = mid_r - len(sprite) // 2 + 1
                    for si, sline in enumerate(sprite):
                        sr = start_r + si
                        sc = mid_c - len(sline) // 2
                        for ci, ch in enumerate(sline):
                            cc = sc + ci
                            if 0 <= sr < H and 0 <= cc < W and ch != ' ':
                                view[sr][cc] = ch
                                mob_mask[sr][cc] = True

                    # Label below sprite
                    if depth <= 2:
                        label = mname[:rc_d - lc_d - 2] if depth <= 1 else msym
                        lr = start_r + len(sprite)
                        lc_start = mid_c - len(label) // 2
                        for li, lch in enumerate(label):
                            lcc = lc_start + li
                            if 0 <= lr < H and 0 <= lcc < W:
                                view[lr][lcc] = lch
                                mob_mask[lr][lcc] = True

    # Fill all empty space with sky/ceiling above horizon, ground below
    horizon = H // 2

    if is_ow:
        for r in range(H):
            for c in range(W):
                if view[r][c] == ' ':
                    if r < horizon:
                        # Sky
                        if c % 11 == 0 and r > 1:
                            view[r][c] = '.'  # cloud
                        else:
                            view[r][c] = '`'
                    elif r == horizon:
                        view[r][c] = '_'  # horizon
                    else:
                        # Ground - perspective: denser detail closer
                        dist = r - horizon
                        spacing = max(2, 7 - dist)
                        if c % spacing == 0:
                            view[r][c] = ';'  # grass tuft
                        elif (r + c) % 4 == 0:
                            view[r][c] = ','
                        else:
                            view[r][c] = '.'
    else:
        for r in range(H):
            for c in range(W):
                if view[r][c] == ' ':
                    if r < horizon:
                        # Ceiling
                        if r == 0:
                            view[r][c] = '~' if c % 3 != 0 else '-'
                        elif (r + c) % 7 == 0:
                            view[r][c] = '.'  # drip
                        else:
                            view[r][c] = '`'  # dark ceiling
                    elif r == horizon:
                        view[r][c] = '_'
                    else:
                        # Floor - perspective
                        dist = r - horizon
                        spacing = max(2, 6 - dist)
                        if c % spacing == 0:
                            view[r][c] = ':'
                        elif (r + c) % 5 == 0:
                            view[r][c] = ','
                        else:
                            view[r][c] = '.'

    # Build output with per-floor color themes
    # Floor 0: gray stone, Floor 1: brown/dark, Floor 2: red/hellish
    FLOOR_COLORS = [
        # Floor 0 - cool stone dungeon
        {"wall": f"{CSI}37m", "brick": f"{CSI}90m", "side": f"{CSI}90m",
         "frame": f"{CSI}36m", "edge": f"{CSI}37m", "ceil": f"{CSI}90m", "floor": f"{CSI}33m"},
        # Floor 1 - deep earth, warmer tones
        {"wall": f"{CSI}33m", "brick": f"{CSI}90m", "side": f"{CSI}31m",
         "frame": f"{CSI}33m", "edge": f"{CSI}93m", "ceil": f"{CSI}90m", "floor": f"{CSI}33m"},
        # Floor 2 - hellish reds
        {"wall": f"{CSI}91m", "brick": f"{CSI}31m", "side": f"{CSI}31m",
         "frame": f"{CSI}91m", "edge": f"{CSI}93m", "ceil": f"{CSI}31m", "floor": f"{CSI}91m"},
        # Floor 3 - frozen caverns (blue/cyan)
        {"wall": f"{CSI}96m", "brick": f"{CSI}36m", "side": f"{CSI}34m",
         "frame": f"{CSI}96m", "edge": f"{CSI}97m", "ceil": f"{CSI}34m", "floor": f"{CSI}36m"},
        # Floor 4 - poisoned depths (green)
        {"wall": f"{CSI}32m", "brick": f"{CSI}92m", "side": f"{CSI}32m",
         "frame": f"{CSI}92m", "edge": f"{CSI}32m", "ceil": f"{CSI}90m", "floor": f"{CSI}32m"},
        # Floor 5 - shadow realm (magenta/dark)
        {"wall": f"{CSI}35m", "brick": f"{CSI}90m", "side": f"{CSI}35m",
         "frame": f"{CSI}95m", "edge": f"{CSI}35m", "ceil": f"{CSI}90m", "floor": f"{CSI}35m"},
        # Floor 6+ - the void (cycles)
        {"wall": f"{CSI}97m", "brick": f"{CSI}90m", "side": f"{CSI}37m",
         "frame": f"{CSI}97m", "edge": f"{CSI}93m", "ceil": f"{CSI}90m", "floor": f"{CSI}90m"},
    ]
    if floor_num == OVERWORLD_FLOOR:
        fc = {"wall": f"{CSI}32m", "brick": f"{CSI}92m", "side": f"{CSI}32m",
              "frame": f"{CSI}92m", "edge": f"{CSI}32m", "ceil": f"{CSI}96m", "floor": f"{CSI}33m"}
    else:
        fc = dict(FLOOR_COLORS[min(floor_num, len(FLOOR_COLORS) - 1)])

    # Apply saved theme overrides
    saved_themes = load_scene_themes()
    theme_key = str(floor_num)
    theme_data = saved_themes.get(theme_key, {})
    for elem in ['wall', 'brick', 'side', 'frame', 'edge', 'ceil', 'floor']:
        if elem in theme_data:
            cname = theme_data[elem]
            if cname in COLOR_NAMES:
                fc[elem] = f"{CSI}{COLOR_NAMES[cname]}m"

    # Background color codes
    BG_BLACK   = f"{CSI}40m"
    BG_RED     = f"{CSI}41m"
    BG_GREEN   = f"{CSI}42m"
    BG_YELLOW  = f"{CSI}43m"
    BG_BLUE    = f"{CSI}44m"
    BG_CYAN    = f"{CSI}46m"
    BG_DKGRAY  = f"{CSI}100m"

    # Apply custom background overrides
    def get_theme_bg(key, default):
        cname = theme_data.get(key, "")
        if cname and cname in BG_COLOR_NAMES and BG_COLOR_NAMES[cname]:
            return f"{CSI}{BG_COLOR_NAMES[cname]}m"
        return default

    theme_sky_bg = get_theme_bg('sky_bg', BG_BLUE if is_ow else BG_BLACK)
    theme_ground_bg = get_theme_bg('ground_bg', BG_GREEN if is_ow else BG_DKGRAY)
    theme_wall_bg = get_theme_bg('wall_bg', BG_DKGRAY)
    theme_water_bg = get_theme_bg('water_bg', BG_BLUE)

    border = color('+' + '-' * W + '+', DIM)
    lines.append(border)
    for ri, row in enumerate(view):
        colored_row = ""
        # Determine background zone
        above_horizon = ri < horizon
        at_horizon = ri == horizon

        for ci, ch in enumerate(row):
            # Monster pixels get special treatment - red fg on dark red bg
            if mob_mask[ri][ci]:
                colored_row += f"{CSI}97;41m{ch}{RESET}"
                continue
            bg = ""
            fg = ""

            # Set background based on zone and content (uses theme overrides)
            if is_ow:
                if ch in ('`', '.') and above_horizon:
                    bg = theme_sky_bg
                elif ch == '_' and at_horizon:
                    bg = theme_ground_bg
                elif ch in (';', ',', '.') and not above_horizon:
                    bg = theme_ground_bg
                elif ch == '~':
                    bg = theme_water_bg
                elif ch in ('^', 'n'):
                    bg = theme_wall_bg
                elif ch == '*':
                    bg = f"{CSI}47m"  # snow = white bg
            else:
                if ch in ('`', '.') and above_horizon:
                    bg = theme_sky_bg
                elif ch in ('.', ',') and not above_horizon:
                    bg = theme_ground_bg
                elif ch == ':' and not above_horizon:
                    bg = theme_wall_bg
                elif ch == '#':
                    bg = theme_wall_bg
                elif ch == '~':
                    bg = theme_water_bg

            # Foreground colors
            if ch == '|':
                fg = fc["frame"]
            elif ch == '+':
                fg = fc["frame"]
            elif ch in ('[', ']'):
                fg = YELLOW
                bg = BG_DKGRAY
            elif ch == '=':
                fg = fc["edge"]
            elif ch == '-':
                fg = fc["wall"]
            elif ch == '#':
                fg = fc["brick"]
            elif ch == ':':
                fg = fc["side"]
            elif ch == '.':
                fg = fc["floor"] if not above_horizon else (f"{CSI}97m" if is_ow else f"{CSI}90m")
            elif ch == ',':
                fg = f"{CSI}33m"
            elif ch == '~':
                fg = f"{CSI}97m" if is_ow else CYAN
                bg = BG_BLUE
            elif ch == '$':
                fg = f"{CSI}93m"
                bg = BG_YELLOW
            elif ch == 'o':
                fg = f"{CSI}93m"
            elif ch in ('^', 'v', 'V'):
                fg = GREEN
            elif ch in ('S','T','A','I','R','D','O','W','N','U','P','H','E'):
                fg = GREEN
            elif ch in ('{', '}'):
                fg = CYAN
                bg = BG_CYAN
            elif ch == 'x':
                fg = f"{CSI}91m"  # bright red monster eyes
                bg = BG_RED
            elif ch == '`':
                fg = f"{CSI}34m" if is_ow else f"{CSI}90m"
            elif ch == '*':
                fg = f"{CSI}97m"
            elif ch == 'n':
                fg = f"{CSI}37m"
            elif ch == ';':
                fg = f"{CSI}92m"
            elif ch == '_':
                fg = f"{CSI}93m"
            elif ch == '\\' or ch == '/':
                fg = f"{CSI}37m"
            elif ch == ' ':
                # Give empty space a background
                if above_horizon:
                    bg = theme_sky_bg
                else:
                    bg = theme_ground_bg
                colored_row += f"{bg} {RESET}" if bg else ch
                continue
            else:
                fg = fc["wall"]

            colored_row += f"{fg}{bg}{ch}{RESET}"
        lines.append(color('|', DIM) + colored_row + color('|', DIM))
    lines.append(border)

    return '\n'.join(lines)
