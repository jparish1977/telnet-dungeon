#!/usr/bin/env python3
"""Convert a real map image to dungeon overworld tiles.

Grabs OpenStreetMap tiles for a given area, stitches them,
and converts pixel colors to game tiles.

Usage:
    python tools/map_image_to_tiles.py --lat 42.01 --lon -86.52 --name stevensville
    python tools/map_image_to_tiles.py --lat 42.11 --lon -86.45 --name benton_harbor
"""

import argparse
import math
import os

import requests
from PIL import Image

# Game tiles
OW_GRASS = 10
OW_FOREST = 11
OW_MOUNTAIN = 12
OW_WATER = 13
OW_ROAD = 14
OW_TOWN = 15
OW_DUNGEON = 16

# OSM tile server (free, no key needed)
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
TILE_SIZE = 256


def latlon_to_tile(lat, lon, zoom):
    """Convert lat/lon to OSM tile x,y at given zoom."""
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    lat_rad = math.radians(lat)
    y = int((1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n)
    return x, y


def tile_to_latlon(x, y, zoom):
    """Convert tile x,y to lat/lon (NW corner)."""
    n = 2 ** zoom
    lon = x / n * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lat, lon


def fetch_tile(z, x, y, cache_dir=".tile_cache"):
    """Fetch a single OSM tile, with caching."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = os.path.join(cache_dir, f"{z}_{x}_{y}.png")
    if os.path.exists(cache_path):
        return Image.open(cache_path)

    url = TILE_URL.format(z=z, x=x, y=y)
    headers = {"User-Agent": "DungeonCrawlerOfDoom/1.0 (map generator)"}
    print(f"  Fetching tile {z}/{x}/{y}...", end=" ", flush=True)
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    with open(cache_path, 'wb') as f:
        f.write(resp.content)
    print("OK")
    return Image.open(cache_path)


def fetch_area(center_lat, center_lon, zoom=14, span_km=5.0):
    """Fetch and stitch OSM tiles covering an area."""
    # Calculate how many tiles we need
    # At zoom 14, each tile covers ~1.2km
    km_per_tile = 40075 * math.cos(math.radians(center_lat)) / (2 ** zoom)

    tiles_needed = math.ceil(span_km / km_per_tile) + 1

    center_tx, center_ty = latlon_to_tile(center_lat, center_lon, zoom)
    half = tiles_needed // 2

    # Fetch tiles
    images = {}
    for dy in range(-half, half + 1):
        for dx in range(-half, half + 1):
            tx, ty = center_tx + dx, center_ty + dy
            try:
                img = fetch_tile(zoom, tx, ty)
                images[(dx, dy)] = img
            except Exception as e:
                print(f"  Failed: {e}")

    if not images:
        print("ERROR: No tiles fetched!")
        return None

    # Stitch into one image
    width = (2 * half + 1) * TILE_SIZE
    height = (2 * half + 1) * TILE_SIZE
    stitched = Image.new("RGB", (width, height))

    for (dx, dy), img in images.items():
        px = (dx + half) * TILE_SIZE
        py = (dy + half) * TILE_SIZE
        stitched.paste(img, (px, py))

    return stitched


def classify_pixel(r, g, b):
    """Classify an RGB pixel as a game tile based on OSM standard tile colors.
    Colors sampled from actual OSM tiles for SW Michigan."""

    # Water: OSM renders water as (170,211,223) and similar blue-gray
    # Key: b > r, and the specific grayish-blue range
    if abs(r - 170) < 30 and abs(g - 211) < 30 and abs(b - 223) < 30:
        return OW_WATER
    # Darker water / river
    if b > 180 and b > r + 20 and g < b and r < 170:
        return OW_WATER
    # Very blue water
    if b > 200 and r < 150 and g < 200:
        return OW_WATER

    # Major roads: orange/yellow (252,214,164) and similar
    if r > 230 and g > 190 and b < 180 and r > b + 60:
        return OW_ROAD
    # White roads (255,255,255) and near-white
    if r > 248 and g > 248 and b > 248:
        return OW_ROAD
    # Light gray roads (238,238,238) and similar
    if r > 225 and g > 225 and b > 225 and abs(r - g) < 8 and abs(g - b) < 8:
        if r < 245:  # but not the land background
            return OW_ROAD

    # Buildings/urban: brown-gray (209,198,189), pink (235,219,232)
    if abs(r - 209) < 20 and abs(g - 198) < 20 and abs(b - 189) < 20:
        return OW_TOWN
    if abs(r - 235) < 15 and abs(g - 219) < 15 and abs(b - 232) < 15:
        return OW_TOWN
    # Commercial pink
    if r > 220 and g < 210 and b > 200 and r > g:
        return OW_TOWN
    # Gray urban areas
    if 200 < r < 225 and abs(r - g) < 10 and abs(g - b) < 10:
        return OW_TOWN

    # Forest: OSM green (173,209,158) and darker greens
    if g > r and g > b and g > 150:
        if r < 185 and g > 180:
            return OW_FOREST
    # Parks: light green (200,250,204), (222,246,192), (205,235,176)
    if g > 220 and g > r + 10 and g > b + 10 and r > 180:
        return OW_FOREST
    if abs(r - 222) < 20 and abs(g - 246) < 20 and abs(b - 192) < 20:
        return OW_FOREST

    # Land background: beige (242,239,233) = grass
    if r > 230 and g > 225 and b > 220 and abs(r - g) < 15:
        return OW_GRASS

    # Medium gray = hillside
    if r < 140 and g < 140 and b < 140:
        return OW_MOUNTAIN

    return OW_GRASS  # fallback


def image_to_grid(img, grid_size=128):
    """Convert an image to a game tile grid."""
    # Resize to grid size
    resized = img.resize((grid_size, grid_size), Image.LANCZOS)
    pixels = resized.load()

    grid = []
    for y in range(grid_size):
        row = []
        for x in range(grid_size):
            r, g, b = pixels[x, y][:3]
            tile = classify_pixel(r, g, b)
            row.append(tile)
        grid.append(row)

    # Post-process: smooth noise, ensure borders
    # Water border
    for i in range(grid_size):
        if grid[0][i] == OW_GRASS:
            grid[0][i] = OW_WATER
        if grid[grid_size-1][i] == OW_GRASS:
            grid[grid_size-1][i] = OW_WATER
        if grid[i][0] == OW_GRASS:
            grid[i][0] = OW_WATER
        if grid[i][grid_size-1] == OW_GRASS:
            grid[i][grid_size-1] = OW_WATER

    return grid


def main():
    parser = argparse.ArgumentParser(description="Convert OSM map to game tiles")
    parser.add_argument("--lat", type=float, required=True, help="Center latitude")
    parser.add_argument("--lon", type=float, required=True, help="Center longitude")
    parser.add_argument("--name", required=True, help="Output name")
    parser.add_argument("--zoom", type=int, default=14, help="OSM zoom level (default 14)")
    parser.add_argument("--size", type=int, default=128, help="Grid size (default 128)")
    parser.add_argument("--span", type=float, default=5.0, help="Area span in km (default 5)")
    parser.add_argument("--preview", action="store_true", help="Save preview images")
    args = parser.parse_args()

    print(f"Fetching OSM tiles for ({args.lat}, {args.lon})...")
    img = fetch_area(args.lat, args.lon, args.zoom, args.span)
    if img is None:
        return

    if args.preview:
        img.save(f"{args.name}_osm.png")
        print(f"  Saved {args.name}_osm.png")

    print(f"Converting to {args.size}x{args.size} game grid...")
    grid = image_to_grid(img, args.size)

    # Save
    import json
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "region_maps", f"{args.name}.json"
    )
    with open(output_path, 'w') as f:
        json.dump(grid, f)
    print(f"Saved to {output_path}")

    if args.preview:
        # Render preview
        colors = {
            OW_GRASS: (80, 160, 60), OW_FOREST: (30, 100, 30),
            OW_MOUNTAIN: (140, 130, 120), OW_WATER: (40, 80, 180),
            OW_ROAD: (180, 160, 100), OW_TOWN: (200, 180, 60),
            OW_DUNGEON: (200, 50, 50),
        }
        from PIL import ImageDraw
        scale = 4
        preview = Image.new("RGB", (args.size * scale, args.size * scale))
        draw = ImageDraw.Draw(preview)
        for y in range(args.size):
            for x in range(args.size):
                c = colors.get(grid[y][x], (100, 100, 100))
                draw.rectangle([x*scale, y*scale, (x+1)*scale-1, (y+1)*scale-1], fill=c)
        preview.save(f"{args.name}_preview.png")
        print(f"  Saved {args.name}_preview.png")

    # Stats
    from collections import Counter
    counts = Counter(t for row in grid for t in row)
    names = {OW_GRASS: 'grass', OW_FOREST: 'forest', OW_MOUNTAIN: 'mountain',
             OW_WATER: 'water', OW_ROAD: 'road', OW_TOWN: 'town'}
    print("\nTile distribution:")
    for tile, count in counts.most_common():
        pct = count / (args.size * args.size) * 100
        print(f"  {names.get(tile, '?'):10s}: {count:5d} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
