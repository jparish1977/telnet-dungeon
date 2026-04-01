#!/usr/bin/env python3
"""Generate a connected region of overworld maps from Buchanan to Benton Harbor.

Each segment is a 128x128 map covering ~5km x 5km. Segments connect at edges
via portal tiles. Each segment gets a quest pack stub.
"""

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Tile codes
OW_GRASS = 10
OW_FOREST = 11
OW_MOUNTAIN = 12
OW_WATER = 13
OW_ROAD = 14
OW_TOWN = 15
OW_DUNGEON = 16
OW_PORTAL = 17  # new: portal to adjacent map segment

# Region definition
SEGMENTS = [
    # (grid_col, grid_row, center_lat, center_lon, name, towns)
    (0, 0, 41.8275, -86.3611, "buchanan", [
        ("Buchanan", 41.8275, -86.3611),
    ]),
    (1, 0, 41.8275, -86.3011, "niles", [
        ("Niles", 41.8348, -86.2543),
    ]),
    (0, 1, 41.8725, -86.3611, "buchanan_north", []),
    (1, 1, 41.8725, -86.3011, "niles_north", []),
    (0, 2, 41.9175, -86.3611, "berrien_springs", [
        ("Berrien Springs", 41.9465, -86.3387),
    ]),
    (1, 2, 41.9175, -86.3011, "berrien_east", []),
    (0, 3, 41.9625, -86.3611, "eau_claire_west", [
        ("Eau Claire", 41.9835, -86.3023),
    ]),
    (1, 3, 41.9625, -86.3011, "eau_claire", []),
    (0, 4, 42.0075, -86.3611, "coloma_south", []),
    (1, 4, 42.0075, -86.3011, "coloma", [
        ("Coloma", 42.1862, -86.3085),  # approximate
    ]),
    (0, 5, 42.0525, -86.3611, "hagar_shores", []),
    (1, 5, 42.0525, -86.3011, "watervliet_area", []),
    (0, 6, 42.0975, -86.3611, "benton_harbor", [
        ("Benton Harbor", 42.1167, -86.4542),
        ("St. Joseph", 42.1097, -86.4808),
    ]),
    (1, 6, 42.0975, -86.3011, "benton_east", []),
]

SIZE = 128
SPAN_KM = 5.0


def generate_segment_terrain(center_lat, center_lon, seed):
    """Generate terrain for a single map segment."""
    rng = random.Random(seed)
    grid = [[OW_GRASS for _ in range(SIZE)] for _ in range(SIZE)]

    # Simple noise for terrain
    def noise(x, y, scale=1.0):
        # Layered pseudo-noise
        v = 0
        for octave in range(4):
            freq = (2 ** octave) * scale
            v += math.sin(x * freq * 0.1 + octave * 17) * math.cos(y * freq * 0.08 + octave * 31)
            v += rng.uniform(-0.1, 0.1)
        return v

    km_per_deg_lon = 111.0 * math.cos(math.radians(center_lat))

    for row in range(SIZE):
        for col in range(SIZE):
            n = noise(col + seed * 7, row + seed * 13, 1.0)

            # St. Joseph River runs through the region roughly N-S
            # River x position varies by latitude
            river_x = 0.35 + 0.1 * math.sin(row * 0.05 + seed)
            river_dist = abs(col / SIZE - river_x)

            if river_dist < 0.03:
                grid[row][col] = OW_WATER
            elif river_dist < 0.06:
                grid[row][col] = OW_GRASS  # floodplain
            elif n > 1.5:
                grid[row][col] = OW_MOUNTAIN
            elif n > 0.5:
                grid[row][col] = OW_FOREST
            else:
                grid[row][col] = OW_GRASS

    # Lake Michigan influence (west side of western segments)
    if center_lon < -86.4:
        for row in range(SIZE):
            for col in range(SIZE // 4):
                if rng.random() < 0.7:
                    grid[row][col] = OW_WATER

    # Border
    for i in range(SIZE):
        grid[0][i] = OW_WATER
        grid[SIZE-1][i] = OW_WATER
        grid[i][0] = OW_WATER
        grid[i][SIZE-1] = OW_WATER

    return grid


def place_town(grid, cx, cy):
    """Clear area and place a town."""
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            ny, nx = cy + dy, cx + dx
            if 0 < ny < SIZE-1 and 0 < nx < SIZE-1:
                grid[ny][nx] = OW_GRASS
    grid[cy][cx] = OW_TOWN


def place_roads(grid, towns, rng):
    """Connect towns with roads."""
    for i in range(1, len(towns)):
        x1, y1 = towns[i-1]
        x2, y2 = towns[i]
        x, y = x1, y1
        while x != x2 or y != y2:
            if 0 < x < SIZE-1 and 0 < y < SIZE-1 and grid[y][x] != OW_WATER:
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


def place_portals(grid, grid_col, grid_row, max_col, max_row):
    """Place portal tiles at edges connecting to adjacent segments."""
    mid = SIZE // 2
    # North edge
    if grid_row < max_row:
        for dx in range(-1, 2):
            grid[1][mid + dx] = OW_ROAD
        grid[0][mid] = OW_PORTAL
    # South edge
    if grid_row > 0:
        for dx in range(-1, 2):
            grid[SIZE-2][mid + dx] = OW_ROAD
        grid[SIZE-1][mid] = OW_PORTAL
    # East edge
    if grid_col < max_col:
        for dy in range(-1, 2):
            grid[mid + dy][SIZE-2] = OW_ROAD
        grid[mid][SIZE-1] = OW_PORTAL
    # West edge
    if grid_col > 0:
        for dy in range(-1, 2):
            grid[mid + dy][1] = OW_ROAD
        grid[mid][0] = OW_PORTAL


def latlon_to_grid(lat, lon, center_lat, center_lon):
    """Convert lat/lon to grid position within a segment."""
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(center_lat))
    lat_span = SPAN_KM / km_per_deg_lat
    lon_span = SPAN_KM / km_per_deg_lon
    min_lat = center_lat - lat_span / 2
    max_lat = center_lat + lat_span / 2
    min_lon = center_lon - lon_span / 2
    max_lon = center_lon + lon_span / 2
    row = int((max_lat - lat) / (max_lat - min_lat) * (SIZE - 1))
    col = int((lon - min_lon) / (max_lon - min_lon) * (SIZE - 1))
    return max(1, min(SIZE-2, col)), max(1, min(SIZE-2, row))


def generate_quest_stub(segment_name, towns):
    """Generate a quest pack stub for a segment."""
    quest = {
        "id": f"quest_{segment_name}",
        "name": f"Tales of {towns[0][0] if towns else segment_name.replace('_', ' ').title()}",
        "description": f"Explore the {segment_name.replace('_', ' ').title()} region.",
        "entrances": [],
        "quest_floors": {},
        "npcs": {},
        "stages": [
            {"id": "started", "description": "Begin exploring."},
            {"id": "complete", "description": "Region explored."},
        ],
        "rewards": {"gold": 500},
    }
    return quest


def main():
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "region_maps")
    quest_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "quests")
    os.makedirs(output_dir, exist_ok=True)

    max_col = max(s[0] for s in SEGMENTS)
    max_row = max(s[1] for s in SEGMENTS)

    # Region index
    region_index = {
        "name": "Berrien County",
        "description": "Buchanan to Benton Harbor, Michigan",
        "segments": [],
    }

    for grid_col, grid_row, center_lat, center_lon, name, towns in SEGMENTS:
        print(f"Generating {name} ({grid_col},{grid_row})...")

        seed = hash(name) & 0xFFFFFF
        grid = generate_segment_terrain(center_lat, center_lon, seed)
        rng = random.Random(seed)

        # Place towns
        town_positions = []
        for town_name, town_lat, town_lon in towns:
            tx, ty = latlon_to_grid(town_lat, town_lon, center_lat, center_lon)
            place_town(grid, tx, ty)
            town_positions.append((tx, ty))
            print(f"  {town_name} at ({tx},{ty})")

        # Place roads between towns
        if len(town_positions) > 1:
            place_roads(grid, town_positions, rng)

        # Main N-S road through each segment
        road_x = SIZE // 2 + rng.randint(-10, 10)
        for y in range(1, SIZE-1):
            if grid[y][road_x] not in (OW_WATER, OW_TOWN):
                grid[y][road_x] = OW_ROAD

        # Dungeon entrances
        for _ in range(rng.randint(2, 4)):
            for attempt in range(30):
                dx = rng.randint(5, SIZE-5)
                dy = rng.randint(5, SIZE-5)
                if grid[dy][dx] in (OW_GRASS, OW_FOREST):
                    grid[dy][dx] = OW_DUNGEON
                    break

        # Portals at edges
        place_portals(grid, grid_col, grid_row, max_col, max_row)

        # Save map
        map_path = os.path.join(output_dir, f"{name}.json")
        with open(map_path, 'w') as f:
            json.dump(grid, f)

        # Generate quest stub
        quest = generate_quest_stub(name, towns)
        quest_path = os.path.join(quest_dir, f"quest_{name}.json")
        if not os.path.exists(quest_path):  # don't overwrite existing quests
            with open(quest_path, 'w') as f:
                json.dump(quest, f, indent=2)
            print(f"  Quest stub: {quest_path}")

        region_index["segments"].append({
            "name": name,
            "grid": [grid_col, grid_row],
            "center": [center_lat, center_lon],
            "map_file": f"{name}.json",
            "towns": [t[0] for t in towns],
            "connections": {
                "north": grid_row < max_row,
                "south": grid_row > 0,
                "east": grid_col < max_col,
                "west": grid_col > 0,
            },
        })

    # Save region index
    index_path = os.path.join(output_dir, "region_index.json")
    with open(index_path, 'w') as f:
        json.dump(region_index, f, indent=2)

    print(f"\nGenerated {len(SEGMENTS)} map segments in {output_dir}/")
    print(f"Region index: {index_path}")
    print(f"\nTo use: load segment maps as overworld replacements via the portal system")


if __name__ == "__main__":
    main()
