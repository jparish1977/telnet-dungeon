"""Dungeon floor generation, overworld generation, floor caching, and tile helpers."""

import math
import random

from dungeon.config import (
    OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
    OW_PASSABLE, OVERWORLD_FLOOR,
)
from dungeon.persistence import load_custom_floor

# ── Hand-built dungeon floors ─────────────────────────────────────
# 1=wall, 0=floor, 2=door, 3=stairs down, 4=stairs up, 5=treasure, 6=fountain
DUNGEON_FLOORS = [
    # Floor 0 - Entry level
    [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,4,0,0,1,0,0,0,1,0,0,0,0,0,0,1],
        [1,0,0,0,2,0,0,0,1,0,5,0,1,0,0,1],
        [1,0,0,0,1,0,0,0,2,0,0,0,1,0,0,1],
        [1,1,2,1,1,0,0,0,1,1,1,2,1,0,0,1],
        [1,0,0,0,1,0,6,0,1,0,0,0,0,0,0,1],
        [1,0,5,0,1,0,0,0,1,0,0,0,1,1,2,1],
        [1,0,0,0,2,0,0,0,0,0,0,0,1,0,0,1],
        [1,1,1,1,1,1,2,1,1,0,0,0,1,0,5,1],
        [1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,1],
        [1,0,0,0,0,5,0,0,2,0,0,0,1,1,1,1],
        [1,0,0,0,0,0,0,0,1,0,0,0,0,0,0,1],
        [1,1,1,1,1,1,1,1,1,0,0,0,1,1,2,1],
        [1,0,0,0,0,0,0,0,1,0,0,0,1,0,0,1],
        [1,0,0,3,0,0,0,0,2,0,0,0,1,0,5,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ],
    # Floor 1 - Deeper
    [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,4,0,0,0,0,1,0,0,0,1,0,0,0,0,1],
        [1,0,0,0,0,0,1,0,5,0,2,0,0,0,0,1],
        [1,0,0,0,0,0,2,0,0,0,1,0,0,0,0,1],
        [1,0,0,0,0,0,1,1,1,1,1,0,0,0,0,1],
        [1,1,1,2,1,1,1,0,0,0,1,1,1,2,1,1],
        [1,0,0,0,0,0,1,0,6,0,1,0,0,0,0,1],
        [1,0,5,0,0,0,2,0,0,0,2,0,0,5,0,1],
        [1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,1],
        [1,1,1,2,1,1,1,0,0,0,1,1,1,2,1,1],
        [1,0,0,0,0,0,1,1,2,1,1,0,0,0,0,1],
        [1,0,0,0,5,0,1,0,0,0,1,0,0,0,0,1],
        [1,0,0,0,0,0,2,0,0,0,2,0,0,5,0,1],
        [1,0,0,0,0,0,1,0,3,0,1,0,0,0,0,1],
        [1,0,0,0,0,0,1,0,0,0,1,0,0,0,0,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ],
    # Floor 2 - Boss level
    [
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
        [1,4,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        [1,0,0,0,0,1,0,5,0,0,1,0,0,0,0,1],
        [1,0,0,0,0,2,0,0,0,0,2,0,0,0,0,1],
        [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        [1,1,1,2,1,1,1,1,2,1,1,1,1,2,1,1],
        [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
        [1,0,0,0,0,0,0,6,0,0,0,0,0,0,0,1],
        [1,0,5,0,0,0,0,0,0,0,0,0,0,5,0,1],
        [1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,1],
        [1,1,1,2,1,1,1,1,2,1,1,1,1,2,1,1],
        [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        [1,0,5,0,0,2,0,3,0,0,2,0,0,5,0,1],
        [1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],
        [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],
    ],
]


# ── Procedural Dungeon Generator ──────────────────────────────────

def generate_floor(floor_num, size=16):
    """Generate a random dungeon floor using recursive division."""
    rng = random.Random(floor_num * 7919 + 1337)  # deterministic per floor

    grid = [[1 for _ in range(size)] for _ in range(size)]
    rooms = []

    def carve_room(x1, y1, x2, y2):
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                if 0 < x < size - 1 and 0 < y < size - 1:
                    grid[y][x] = 0
        rooms.append((x1, y1, x2, y2))

    def room_center(room):
        return ((room[0] + room[2]) // 2, (room[1] + room[3]) // 2)

    def carve_corridor(x1, y1, x2, y2):
        x, y = x1, y1
        while x != x2:
            if 0 < x < size - 1 and 0 < y < size - 1:
                grid[y][x] = 0
            x += 1 if x2 > x else -1
        while y != y2:
            if 0 < x < size - 1 and 0 < y < size - 1:
                grid[y][x] = 0
            y += 1 if y2 > y else -1
        if 0 < x2 < size - 1 and 0 < y2 < size - 1:
            grid[y2][x2] = 0

    base_rooms = max(5, size // 4)
    num_rooms = rng.randint(base_rooms, base_rooms + base_rooms // 2)
    num_rooms = min(num_rooms, 80)
    max_room = max(3, min(10, size // 6))
    min_room = max(2, max_room // 2)
    attempts = 0
    while len(rooms) < num_rooms and attempts < num_rooms * 15:
        attempts += 1
        rw = rng.randint(min_room, max_room)
        rh = rng.randint(min_room, max_room)
        rx = rng.randint(1, size - rw - 2)
        ry = rng.randint(1, size - rh - 2)
        overlap = False
        for r in rooms:
            if (rx - 1 <= r[2] and rx + rw + 1 >= r[0] and
                    ry - 1 <= r[3] and ry + rh + 1 >= r[1]):
                overlap = True
                break
        if not overlap:
            carve_room(rx, ry, rx + rw, ry + rh)

    for i in range(1, len(rooms)):
        cx1, cy1 = room_center(rooms[i - 1])
        cx2, cy2 = room_center(rooms[i])
        if rng.random() < 0.5:
            carve_corridor(cx1, cy1, cx2, cy2)
        else:
            carve_corridor(cx1, cy1, cx1, cy2)
            carve_corridor(cx1, cy2, cx2, cy2)

    extra_loops = max(1, len(rooms) // 4)
    for _ in range(rng.randint(1, extra_loops)):
        if len(rooms) >= 2:
            r1, r2 = rng.sample(rooms, 2)
            cx1, cy1 = room_center(r1)
            cx2, cy2 = room_center(r2)
            carve_corridor(cx1, cy1, cx2, cy2)

    for y in range(1, size - 1):
        for x in range(1, size - 1):
            if grid[y][x] == 0:
                h_walls = (grid[y][x-1] == 1 and grid[y][x+1] == 1)
                v_walls = (grid[y-1][x] == 1 and grid[y+1][x] == 1)
                if (h_walls or v_walls) and rng.random() < 0.3:
                    grid[y][x] = 2

    if rooms:
        cx, cy = room_center(rooms[0])
        grid[cy][cx] = 4

        best_room = rooms[-1]
        best_dist = 0
        up_cx, up_cy = cx, cy
        for r in rooms[1:]:
            rcx, rcy = room_center(r)
            dist = abs(rcx - up_cx) + abs(rcy - up_cy)
            if dist > best_dist:
                best_dist = dist
                best_room = r
        cx, cy = room_center(best_room)
        grid[cy][cx] = 3

    num_treasures = max(3, len(rooms) // 3)
    placed = 0
    shuffled_rooms = list(rooms[1:]) if len(rooms) > 2 else list(rooms)
    rng.shuffle(shuffled_rooms)
    for room in shuffled_rooms:
        if placed >= num_treasures:
            break
        tx = rng.randint(room[0], room[2])
        ty = rng.randint(room[1], room[3])
        if grid[ty][tx] == 0:
            grid[ty][tx] = 5
            placed += 1

    num_fountains = max(1, len(rooms) // 8)
    for _ in range(num_fountains):
        room = rng.choice(rooms)
        fx = rng.randint(room[0], room[2])
        fy = rng.randint(room[1], room[3])
        if grid[fy][fx] == 0:
            grid[fy][fx] = 6

    return grid


# ── Floor caching and access ──────────────────────────────────────

_generated_floors = {}


def get_floor_size(floor_num):
    """Floor size grows with depth. 16 -> 256 max."""
    if floor_num < len(DUNGEON_FLOORS):
        return 16
    size = 16 + floor_num * 8
    return min(256, max(16, size))


def get_floor(floor_num):
    """Get a dungeon floor - overworld for -1, hand-built for 0-2, procedural after.
    Custom floor edits override everything."""
    if floor_num == OVERWORLD_FLOOR:
        return get_overworld()
    if floor_num in _generated_floors:
        return _generated_floors[floor_num]
    custom = load_custom_floor(floor_num)
    if custom:
        _generated_floors[floor_num] = custom
        return custom
    if floor_num < len(DUNGEON_FLOORS):
        return DUNGEON_FLOORS[floor_num]
    size = get_floor_size(floor_num)
    _generated_floors[floor_num] = generate_floor(floor_num, size)
    return _generated_floors[floor_num]


def set_floor(floor_num, grid):
    """Set a floor in the cache (used by GM editor)."""
    _generated_floors[floor_num] = grid


def get_floor_spawn(floor_num):
    """Find stairs-up position on a floor for spawning."""
    floor = get_floor(floor_num)
    for y in range(len(floor)):
        for x in range(len(floor[0])):
            if floor[y][x] == 4:
                return x, y
    return find_open_tile(floor)


def find_open_tile(floor):
    """Find any walkable tile on a floor."""
    size = len(floor)
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            if floor[y][x] != 1:
                return x, y
    return 1, 1


def is_tile_blocked(tile, floor_num):
    """Check if a tile is impassable."""
    if tile == 1:
        return True
    if floor_num == OVERWORLD_FLOOR:
        return tile not in OW_PASSABLE
    return False


MAX_FLOOR = 99999


# ── Overworld ─────────────────────────────────────────────────────

_overworld = None
_overworld_size = 128


def get_overworld():
    global _overworld
    if _overworld is None:
        _overworld = generate_overworld(_overworld_size)
    return _overworld


def set_overworld(grid):
    """Replace the overworld (used by GM editor)."""
    global _overworld
    _overworld = grid


def generate_overworld(size=128):
    """Generate an overworld map with terrain using simplex-like noise."""
    rng = random.Random(42)
    grid = [[OW_GRASS for _ in range(size)] for _ in range(size)]

    def make_noise(seed, octaves=4):
        r = random.Random(seed)
        field = [[0.0 for _ in range(size)] for _ in range(size)]
        for octave in range(octaves):
            freq = 2 ** octave
            amp = 1.0 / (octave + 1)
            num_blobs = freq * freq * 2
            for _ in range(num_blobs):
                bx = r.randint(0, size - 1)
                by = r.randint(0, size - 1)
                radius = max(2, size // (freq * 2))
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        nx, ny = (bx + dx) % size, (by + dy) % size
                        dist = math.sqrt(dx*dx + dy*dy)
                        if dist < radius:
                            field[ny][nx] += amp * (1 - dist / radius)
        return field

    height = make_noise(1001)
    moisture = make_noise(2002)

    def normalize(field):
        flat = [v for row in field for v in row]
        lo, hi = min(flat), max(flat)
        rng_v = hi - lo if hi > lo else 1
        return [[((field[y][x] - lo) / rng_v) for x in range(size)] for y in range(size)]

    height = normalize(height)
    moisture = normalize(moisture)

    for y in range(size):
        for x in range(size):
            h = height[y][x]
            m = moisture[y][x]
            if h > 0.7:
                grid[y][x] = OW_MOUNTAIN
            elif h < 0.25:
                grid[y][x] = OW_WATER
            elif m > 0.6:
                grid[y][x] = OW_FOREST
            else:
                grid[y][x] = OW_GRASS

    def place_road(x1, y1, x2, y2):
        x, y = x1, y1
        while x != x2 or y != y2:
            if 0 <= x < size and 0 <= y < size and grid[y][x] != OW_WATER:
                grid[y][x] = OW_ROAD
            if rng.random() < 0.6:
                if x != x2:
                    x += 1 if x2 > x else -1
                elif y != y2:
                    y += 1 if y2 > y else -1
            else:
                if y != y2:
                    y += 1 if y2 > y else -1
                elif x != x2:
                    x += 1 if x2 > x else -1

    def place_town(tx, ty):
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = tx + dx, ty + dy
                if 1 <= nx < size - 1 and 1 <= ny < size - 1:
                    grid[ny][nx] = OW_GRASS
        grid[ty][tx] = OW_TOWN

    towns = []
    cx, cy = size // 2, size // 2
    place_town(cx, cy)
    towns.append((cx, cy))

    for _ in range(6):
        for attempt in range(50):
            tx = rng.randint(10, size - 10)
            ty = rng.randint(10, size - 10)
            too_close = any(abs(tx - ox) + abs(ty - oy) < 15 for ox, oy in towns)
            if not too_close:
                place_town(tx, ty)
                towns.append((tx, ty))
                break

    for i in range(1, len(towns)):
        place_road(towns[i-1][0], towns[i-1][1], towns[i][0], towns[i][1])
    if len(towns) > 2:
        place_road(towns[-1][0], towns[-1][1], towns[0][0], towns[0][1])

    dungeons_placed = 0
    for tx, ty in towns:
        for attempt in range(30):
            dx = tx + rng.randint(-8, 8)
            dy = ty + rng.randint(-8, 8)
            if 1 <= dx < size-1 and 1 <= dy < size-1:
                if grid[dy][dx] in (OW_GRASS, OW_FOREST):
                    grid[dy][dx] = OW_DUNGEON
                    dungeons_placed += 1
                    break

    for _ in range(3):
        for attempt in range(50):
            dx = rng.randint(5, size - 5)
            dy = rng.randint(5, size - 5)
            if grid[dy][dx] in (OW_GRASS, OW_FOREST):
                grid[dy][dx] = OW_DUNGEON
                break

    for i in range(size):
        grid[0][i] = OW_WATER
        grid[size-1][i] = OW_WATER
        grid[i][0] = OW_WATER
        grid[i][size-1] = OW_WATER

    return grid


def get_overworld_spawn():
    """Spawn at the center town."""
    ow = get_overworld()
    size = len(ow)
    cx, cy = size // 2, size // 2
    if ow[cy][cx] == OW_TOWN:
        return cx, cy
    for y in range(size):
        for x in range(size):
            if ow[y][x] == OW_TOWN:
                return x, y
    return size // 2, size // 2


def is_overworld(floor_num):
    return floor_num == OVERWORLD_FLOOR
