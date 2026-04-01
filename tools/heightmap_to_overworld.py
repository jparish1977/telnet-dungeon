#!/usr/bin/env python3
"""Generate a dungeon overworld map from real-world elevation data.

Uses the Open-Elevation API (free, no key needed) to grab a heightmap
for a given area, then converts it to game tiles.

Usage:
    python tools/heightmap_to_overworld.py [--size 128] [--output overworld.json]
"""

import argparse
import json
import math

import requests
from PIL import Image, ImageDraw

# Tile codes from dungeon/config.py
OW_GRASS = 10
OW_FOREST = 11
OW_MOUNTAIN = 12
OW_WATER = 13
OW_ROAD = 14
OW_TOWN = 15
OW_DUNGEON = 16

# Buchanan, Michigan - center coordinates
# 41.8275° N, 86.3611° W
# St. Joseph River runs through it, Lake Michigan to the west
CENTER_LAT = 41.8275
CENTER_LON = -86.3611


def fetch_elevations(center_lat, center_lon, size, span_km=5.0):
    """Fetch elevation data from Open-Elevation API in a grid."""
    print(f"Fetching {size}x{size} elevation grid centered on ({center_lat}, {center_lon})...")

    # Calculate lat/lon bounds
    # ~111km per degree lat, ~85km per degree lon at this latitude
    km_per_deg_lat = 111.0
    km_per_deg_lon = 111.0 * math.cos(math.radians(center_lat))

    lat_span = span_km / km_per_deg_lat
    lon_span = span_km / km_per_deg_lon

    min_lat = center_lat - lat_span / 2
    max_lat = center_lat + lat_span / 2
    min_lon = center_lon - lon_span / 2
    max_lon = center_lon + lon_span / 2

    # Build grid of points
    locations = []
    for row in range(size):
        for col in range(size):
            lat = max_lat - (row / (size - 1)) * (max_lat - min_lat)
            lon = min_lon + (col / (size - 1)) * (max_lon - min_lon)
            locations.append({"latitude": round(lat, 6), "longitude": round(lon, 6)})

    # API has a limit per request, batch them
    batch_size = 500
    elevations = []
    for i in range(0, len(locations), batch_size):
        batch = locations[i:i + batch_size]
        print(f"  Requesting batch {i // batch_size + 1}/{math.ceil(len(locations) / batch_size)}...")
        try:
            resp = requests.post(
                "https://api.open-elevation.com/api/v1/lookup",
                json={"locations": batch},
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            elevations.extend([r["elevation"] for r in results])
        except Exception as e:
            print(f"  API error: {e}")
            print("  Falling back to synthetic data based on known geography...")
            return generate_buchanan_synthetic(size)

    return elevations


def generate_buchanan_synthetic(size):
    """Generate synthetic elevation data mimicking Buchanan, MI geography.
    - St. Joseph River runs roughly north-south through the center
    - Town is on the east bank
    - Relatively flat terrain (180-250m elevation)
    - River valley is lower
    - Some rolling hills to the east
    """
    import random
    rng = random.Random(41827)  # deterministic

    elevations = []
    for row in range(size):
        for col in range(size):
            # Normalize to 0-1
            x = col / (size - 1)
            y = row / (size - 1)

            # Base elevation: gentle hills
            base = 200 + 20 * math.sin(x * 4) * math.cos(y * 3)
            base += 10 * math.sin(x * 7 + 1) * math.sin(y * 5 + 2)

            # St. Joseph River: meanders north-south, slightly west of center
            river_x = 0.38 + 0.05 * math.sin(y * 8) + 0.03 * math.sin(y * 13)
            river_dist = abs(x - river_x)
            if river_dist < 0.04:
                base = 170  # river bed
            elif river_dist < 0.08:
                base = 175 + (river_dist - 0.04) * 500  # river banks

            # McCoy Creek: small tributary from the east
            if 0.4 < y < 0.55:
                creek_y = 0.47 + 0.02 * math.sin(x * 15)
                creek_dist = abs(y - creek_y)
                if creek_dist < 0.015 and x > 0.4:
                    base = 175

            # Some noise
            base += rng.uniform(-3, 3)

            elevations.append(base)

    return elevations


def elevations_to_tiles(elevations, size):
    """Convert elevation data to game tiles."""
    # Find min/max for normalization
    min_e = min(elevations)
    max_e = max(elevations)
    e_range = max_e - min_e if max_e > min_e else 1

    grid = []
    for row in range(size):
        grid_row = []
        for col in range(size):
            e = elevations[row * size + col]
            # Normalize to 0-1
            n = (e - min_e) / e_range

            if n < 0.15:
                tile = OW_WATER  # river/lake
            elif n < 0.25:
                tile = OW_GRASS  # low flat - floodplain
            elif n < 0.55:
                tile = OW_GRASS  # main terrain
            elif n < 0.7:
                tile = OW_FOREST  # wooded hills
            elif n < 0.85:
                tile = OW_FOREST  # dense forest
            else:
                tile = OW_MOUNTAIN  # highest points
            grid_row.append(tile)
        grid.append(grid_row)

    return grid


def place_buchanan_features(grid, size):
    """Place Buchanan-specific features on the map."""
    # Town center: east bank of the river, roughly center
    cx, cy = int(size * 0.52), int(size * 0.48)

    # Clear area for downtown
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            y, x = cy + dy, cx + dx
            if 0 <= y < size and 0 <= x < size:
                grid[y][x] = OW_GRASS
    grid[cy][cx] = OW_TOWN

    # A few more town blocks
    for dx, dy in [(3, 0), (-3, 0), (0, 3), (2, 2)]:
        y, x = cy + dy, cx + dx
        if 0 <= y < size and 0 <= x < size and grid[y][x] != OW_WATER:
            grid[y][x] = OW_TOWN

    # Main roads: Front St (along river), Red Bud Trail (east-west)
    # Front St - north-south along the river
    for row in range(size):
        x = int(size * 0.48)
        if 0 <= x < size and grid[row][x] != OW_WATER:
            grid[row][x] = OW_ROAD

    # Red Bud Trail / Main St - east-west through town
    for col in range(int(size * 0.3), int(size * 0.8)):
        if grid[cy][col] != OW_WATER:
            grid[cy][col] = OW_ROAD

    # Dungeon entrances
    dungeon_spots = [
        (int(size * 0.7), int(size * 0.3)),   # NE woods
        (int(size * 0.25), int(size * 0.65)),  # SW across river
        (int(size * 0.8), int(size * 0.75)),   # SE
    ]
    for dx, dy in dungeon_spots:
        if 0 <= dy < size and 0 <= dx < size and grid[dy][dx] not in (OW_WATER, OW_TOWN):
            grid[dy][dx] = OW_DUNGEON

    # Border with water (lake michigan vibe to the west)
    for i in range(size):
        grid[0][i] = OW_WATER
        grid[size - 1][i] = OW_WATER
        grid[i][0] = OW_WATER
        grid[i][size - 1] = OW_WATER

    return cx, cy


def render_preview(grid, size, filename="buchanan_preview.png"):
    """Render a PNG preview of the map."""
    colors = {
        OW_GRASS: (80, 160, 60),
        OW_FOREST: (30, 100, 30),
        OW_MOUNTAIN: (140, 130, 120),
        OW_WATER: (40, 80, 180),
        OW_ROAD: (180, 160, 100),
        OW_TOWN: (200, 180, 60),
        OW_DUNGEON: (200, 50, 50),
    }
    scale = 4
    img = Image.new("RGB", (size * scale, size * scale))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        for x in range(size):
            c = colors.get(grid[y][x], (100, 100, 100))
            draw.rectangle([x * scale, y * scale, (x + 1) * scale - 1, (y + 1) * scale - 1], fill=c)
    img.save(filename)
    print(f"Preview saved to {filename}")


def main():
    parser = argparse.ArgumentParser(description="Generate overworld from real elevation data")
    parser.add_argument("--size", type=int, default=128, help="Map size (default 128)")
    parser.add_argument("--output", default="buchanan_overworld.json", help="Output JSON file")
    parser.add_argument("--preview", action="store_true", help="Generate PNG preview")
    parser.add_argument("--api", action="store_true", help="Use real API (default: synthetic)")
    args = parser.parse_args()

    size = args.size

    if args.api:
        elevations = fetch_elevations(CENTER_LAT, CENTER_LON, size)
    else:
        print("Using synthetic Buchanan, MI geography...")
        elevations = generate_buchanan_synthetic(size)

    print("Converting to tiles...")
    grid = elevations_to_tiles(elevations, size)

    print("Placing Buchanan features...")
    cx, cy = place_buchanan_features(grid, size)
    print(f"Town center at ({cx}, {cy})")

    # Save
    with open(args.output, "w") as f:
        json.dump(grid, f)
    print(f"Map saved to {args.output}")

    if args.preview:
        render_preview(grid, size)

    # Print ASCII preview
    syms = {OW_GRASS: ".", OW_FOREST: "T", OW_MOUNTAIN: "^",
            OW_WATER: "~", OW_ROAD: "=", OW_TOWN: "@", OW_DUNGEON: "D"}
    print(f"\nASCII preview ({size}x{size}):")
    step = max(1, size // 40)
    for y in range(0, size, step):
        row = ""
        for x in range(0, size, step):
            row += syms.get(grid[y][x], "?")
        print(f"  {row}")


if __name__ == "__main__":
    main()
