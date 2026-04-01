#!/usr/bin/env python3
"""
Telnet Dungeon Crawler - Wizardry-style BBS game
Run: python dungeon_server.py [port]
Connect: telnet localhost 2323
"""

import asyncio
import sys
import random
import json
import os
import math

# ── Telnet protocol bytes ──────────────────────────────────────────
IAC  = bytes([255])
WILL = bytes([251])
WONT = bytes([252])
DO   = bytes([253])
DONT = bytes([254])
SB   = bytes([250])
SE   = bytes([240])
ECHO = bytes([1])
SGA  = bytes([3])  # Suppress Go Ahead
NAWS = bytes([31]) # Window size
LINEMODE = bytes([34])

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 2323

# ── ANSI helpers ───────────────────────────────────────────────────
CSI = "\033["
CLEAR = f"{CSI}2J{CSI}H"
BOLD = f"{CSI}1m"
DIM = f"{CSI}2m"
RESET = f"{CSI}0m"
RED = f"{CSI}31m"
GREEN = f"{CSI}32m"
YELLOW = f"{CSI}33m"
CYAN = f"{CSI}36m"
WHITE = f"{CSI}37m"
MAGENTA = f"{CSI}35m"

def color(text, c):
    return f"{c}{text}{RESET}"

# ── Overworld Tiles ───────────────────────────────────────────────
# 10=grass, 11=forest, 12=mountain, 13=water, 14=road, 15=town, 16=dungeon entrance
OW_GRASS = 10
OW_FOREST = 11
OW_MOUNTAIN = 12
OW_WATER = 13
OW_ROAD = 14
OW_TOWN = 15
OW_DUNGEON = 16
OW_PASSABLE = {OW_GRASS, OW_FOREST, OW_ROAD, OW_TOWN, OW_DUNGEON}
OVERWORLD_FLOOR = -1

# ── Dungeon Map ────────────────────────────────────────────────────
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

# ── Monster definitions ───────────────────────────────────────────
MONSTERS_BY_FLOOR = {
    0: [
        {"name": "Giant Rat",      "hp": 8,  "atk": 3,  "def": 1, "xp": 10, "gold": 5},
        {"name": "Kobold",         "hp": 12, "atk": 5,  "def": 2, "xp": 15, "gold": 8},
        {"name": "Skeleton",       "hp": 15, "atk": 6,  "def": 3, "xp": 20, "gold": 12},
        {"name": "Giant Spider",   "hp": 10, "atk": 7,  "def": 1, "xp": 18, "gold": 6},
        {"name": "Zombie",         "hp": 20, "atk": 4,  "def": 2, "xp": 22, "gold": 10},
    ],
    1: [
        {"name": "Orc Warrior",    "hp": 25, "atk": 9,  "def": 4, "xp": 35, "gold": 20},
        {"name": "Dark Elf",       "hp": 20, "atk": 11, "def": 3, "xp": 40, "gold": 25},
        {"name": "Ghoul",          "hp": 30, "atk": 8,  "def": 5, "xp": 38, "gold": 18},
        {"name": "Stone Golem",    "hp": 40, "atk": 7,  "def": 8, "xp": 45, "gold": 30},
        {"name": "Wraith",         "hp": 22, "atk": 12, "def": 2, "xp": 42, "gold": 22},
    ],
    2: [
        {"name": "Minotaur",       "hp": 45, "atk": 14, "def": 6, "xp": 60, "gold": 40},
        {"name": "Lich",           "hp": 35, "atk": 18, "def": 5, "xp": 70, "gold": 50},
        {"name": "Dragon Whelp",   "hp": 55, "atk": 15, "def": 8, "xp": 80, "gold": 60},
        {"name": "Death Knight",   "hp": 50, "atk": 16, "def": 7, "xp": 75, "gold": 55},
        {"name": "Demon Lord",     "hp": 80, "atk": 20, "def": 10, "xp": 150, "gold": 100},
    ],
}

# ── Procedural Dungeon Generator ───────────────────────────────────
def generate_floor(floor_num, size=16):
    """Generate a random dungeon floor using recursive division."""
    rng = random.Random(floor_num * 7919 + 1337)  # deterministic per floor

    # Start with all walls
    grid = [[1 for _ in range(size)] for _ in range(size)]

    # Carve rooms using BSP-like approach
    rooms = []

    def carve_room(x1, y1, x2, y2):
        """Carve a rectangular room."""
        for y in range(y1, y2 + 1):
            for x in range(x1, x2 + 1):
                if 0 < x < size - 1 and 0 < y < size - 1:
                    grid[y][x] = 0
        rooms.append((x1, y1, x2, y2))

    def room_center(room):
        return ((room[0] + room[2]) // 2, (room[1] + room[3]) // 2)

    def carve_corridor(x1, y1, x2, y2):
        """Carve an L-shaped corridor between two points."""
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

    # Scale rooms to map size - bigger maps get more and bigger rooms
    base_rooms = max(5, size // 4)
    num_rooms = rng.randint(base_rooms, base_rooms + base_rooms // 2)
    num_rooms = min(num_rooms, 80)  # cap for sanity
    max_room = max(3, min(10, size // 6))  # room size scales with map
    min_room = max(2, max_room // 2)
    attempts = 0
    while len(rooms) < num_rooms and attempts < num_rooms * 15:
        attempts += 1
        rw = rng.randint(min_room, max_room)
        rh = rng.randint(min_room, max_room)
        rx = rng.randint(1, size - rw - 2)
        ry = rng.randint(1, size - rh - 2)
        # Check overlap
        overlap = False
        for r in rooms:
            if (rx - 1 <= r[2] and rx + rw + 1 >= r[0] and
                    ry - 1 <= r[3] and ry + rh + 1 >= r[1]):
                overlap = True
                break
        if not overlap:
            carve_room(rx, ry, rx + rw, ry + rh)

    # Connect rooms with corridors
    for i in range(1, len(rooms)):
        cx1, cy1 = room_center(rooms[i - 1])
        cx2, cy2 = room_center(rooms[i])
        if rng.random() < 0.5:
            carve_corridor(cx1, cy1, cx2, cy2)
        else:
            carve_corridor(cx1, cy1, cx1, cy2)
            carve_corridor(cx1, cy2, cx2, cy2)

    # Add extra connections for loops - more on bigger maps
    extra_loops = max(1, len(rooms) // 4)
    for _ in range(rng.randint(1, extra_loops)):
        if len(rooms) >= 2:
            r1, r2 = rng.sample(rooms, 2)
            cx1, cy1 = room_center(r1)
            cx2, cy2 = room_center(r2)
            carve_corridor(cx1, cy1, cx2, cy2)

    # Place doors at corridor-room transitions
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            if grid[y][x] == 0:
                h_walls = (grid[y][x-1] == 1 and grid[y][x+1] == 1)
                v_walls = (grid[y-1][x] == 1 and grid[y+1][x] == 1)
                if (h_walls or v_walls) and rng.random() < 0.3:
                    grid[y][x] = 2

    # Place stairs up in first room
    if rooms:
        cx, cy = room_center(rooms[0])
        grid[cy][cx] = 4

        # Place stairs down in the room farthest from stairs up
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

    # Place treasures - scales with map size
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

    # Place fountains - scales with map size
    num_fountains = max(1, len(rooms) // 8)
    for _ in range(num_fountains):
        room = rng.choice(rooms)
        fx = rng.randint(room[0], room[2])
        fy = rng.randint(room[1], room[3])
        if grid[fy][fx] == 0:
            grid[fy][fx] = 6

    return grid


# Cache generated floors so they stay consistent
_generated_floors = {}

def get_floor_size(floor_num):
    """Floor size grows with depth. 16 -> 256 max."""
    if floor_num < len(DUNGEON_FLOORS):
        return 16  # hand-built floors are 16x16
    # Grow: 20, 24, 32, 40, 48, 64, 80, 96, 128, 160, 192, 224, 256...
    size = 16 + floor_num * 8
    return min(256, max(16, size))

def get_floor(floor_num):
    """Get a dungeon floor - overworld for -1, hand-built for 0-2, procedural after.
    Custom floor edits override everything."""
    if floor_num == OVERWORLD_FLOOR:
        return get_overworld()
    # Check cache first (includes live edits)
    if floor_num in _generated_floors:
        return _generated_floors[floor_num]
    # Check for saved custom floor
    custom = load_custom_floor(floor_num)
    if custom:
        _generated_floors[floor_num] = custom
        return custom
    if floor_num < len(DUNGEON_FLOORS):
        return DUNGEON_FLOORS[floor_num]
    size = get_floor_size(floor_num)
    _generated_floors[floor_num] = generate_floor(floor_num, size)
    return _generated_floors[floor_num]


def get_floor_spawn(floor_num):
    """Find stairs-up position on a floor for spawning."""
    floor = get_floor(floor_num)
    for y in range(len(floor)):
        for x in range(len(floor[0])):
            if floor[y][x] == 4:
                return x, y
    # Fallback: find any open tile
    return find_open_tile(floor)


def find_open_tile(floor):
    """Find any walkable tile on a floor."""
    size = len(floor)
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            if floor[y][x] != 1:
                return x, y
    return 1, 1  # absolute last resort


MAX_FLOOR = 99999  # deepest allowed floor

def sanitize_character(char):
    """Clamp all character values to sane ranges. Prevents save file tampering."""
    char['floor'] = max(OVERWORLD_FLOOR, min(MAX_FLOOR, int(char.get('floor', 0))))
    char['level'] = max(1, min(9999, int(char.get('level', 1))))
    char['hp'] = int(char.get('hp', 1))
    char['max_hp'] = max(1, min(99999, int(char.get('max_hp', 30))))
    char['hp'] = max(-1, min(char['max_hp'], char['hp']))
    char['mp'] = max(0, min(99999, int(char.get('mp', 0))))
    char['max_mp'] = max(0, min(99999, int(char.get('max_mp', 0))))
    char['base_atk'] = max(0, min(9999, int(char.get('base_atk', 5))))
    char['base_def'] = max(0, min(9999, int(char.get('base_def', 5))))
    char['spd'] = max(0, min(9999, int(char.get('spd', 4))))
    char['gold'] = max(0, min(9999999, int(char.get('gold', 0))))
    char['potions'] = max(0, min(999, int(char.get('potions', 0))))
    char['weapon'] = max(0, min(len(WEAPONS) - 1, int(char.get('weapon', 0))))
    char['armor'] = max(0, min(len(ARMOR) - 1, int(char.get('armor', 0))))
    char['xp'] = max(0, min(9999999, int(char.get('xp', 0))))
    char['xp_next'] = max(10, min(9999999, int(char.get('xp_next', 100))))
    char['kills'] = max(0, int(char.get('kills', 0)))
    char['x'] = max(0, min(255, int(char.get('x', 1))))
    char['y'] = max(0, min(255, int(char.get('y', 1))))
    char['facing'] = max(0, min(3, int(char.get('facing', 0))))


def is_tile_blocked(tile, floor_num):
    """Check if a tile is impassable."""
    if tile == 1:
        return True  # dungeon wall
    if floor_num == OVERWORLD_FLOOR:
        return tile not in OW_PASSABLE
    return False


def validate_position(char):
    """Make sure a character isn't stuck in a wall/water/mountain. Fix if so."""
    sanitize_character(char)
    floor_num = char['floor']
    floor = get_floor(floor_num)
    size = len(floor)
    x, y = char['x'], char['y']
    # Out of bounds or inside impassable tile
    if x < 0 or y < 0 or x >= size or y >= size or is_tile_blocked(floor[y][x], floor_num):
        if floor_num == OVERWORLD_FLOOR:
            sx, sy = get_overworld_spawn()
        else:
            sx, sy = get_floor_spawn(floor_num)
        char['x'] = sx
        char['y'] = sy
        save_character(char)
        return True  # was fixed
    return False


# ── Monster scaling for deep floors ──────────────────────────────
def get_monsters_for_floor(floor_num):
    """Get monster list for a floor, scaling stats for deep floors. Includes custom monsters."""
    customs = load_custom_monsters()
    # Filter custom monsters for this floor (floor=-1 means all floors)
    floor_customs = [m for m in customs if m.get('floor', -1) in (-1, floor_num)]

    if floor_num in MONSTERS_BY_FLOOR:
        return MONSTERS_BY_FLOOR[floor_num] + floor_customs
    if floor_customs:
        pass  # will be added below
    # Scale from floor 2 monsters with multiplier
    base = MONSTERS_BY_FLOOR[2]
    scale = 1 + (floor_num - 2) * 0.4
    scaled = []
    for m in base:
        sm = dict(m)
        sm['hp'] = int(m['hp'] * scale)
        sm['atk'] = int(m['atk'] * scale)
        sm['def'] = int(m['def'] * scale)
        sm['xp'] = int(m['xp'] * scale)
        sm['gold'] = int(m['gold'] * scale)
        # Rename for deep floors
        depth_prefix = ["Ancient ", "Elder ", "Abyssal ", "Void ", "Eternal "]
        prefix = depth_prefix[min((floor_num - 3) // 2, len(depth_prefix) - 1)]
        sm['name'] = prefix + m['name']
        scaled.append(sm)
    return scaled + floor_customs


# ── Overworld Generation ──────────────────────────────────────────
_overworld = None
_overworld_size = 128

def get_overworld():
    global _overworld
    if _overworld is None:
        _overworld = generate_overworld(_overworld_size)
    return _overworld

def generate_overworld(size=128):
    """Generate an overworld map with terrain using simplex-like noise."""
    rng = random.Random(42)  # deterministic
    grid = [[OW_GRASS for _ in range(size)] for _ in range(size)]

    # Simple noise: generate height and moisture maps using layered random blobs
    def make_noise(seed, octaves=4):
        r = random.Random(seed)
        field = [[0.0 for _ in range(size)] for _ in range(size)]
        for octave in range(octaves):
            freq = 2 ** octave
            amp = 1.0 / (octave + 1)
            # Place random blobs
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

    # Normalize
    def normalize(field):
        flat = [v for row in field for v in row]
        lo, hi = min(flat), max(flat)
        rng_v = hi - lo if hi > lo else 1
        return [[((field[y][x] - lo) / rng_v) for x in range(size)] for y in range(size)]

    height = normalize(height)
    moisture = normalize(moisture)

    # Assign terrain based on height and moisture
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

    # Place roads connecting key points
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

    # Place towns - carve a clearing around each one
    def place_town(tx, ty):
        """Place a town and clear the area around it to grass."""
        # Clear a 5x5 area to grass
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = tx + dx, ty + dy
                if 1 <= nx < size - 1 and 1 <= ny < size - 1:
                    grid[ny][nx] = OW_GRASS
        grid[ty][tx] = OW_TOWN

    towns = []
    # Starting town near center
    cx, cy = size // 2, size // 2
    place_town(cx, cy)
    towns.append((cx, cy))

    # More towns scattered around
    for _ in range(6):
        for attempt in range(50):
            tx = rng.randint(10, size - 10)
            ty = rng.randint(10, size - 10)
            # Not too close to other towns
            too_close = any(abs(tx - ox) + abs(ty - oy) < 15 for ox, oy in towns)
            if not too_close:
                place_town(tx, ty)
                towns.append((tx, ty))
                break

    # Connect towns with roads
    for i in range(1, len(towns)):
        place_road(towns[i-1][0], towns[i-1][1], towns[i][0], towns[i][1])
    # Connect last to first for a loop
    if len(towns) > 2:
        place_road(towns[-1][0], towns[-1][1], towns[0][0], towns[0][1])

    # Place dungeon entrances near (but not in) towns
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

    # A few extra remote dungeons
    for _ in range(3):
        for attempt in range(50):
            dx = rng.randint(5, size - 5)
            dy = rng.randint(5, size - 5)
            if grid[dy][dx] in (OW_GRASS, OW_FOREST):
                grid[dy][dx] = OW_DUNGEON
                break

    # Border with water
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
    # Find center town
    cx, cy = size // 2, size // 2
    if ow[cy][cx] == OW_TOWN:
        return cx, cy
    # Fallback: find any town
    for y in range(size):
        for x in range(size):
            if ow[y][x] == OW_TOWN:
                return x, y
    return size // 2, size // 2


def is_overworld(floor_num):
    return floor_num == OVERWORLD_FLOOR


# ── Floor Monsters (visible wandering mobs) ───────────────────────
_floor_monsters = {}  # floor_num -> list of monster dicts with x, y

def get_floor_monsters(floor_num):
    """Get or spawn monsters for a floor."""
    if floor_num not in _floor_monsters:
        spawn_floor_monsters(floor_num)
    return _floor_monsters[floor_num]


def spawn_floor_monsters(floor_num):
    """Populate a floor with wandering monsters."""
    floor = get_floor(floor_num)
    size = len(floor)
    templates = get_monsters_for_floor(floor_num)
    rng = random.Random(floor_num * 4201 + 777)

    # Number of monsters scales with floor size
    num_mobs = max(3, size // 4)
    num_mobs = min(num_mobs, 40)

    monsters = []
    for _ in range(num_mobs):
        # Find a random open tile
        for attempt in range(50):
            mx = rng.randint(1, size - 2)
            my = rng.randint(1, size - 2)
            if floor[my][mx] == 0:
                template = rng.choice(templates)
                mob = dict(template)
                mob['max_hp'] = mob['hp']
                mob['x'] = mx
                mob['y'] = my
                mob['symbol'] = mob['name'][0].upper()
                mob['alive'] = True
                mob['respawn_timer'] = 0
                monsters.append(mob)
                break

    _floor_monsters[floor_num] = monsters


def move_floor_monsters(floor_num, player_positions):
    """Move monsters around. Called each game tick.
    player_positions is list of (x, y) for players on this floor."""
    floor = get_floor(floor_num)
    size = len(floor)
    monsters = get_floor_monsters(floor_num)

    for mob in monsters:
        if not mob['alive']:
            mob['respawn_timer'] -= 1
            if mob['respawn_timer'] <= 0:
                # Respawn at a random open tile
                for _ in range(30):
                    rx = random.randint(1, size - 2)
                    ry = random.randint(1, size - 2)
                    if floor[ry][rx] == 0:
                        # Don't spawn on top of a player
                        if not any(px == rx and py == ry for px, py in player_positions):
                            templates = get_monsters_for_floor(floor_num)
                            template = random.choice(templates)
                            mob.update(template)
                            mob['max_hp'] = mob['hp']
                            mob['x'] = rx
                            mob['y'] = ry
                            mob['symbol'] = mob['name'][0].upper()
                            mob['alive'] = True
                            break
            continue

        # Wander or pursue
        # Check if any player is nearby (within 5 tiles) - aggro
        nearest_dist = 999
        nearest_px, nearest_py = mob['x'], mob['y']
        for px, py in player_positions:
            dist = abs(px - mob['x']) + abs(py - mob['y'])
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_px, nearest_py = px, py

        if nearest_dist <= 5 and random.random() < 0.6:
            # Move toward nearest player
            dx = 0
            dy = 0
            if nearest_px > mob['x']: dx = 1
            elif nearest_px < mob['x']: dx = -1
            if nearest_py > mob['y']: dy = 1
            elif nearest_py < mob['y']: dy = -1
            # Pick one axis to move on
            if random.random() < 0.5:
                nx, ny = mob['x'] + dx, mob['y']
            else:
                nx, ny = mob['x'], mob['y'] + dy
        elif random.random() < 0.3:
            # Random wander
            direction = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            nx, ny = mob['x'] + direction[0], mob['y'] + direction[1]
        else:
            continue  # stay put this tick

        # Check if target tile is walkable
        if 0 < nx < size - 1 and 0 < ny < size - 1:
            tile = floor[ny][nx]
            if tile != 1:  # not a wall
                # Don't stack on other monsters
                occupied = any(m['x'] == nx and m['y'] == ny and m['alive'] and m is not mob
                              for m in monsters)
                if not occupied:
                    mob['x'] = nx
                    mob['y'] = ny


def get_monster_at(floor_num, x, y):
    """Get the first alive monster at a position, or None."""
    for mob in get_floor_monsters(floor_num):
        if mob['alive'] and mob['x'] == x and mob['y'] == y:
            return mob
    return None


def kill_monster(mob):
    """Mark a monster as dead and start respawn timer."""
    mob['alive'] = False
    mob['respawn_timer'] = random.randint(15, 30)  # respawn after 15-30 player moves


# ── Items / Spells ─────────────────────────────────────────────────
WEAPONS = [
    {"name": "Rusty Dagger",   "atk": 2,  "price": 0},
    {"name": "Short Sword",    "atk": 5,  "price": 50},
    {"name": "Longsword",      "atk": 8,  "price": 150},
    {"name": "Battle Axe",     "atk": 11, "price": 300},
    {"name": "Flaming Sword",  "atk": 15, "price": 600},
    {"name": "Vorpal Blade",   "atk": 20, "price": 1200},
]

ARMOR = [
    {"name": "Cloth Rags",     "def": 1,  "price": 0},
    {"name": "Leather Armor",  "def": 3,  "price": 40},
    {"name": "Chain Mail",     "def": 6,  "price": 120},
    {"name": "Plate Armor",    "def": 9,  "price": 350},
    {"name": "Mithril Plate",  "def": 13, "price": 800},
    {"name": "Dragon Scale",   "def": 18, "price": 1500},
]

SPELLS = {
    "HEAL":   {"cost": 3, "desc": "Restore 15-25 HP",     "min_level": 1},
    "FIREBALL":{"cost": 5, "desc": "Deal 12-20 fire dmg", "min_level": 2},
    "SHIELD": {"cost": 4, "desc": "+5 DEF for combat",    "min_level": 3},
    "LIGHTNING":{"cost": 7,"desc": "Deal 20-35 dmg",      "min_level": 4},
    "CURE":   {"cost": 6, "desc": "Remove poison",        "min_level": 2},
}

# ── Character classes ──────────────────────────────────────────────
CLASSES = {
    "FIGHTER": {"hp": 30, "mp": 0,  "atk": 8, "def": 6, "spd": 4, "desc": "Strong melee, high HP, no magic"},
    "MAGE":    {"hp": 16, "mp": 20, "atk": 3, "def": 3, "spd": 5, "desc": "Powerful spells, fragile body"},
    "THIEF":   {"hp": 22, "mp": 5,  "atk": 6, "def": 4, "spd": 8, "desc": "Fast, finds traps & treasure"},
    "CLERIC":  {"hp": 24, "mp": 15, "atk": 5, "def": 5, "spd": 4, "desc": "Healing magic, decent combat"},
}

# ── Directions ─────────────────────────────────────────────────────
NORTH, EAST, SOUTH, WEST = 0, 1, 2, 3
DIR_NAMES = ["North", "East", "South", "West"]
DIR_DX = [0, 1, 0, -1]  # column delta
DIR_DY = [-1, 0, 1, 0]  # row delta

# ── Save/Load ──────────────────────────────────────────────────────
SAVE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")
os.makedirs(SAVE_DIR, exist_ok=True)

def save_character(char):
    path = os.path.join(SAVE_DIR, f"{char['name'].lower()}.json")
    with open(path, 'w') as f:
        json.dump(char, f, indent=2)

def load_character(name):
    path = os.path.join(SAVE_DIR, f"{name.lower()}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def list_saves():
    saves = []
    for fn in os.listdir(SAVE_DIR):
        if fn.endswith('.json'):
            saves.append(fn[:-5])
    return saves

# ── First-person dungeon view ─────────────────────────────────────
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
                if 0 <= tr < H and 0 <= lc < W: view[tr][lc] = '+'
                if 0 <= tr < H and 0 <= rc < W: view[tr][rc] = '+'
                if 0 <= br < H and 0 <= lc < W: view[br][lc] = '+'
                if 0 <= br < H and 0 <= rc < W: view[br][rc] = '+'
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
                        sprite = [l[:8] for l in mob_art[:3]]
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
    BG_MAGENTA = f"{CSI}45m"
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
                elif ch in ('.', ':', ',') and not above_horizon:
                    bg = theme_ground_bg
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


def render_minimap(dungeon, px, py, facing, radius=3, other_players=None, floor_num=0):
    """Render a small minimap around the player."""
    lines = []
    dir_arrows = ['^', '>', 'v', '<']

    # Build set of other player positions for fast lookup
    player_positions = {}
    if other_players:
        for name, ox, oy, of in other_players:
            player_positions[(ox, oy)] = name[0].upper()

    # Build monster positions
    monster_positions = {}
    for mob in get_floor_monsters(floor_num):
        if mob['alive']:
            monster_positions[(mob['x'], mob['y'])] = mob['symbol']

    for dy in range(-radius, radius + 1):
        row = ""
        for dx in range(-radius, radius + 1):
            mx, my = px + dx, py + dy
            if dx == 0 and dy == 0:
                row += color(dir_arrows[facing], YELLOW)
            elif (mx, my) in player_positions:
                row += color(player_positions[(mx, my)], GREEN)
            elif (mx, my) in monster_positions:
                row += color(monster_positions[(mx, my)], RED)
            elif 0 <= my < len(dungeon) and 0 <= mx < len(dungeon[0]):
                tile = dungeon[my][mx]
                if tile == 1:
                    row += color('#', DIM)
                elif tile == 0:
                    row += color('.', WHITE)
                elif tile == 2:
                    row += color('+', CYAN)
                elif tile == 3:
                    row += color('>', RED)
                elif tile == 4:
                    row += color('<', GREEN)
                elif tile == 5:
                    row += color('$', YELLOW)
                elif tile == 6:
                    row += color('~', CYAN)
                # Overworld tiles
                elif tile == OW_GRASS:
                    row += color('.', GREEN)
                elif tile == OW_FOREST:
                    row += color('T', f"{CSI}32m")
                elif tile == OW_MOUNTAIN:
                    row += color('^', WHITE)
                elif tile == OW_WATER:
                    row += color('~', f"{CSI}34m")
                elif tile == OW_ROAD:
                    row += color('=', YELLOW)
                elif tile == OW_TOWN:
                    row += color('@', f"{CSI}93m")
                elif tile == OW_DUNGEON:
                    row += color('D', RED)
                else:
                    row += color('.', DIM)
            else:
                row += ' '
        lines.append(row)

    return lines


# ── Shared World ───────────────────────────────────────────────────
GM_PASSWORD = os.environ.get("DUNGEON_GM_PASS", "dungeon")  # set via env var
BAN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "banned.json")
CUSTOM_MONSTERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_monsters.json")
CUSTOM_FLOORS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_floors")
os.makedirs(CUSTOM_FLOORS_DIR, exist_ok=True)
SCENE_THEMES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scene_themes.json")


# Color name -> ANSI code mapping for theme editing
COLOR_NAMES = {
    "black": "30", "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36", "white": "37",
    "gray": "90", "bright_red": "91", "bright_green": "92",
    "bright_yellow": "93", "bright_blue": "94", "bright_magenta": "95",
    "bright_cyan": "96", "bright_white": "97",
}
BG_COLOR_NAMES = {
    "black": "40", "red": "41", "green": "42", "yellow": "43",
    "blue": "44", "magenta": "45", "cyan": "46", "white": "47",
    "gray": "100", "bright_red": "101", "bright_green": "102",
    "bright_yellow": "103", "bright_blue": "104", "bright_magenta": "105",
    "bright_cyan": "106", "bright_white": "107", "none": "",
}


def load_scene_themes():
    if os.path.exists(SCENE_THEMES_FILE):
        with open(SCENE_THEMES_FILE) as f:
            return json.load(f)
    return {}


def save_scene_themes(themes):
    with open(SCENE_THEMES_FILE, 'w') as f:
        json.dump(themes, f, indent=2)


def load_custom_monsters():
    if os.path.exists(CUSTOM_MONSTERS_FILE):
        with open(CUSTOM_MONSTERS_FILE) as f:
            return json.load(f)
    return []


def save_custom_monsters(monsters):
    with open(CUSTOM_MONSTERS_FILE, 'w') as f:
        json.dump(monsters, f, indent=2)


BUILTIN_OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "builtin_overrides.json")


def save_builtin_overrides():
    """Save all built-in monster edits to disk."""
    overrides = {}
    for fl, mlist in MONSTERS_BY_FLOOR.items():
        for m in mlist:
            # Only save if it has custom art or non-default values
            if 'art' in m:
                key = f"{fl}_{m['name']}"
                overrides[key] = dict(m)
    # Also save all monsters to capture stat changes
    data = {}
    for fl, mlist in MONSTERS_BY_FLOOR.items():
        data[str(fl)] = mlist
    with open(BUILTIN_OVERRIDES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_builtin_overrides():
    """Apply saved overrides to built-in monsters on startup."""
    if not os.path.exists(BUILTIN_OVERRIDES_FILE):
        return
    with open(BUILTIN_OVERRIDES_FILE) as f:
        data = json.load(f)
    for fl_str, mlist in data.items():
        fl = int(fl_str)
        if fl in MONSTERS_BY_FLOOR:
            MONSTERS_BY_FLOOR[fl] = mlist


# Apply on import
load_builtin_overrides()


def save_custom_floor(floor_num, grid):
    """Save a modified floor to disk so edits persist across restarts."""
    path = os.path.join(CUSTOM_FLOORS_DIR, f"floor_{floor_num}.json")
    with open(path, 'w') as f:
        json.dump(grid, f)


def load_custom_floor(floor_num):
    """Load a custom floor if one exists."""
    path = os.path.join(CUSTOM_FLOORS_DIR, f"floor_{floor_num}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def load_bans():
    if os.path.exists(BAN_FILE):
        with open(BAN_FILE) as f:
            return json.load(f)
    return []


def save_bans(bans):
    with open(BAN_FILE, 'w') as f:
        json.dump(bans, f, indent=2)


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
                s.writer.close()
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
        self.reader = reader
        self.writer = writer
        self.char = None
        self.running = True
        self.message_log = []
        self.combat_shield_bonus = 0
        self.term_width = 80
        self.term_height = 24
        self.resized = False
        self.notify_event = asyncio.Event()  # set when new messages arrive
        self.is_gm = False

    async def send(self, text):
        # Normalize all \n to \r\n for telnet, but don't double up existing \r\n
        text = text.replace('\r\n', '\n').replace('\n', '\r\n')
        self.writer.write(text.encode('utf-8'))
        await self.writer.drain()

    async def send_line(self, text=""):
        await self.send(text + "\r\n")

    async def move_to(self, row, col):
        """Move cursor to absolute position (1-based)."""
        self.writer.write(f"\033[{row};{col}H".encode('utf-8'))
        await self.writer.drain()

    async def clear_row(self, row):
        """Clear a specific row."""
        await self.move_to(row, 1)
        self.writer.write(b"\033[2K")
        await self.writer.drain()

    def parse_naws(self, data):
        """Parse NAWS subnegotiation data to get terminal width/height."""
        if len(data) >= 4:
            w = (data[0] << 8) | data[1]
            h = (data[2] << 8) | data[3]
            w = max(40, min(200, w))
            h = max(16, min(80, h))
            if w != self.term_width or h != self.term_height:
                self.term_width = w
                self.term_height = h
                self.resized = True

    def get_view_size(self):
        """Calculate 3D viewport size. Aspect-ratio limited, extra space goes to log."""
        map_radius = self.get_map_radius()
        map_cols = (map_radius * 2 + 1) + 4
        avail_w = self.term_width - map_cols - 4
        vw = max(20, avail_w)
        # Cap viewport height at ~3:1 char ratio for good proportions
        max_vh = max(8, vw // 3)
        # But don't exceed available terminal rows minus chrome
        avail_h = self.term_height - 8
        vh = min(max_vh, avail_h)
        return vw, vh

    def get_log_rows(self):
        """How many rows available for the message/chat log below the viewport."""
        vw, vh = self.get_view_size()
        # viewport takes rows 3..(3+vh+2), status takes 2, controls 1, prompt 1
        used = 2 + vh + 2 + 2 + 1 + 1  # header + viewport+border + status + controls + prompt
        return max(2, self.term_height - used)

    def get_map_radius(self):
        # Scale minimap with terminal height - bigger terminal, bigger map
        return max(3, min(7, (self.term_height - 10) // 3))

    async def get_input(self, prompt="> ", preserve_spaces=False, prefill=""):
        await self.send(prompt)
        if prefill:
            # Send prefill text so it appears as if user typed it
            await self.send(prefill)
            data = prefill.encode('utf-8')
        else:
            data = b""
        while True:
            try:
                byte = await asyncio.wait_for(self.reader.read(1), timeout=300)
            except asyncio.TimeoutError:
                await self.send_line("\r\nConnection timed out. Farewell!")
                self.running = False
                return ""
            if not byte:
                self.running = False
                return ""

            # Handle telnet IAC sequences
            if byte == IAC:
                cmd = await self.reader.read(1)
                if cmd in (WILL, WONT, DO, DONT):
                    opt = await self.reader.read(1)
                    continue
                elif cmd == SB:
                    # Read subnegotiation data until IAC SE
                    sb_option = await self.reader.read(1)
                    sb_data = bytearray()
                    while True:
                        sb = await self.reader.read(1)
                        if sb == IAC:
                            se = await self.reader.read(1)
                            if se == SE:
                                break
                            sb_data.append(sb[0])
                        else:
                            sb_data.append(sb[0])
                    if sb_option == NAWS:
                        self.parse_naws(sb_data)
                    continue

            # Handle backspace
            if byte in (b'\x7f', b'\x08'):
                if data:
                    data = data[:-1]
                    await self.send('\b \b')
                continue

            # Handle enter
            if byte in (b'\r', b'\n'):
                if byte == b'\r':
                    # Consume following \n if present
                    try:
                        next_byte = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                        if next_byte != b'\n':
                            data += next_byte
                    except asyncio.TimeoutError:
                        pass
                await self.send("\r\n")
                result = data.decode('utf-8', errors='ignore')
                return result.rstrip() if preserve_spaces else result.strip()

            # Handle escape sequences (arrow keys)
            if byte == b'\x1b':
                try:
                    seq1 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                    if seq1 == b'[':
                        seq2 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                        if seq2 == b'A':
                            return 'w'  # up arrow
                        elif seq2 == b'B':
                            return 's'  # down arrow (back)
                        elif seq2 == b'C':
                            return 'd'  # right arrow
                        elif seq2 == b'D':
                            return 'a'  # left arrow
                except asyncio.TimeoutError:
                    pass
                continue

            # Regular character - echo it
            if 32 <= byte[0] < 127:
                data += byte
                await self.send(byte.decode('utf-8', errors='ignore'))

        result = data.decode('utf-8', errors='ignore')
        return result.rstrip() if preserve_spaces else result.strip()

    async def get_char(self, prompt="", redraw_on_resize=False):
        """Get a single character without waiting for enter.
        If redraw_on_resize=True, returns 'RESIZE' when terminal size changes
        or when a notification (chat, broadcast) arrives."""
        if prompt:
            await self.send(prompt)
        self.resized = False
        self.notify_event.clear()
        while True:
            # Race: wait for either user input or a notification
            read_task = asyncio.ensure_future(self.reader.read(1))
            notify_task = asyncio.ensure_future(self.notify_event.wait())
            try:
                done, pending = await asyncio.wait(
                    [read_task, notify_task],
                    timeout=300,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                read_task.cancel()
                notify_task.cancel()
                return ''

            # Cancel whichever didn't finish
            for task in pending:
                task.cancel()

            if not done:
                # Timeout
                return ''

            # Check if notification won
            if notify_task in done:
                if redraw_on_resize:
                    self.notify_event.clear()
                    # If read_task also completed, we need to handle that byte
                    if read_task in done:
                        # Put it back by processing below
                        pass
                    else:
                        return 'RESIZE'

            if read_task not in done:
                continue

            try:
                byte = read_task.result()
            except Exception:
                self.running = False
                return ''
            if not byte:
                self.running = False
                return ''
            if byte == IAC:
                cmd = await self.reader.read(1)
                if cmd in (WILL, WONT, DO, DONT):
                    await self.reader.read(1)
                    continue
                elif cmd == SB:
                    sb_option = await self.reader.read(1)
                    sb_data = bytearray()
                    while True:
                        sb = await self.reader.read(1)
                        if sb == IAC:
                            se = await self.reader.read(1)
                            if se == SE:
                                break
                            sb_data.append(sb[0])
                        else:
                            sb_data.append(sb[0])
                    if sb_option == NAWS:
                        self.parse_naws(sb_data)
                    continue
            # If we got a resize during this wait, signal it
            if self.resized and redraw_on_resize:
                self.resized = False
                return 'RESIZE'
            if byte == b'\x1b':
                try:
                    seq1 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                    if seq1 == b'[':
                        seq2 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                        if seq2 == b'A': return 'w'
                        elif seq2 == b'B': return 's'
                        elif seq2 == b'C': return 'd'
                        elif seq2 == b'D': return 'a'
                except asyncio.TimeoutError:
                    pass
                continue
            if byte in (b'\r', b'\n'):
                return '\r'
            if 32 <= byte[0] < 127:
                return byte.decode('utf-8', errors='ignore')
        return ''

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
            path = os.path.join(SAVE_DIR, f"{self.char['name'].lower()}.json")
            if os.path.exists(path):
                os.remove(path)
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

                        save_builtin_overrides()
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
        # Send telnet negotiations
        self.writer.write(IAC + WILL + ECHO)    # We'll handle echo
        self.writer.write(IAC + WILL + SGA)     # Suppress go ahead
        self.writer.write(IAC + DO + NAWS)      # Request window size
        await self.writer.drain()

        # Give client time to respond with NAWS and other negotiations
        # Read any pending negotiation bytes
        await asyncio.sleep(0.3)
        try:
            while True:
                byte = await asyncio.wait_for(self.reader.read(1), timeout=0.2)
                if not byte:
                    break
                if byte == IAC:
                    cmd = await self.reader.read(1)
                    if cmd in (WILL, WONT, DO, DONT):
                        await self.reader.read(1)
                    elif cmd == SB:
                        sb_option = await self.reader.read(1)
                        sb_data = bytearray()
                        while True:
                            sb = await self.reader.read(1)
                            if sb == IAC:
                                se = await self.reader.read(1)
                                if se == SE:
                                    break
                                sb_data.append(sb[0])
                            else:
                                sb_data.append(sb[0])
                        if sb_option == NAWS:
                            self.parse_naws(sb_data)
        except asyncio.TimeoutError:
            pass  # Done reading negotiation data

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

        self.writer.close()


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
