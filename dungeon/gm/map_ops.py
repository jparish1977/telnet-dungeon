"""Map operations — export, look, and bulk editing for GM and agent use.

All functions are pure game-logic: no I/O, no ANSI, no session dependency.
They operate on floor grids (2D lists of ints) and return data structures.
The GM menu and agent adapter both call into these.
"""

from dungeon.config import (
    OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
    OVERWORLD_FLOOR,
)
from dungeon.floor import get_floor, set_floor, is_overworld
from dungeon.monsters import get_floor_monsters
from dungeon.items import DIR_NAMES, DIR_DX, DIR_DY
from dungeon.persistence import save_custom_floor


# ── Tile legends ──────────────────────────────────────────────────

DUNGEON_TILE_CHARS = {
    0: '.', 1: '#', 2: 'D', 3: '>', 4: '<', 5: 'C', 6: 'F', 7: '#',
}
DUNGEON_TILE_NAMES = {
    0: 'floor', 1: 'wall', 2: 'door', 3: 'stairs_down', 4: 'stairs_up',
    5: 'chest', 6: 'fountain', 7: 'secret_wall',
}

OW_TILE_CHARS = {
    OW_GRASS: '.', OW_FOREST: 'T', OW_MOUNTAIN: '^',
    OW_WATER: '~', OW_ROAD: '=', OW_TOWN: '@', OW_DUNGEON: 'D',
}
OW_TILE_NAMES = {
    OW_GRASS: 'grass', OW_FOREST: 'forest', OW_MOUNTAIN: 'mountain',
    OW_WATER: 'water', OW_ROAD: 'road', OW_TOWN: 'town',
    OW_DUNGEON: 'dungeon_entrance',
}


def _tile_char(tile, is_ow):
    """Single ASCII char for a tile code."""
    chars = OW_TILE_CHARS if is_ow else DUNGEON_TILE_CHARS
    return chars.get(tile, '?')


def _tile_name(tile, is_ow):
    """Human-readable name for a tile code."""
    names = OW_TILE_NAMES if is_ow else DUNGEON_TILE_NAMES
    return names.get(tile, 'unknown')


# ── Map Export ────────────────────────────────────────────────────

def export_map_ascii(floor_num):
    """Export a floor as ASCII text. Returns (header, grid_lines, legend)."""
    grid = get_floor(floor_num)
    is_ow = is_overworld(floor_num)
    size = len(grid)

    label = "Overworld" if is_ow else f"Floor {floor_num}"
    header = f"{label} ({size}x{size})"

    lines = []
    for row in grid:
        lines.append(''.join(_tile_char(t, is_ow) for t in row))

    chars = OW_TILE_CHARS if is_ow else DUNGEON_TILE_CHARS
    names = OW_TILE_NAMES if is_ow else DUNGEON_TILE_NAMES
    legend = {ch: names[code] for code, ch in chars.items()}

    return header, lines, legend


def export_map_json(floor_num):
    """Export a floor as a JSON-serializable dict."""
    grid = get_floor(floor_num)
    is_ow = is_overworld(floor_num)
    size = len(grid)
    header, ascii_lines, legend = export_map_ascii(floor_num)
    return {
        'floor': floor_num,
        'size': size,
        'is_overworld': is_ow,
        'header': header,
        'ascii': ascii_lines,
        'legend': legend,
        'grid': [list(row) for row in grid],
    }


# ── Look ──────────────────────────────────────────────────────────

def look(floor_num, x, y, facing, radius=10):
    """Describe surroundings as structured data.

    Returns a dict with position, visible tiles, nearby features,
    monsters, and directional info — everything an LLM needs to
    understand the player's situation.
    """
    grid = get_floor(floor_num)
    is_ow = is_overworld(floor_num)
    size = len(grid)

    # Tile under feet
    current = grid[y][x] if 0 <= y < size and 0 <= x < size else -1

    # What's in each direction (from facing)
    directions = {}
    for turn, label in [(0, 'ahead'), (1, 'right'), (2, 'behind'), (3, 'left')]:
        d = (facing + turn) % 4
        dx, dy = DIR_DX[d], DIR_DY[d]
        # Walk until blocked or radius
        dist = 0
        tiles_seen = []
        cx, cy = x, y
        for step in range(1, radius + 1):
            cx, cy = x + dx * step, y + dy * step
            if not (0 <= cx < size and 0 <= cy < size):
                tiles_seen.append({'dist': step, 'tile': 'edge'})
                break
            t = grid[cy][cx]
            name = _tile_name(t, is_ow)
            if t == 1 or (is_ow and t in (OW_MOUNTAIN, OW_WATER)):
                tiles_seen.append({'dist': step, 'tile': name, 'blocked': True})
                dist = step
                break
            if name != ('floor' if not is_ow else 'grass'):
                tiles_seen.append({'dist': step, 'tile': name})
            dist = step
        directions[label] = {
            'compass': DIR_NAMES[d],
            'open_tiles': dist,
            'features': tiles_seen,
        }

    # Nearby features (scan radius)
    features = []
    for sy in range(max(0, y - radius), min(size, y + radius + 1)):
        for sx in range(max(0, x - radius), min(size, x + radius + 1)):
            if sx == x and sy == y:
                continue
            t = grid[sy][sx]
            name = _tile_name(t, is_ow)
            if name in ('floor', 'wall', 'grass', 'forest'):
                continue  # skip boring tiles
            features.append({
                'x': sx, 'y': sy,
                'tile': name,
                'dist': abs(sx - x) + abs(sy - y),
            })
    features.sort(key=lambda f: f['dist'])

    # Monsters
    monsters = []
    for mob in get_floor_monsters(floor_num):
        if not mob.get('alive', True):
            continue
        mx, my = mob.get('x', -1), mob.get('y', -1)
        if abs(mx - x) <= radius and abs(my - y) <= radius:
            monsters.append({
                'name': mob['name'],
                'x': mx, 'y': my,
                'hp': mob['hp'],
                'dist': abs(mx - x) + abs(my - y),
            })
    monsters.sort(key=lambda m: m['dist'])

    return {
        'floor': floor_num,
        'x': x, 'y': y,
        'facing': DIR_NAMES[facing],
        'current_tile': _tile_name(current, is_ow),
        'is_overworld': is_ow,
        'directions': directions,
        'nearby_features': features[:20],  # cap for LLM context
        'monsters': monsters,
    }


def look_text(floor_num, x, y, facing, radius=10):
    """Human-readable text version of look()."""
    data = look(floor_num, x, y, facing, radius)
    is_ow = data['is_overworld']
    label = "Overworld" if is_ow else f"Floor {floor_num}"

    lines = [f"{label}, position ({x},{y}), facing {data['facing']}."]
    lines.append(f"Standing on: {data['current_tile']}.")

    for direction, info in data['directions'].items():
        feat_str = ""
        if info['features']:
            parts = []
            for f in info['features']:
                s = f"{f['tile']} at {f['dist']}"
                if f.get('blocked'):
                    s += " (blocked)"
                parts.append(s)
            feat_str = " — " + ", ".join(parts)
        lines.append(f"  {direction.capitalize()} ({info['compass']}): {info['open_tiles']} tiles open{feat_str}")

    if data['nearby_features']:
        lines.append("Nearby features:")
        for f in data['nearby_features'][:10]:
            lines.append(f"  {f['tile']} at ({f['x']},{f['y']}) dist={f['dist']}")

    if data['monsters']:
        lines.append("Monsters:")
        for m in data['monsters']:
            lines.append(f"  {m['name']} at ({m['x']},{m['y']}) HP={m['hp']} dist={m['dist']}")

    return "\n".join(lines)


# ── Bulk Map Operations ───────────────────────────────────────────

def set_tile(grid, x, y, tile):
    """Set a single tile with bounds checking. Returns True if set."""
    size = len(grid)
    if 0 <= x < size and 0 <= y < size:
        grid[y][x] = tile
        return True
    return False


def set_tile_range(grid, x1, y1, x2, y2, tile):
    """Fill a rectangular region with a tile. Returns count of tiles set."""
    size = len(grid)
    count = 0
    for y in range(max(0, min(y1, y2)), min(size, max(y1, y2) + 1)):
        for x in range(max(0, min(x1, x2)), min(size, max(x1, x2) + 1)):
            grid[y][x] = tile
            count += 1
    return count


def place_room(grid, x, y, w, h, door_side=None):
    """Place a rectangular room: walls around the edge, floor inside.

    door_side: 'north', 'south', 'east', 'west', or None (no door).
    Returns True if placed, False if out of bounds.
    """
    size = len(grid)
    x2, y2 = x + w - 1, y + h - 1
    if x < 0 or y < 0 or x2 >= size or y2 >= size:
        return False

    # Walls
    for cx in range(x, x2 + 1):
        grid[y][cx] = 1
        grid[y2][cx] = 1
    for cy in range(y, y2 + 1):
        grid[cy][x] = 1
        grid[cy][x2] = 1

    # Floor inside
    for cy in range(y + 1, y2):
        for cx in range(x + 1, x2):
            grid[cy][cx] = 0

    # Door
    if door_side:
        mid_x = (x + x2) // 2
        mid_y = (y + y2) // 2
        door_positions = {
            'north': (mid_x, y),
            'south': (mid_x, y2),
            'west':  (x, mid_y),
            'east':  (x2, mid_y),
        }
        pos = door_positions.get(door_side)
        if pos:
            grid[pos[1]][pos[0]] = 2

    return True


def carve_corridor(grid, x1, y1, x2, y2, tile=0):
    """Carve a corridor (L-shaped) between two points. Returns tile count."""
    size = len(grid)
    count = 0
    x, y = x1, y1

    # Horizontal first
    while x != x2:
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = tile
            count += 1
        x += 1 if x2 > x else -1
    # Then vertical
    while y != y2:
        if 0 <= x < size and 0 <= y < size:
            grid[y][x] = tile
            count += 1
        y += 1 if y2 > y else -1
    # Final tile
    if 0 <= x2 < size and 0 <= y2 < size:
        grid[y2][x2] = tile
        count += 1

    return count


def flood_fill(grid, x, y, new_tile, max_tiles=5000):
    """Flood fill from (x,y) replacing the existing tile. Returns count."""
    size = len(grid)
    if not (0 <= x < size and 0 <= y < size):
        return 0
    target = grid[y][x]
    if target == new_tile:
        return 0

    stack = [(x, y)]
    visited = set()
    count = 0
    while stack and count < max_tiles:
        fx, fy = stack.pop()
        if (fx, fy) in visited:
            continue
        if not (0 <= fx < size and 0 <= fy < size):
            continue
        if grid[fy][fx] != target:
            continue
        visited.add((fx, fy))
        grid[fy][fx] = new_tile
        count += 1
        stack.extend([(fx+1, fy), (fx-1, fy), (fx, fy+1), (fx, fy-1)])
    return count


def apply_ops(floor_num, ops):
    """Apply a list of operations to a floor. Each op is a dict.

    Supported ops:
        {"action": "set_tile", "x": 5, "y": 3, "tile": 1}
        {"action": "set_range", "x1": 0, "y1": 0, "x2": 5, "y2": 5, "tile": 1}
        {"action": "place_room", "x": 10, "y": 10, "w": 4, "h": 4, "door_side": "north"}
        {"action": "carve_corridor", "x1": 5, "y1": 5, "x2": 10, "y2": 5}
        {"action": "flood_fill", "x": 5, "y": 5, "tile": 0}

    Returns a summary dict with counts and any errors.
    """
    grid = get_floor(floor_num)
    results = {'applied': 0, 'errors': []}

    for i, op in enumerate(ops):
        action = op.get('action', '')
        try:
            if action == 'set_tile':
                if set_tile(grid, op['x'], op['y'], op['tile']):
                    results['applied'] += 1
                else:
                    results['errors'].append(f"op {i}: out of bounds")

            elif action == 'set_range':
                count = set_tile_range(grid, op['x1'], op['y1'], op['x2'], op['y2'], op['tile'])
                results['applied'] += 1

            elif action == 'place_room':
                ok = place_room(grid, op['x'], op['y'], op['w'], op['h'],
                                op.get('door_side'))
                if ok:
                    results['applied'] += 1
                else:
                    results['errors'].append(f"op {i}: room out of bounds")

            elif action == 'carve_corridor':
                carve_corridor(grid, op['x1'], op['y1'], op['x2'], op['y2'],
                               op.get('tile', 0))
                results['applied'] += 1

            elif action == 'flood_fill':
                flood_fill(grid, op['x'], op['y'], op['tile'])
                results['applied'] += 1

            else:
                results['errors'].append(f"op {i}: unknown action '{action}'")

        except (KeyError, TypeError) as e:
            results['errors'].append(f"op {i}: {e}")

    # Update the floor cache
    set_floor(floor_num, grid)
    return results


def save_floor(floor_num):
    """Persist current floor state to custom_floors/."""
    grid = get_floor(floor_num)
    save_custom_floor(floor_num, grid)
