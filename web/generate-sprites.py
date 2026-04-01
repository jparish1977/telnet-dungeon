#!/usr/bin/env python3
"""Generate placeholder sprite PNGs from ASCII monster art.

Renders each ASCII art character as a colored pixel in a small PNG.
Output: web/public/assets/monsters/*.png
"""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public", "assets", "monsters")
os.makedirs(ASSET_DIR, exist_ok=True)

# Pixel scale: each ASCII char becomes NxN pixels
SCALE = 8

# Color palette for ASCII chars
CHAR_COLORS = {
    '/': (200, 200, 200),
    '\\': (200, 200, 200),
    '|': (180, 180, 180),
    '-': (160, 160, 160),
    '_': (140, 140, 140),
    '+': (220, 220, 220),
    '=': (200, 200, 100),
    '#': (150, 100, 80),
    'o': (255, 255, 255),
    'O': (255, 255, 255),
    'x': (255, 50, 50),
    'X': (255, 50, 50),
    '*': (255, 255, 100),
    '~': (100, 180, 255),
    '^': (100, 200, 100),
    '.': (120, 120, 120),
    ':': (140, 140, 140),
    '@': (255, 200, 50),
    '$': (255, 215, 0),
    '>': (200, 200, 200),
    '<': (200, 200, 200),
    '(': (200, 150, 150),
    ')': (200, 150, 150),
    '[': (180, 180, 100),
    ']': (180, 180, 100),
    '{': (100, 200, 200),
    '}': (100, 200, 200),
    'A': (255, 100, 100),
    'n': (150, 120, 80),
}
DEFAULT_COLOR = (200, 80, 80)  # reddish for unrecognized chars
BG_COLOR = (0, 0, 0, 0)  # transparent


def render_ascii_to_ppm(art_lines: list[str], filename: str):
    """Render ASCII art to a simple PPM image (no dependencies needed).

    PPM is the simplest image format — just header + raw RGB bytes.
    Can be converted to PNG later or used directly.
    """
    if not art_lines:
        return

    # Find dimensions
    max_w = max(len(line) for line in art_lines)
    height = len(art_lines)
    img_w = max_w * SCALE
    img_h = height * SCALE

    # Build pixel data
    pixels = bytearray(img_w * img_h * 3)

    for row_idx, line in enumerate(art_lines):
        for col_idx, ch in enumerate(line):
            if ch == ' ':
                continue
            color = CHAR_COLORS.get(ch, DEFAULT_COLOR)
            for py in range(SCALE):
                for px in range(SCALE):
                    x = col_idx * SCALE + px
                    y = row_idx * SCALE + py
                    offset = (y * img_w + x) * 3
                    pixels[offset] = color[0]
                    pixels[offset + 1] = color[1]
                    pixels[offset + 2] = color[2]

    # Write PPM (P6 binary)
    with open(filename, 'wb') as f:
        f.write(f'P6\n{img_w} {img_h}\n255\n'.encode())
        f.write(pixels)

    print(f"  {os.path.basename(filename)}: {img_w}x{img_h}")


def main():
    # Load monster art from builtin_overrides.json
    overrides_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "builtin_overrides.json"
    )

    if os.path.exists(overrides_path):
        with open(overrides_path) as f:
            data = json.load(f)
        print(f"Loaded {sum(len(v) for v in data.values())} monsters from builtin_overrides.json")
    else:
        print("No builtin_overrides.json found, using inline defaults")
        data = {}

    # Also add some hardcoded fallback art
    all_monsters = {}
    for floor_key, monsters in data.items():
        for m in monsters:
            name = m.get('name', 'unknown')
            art = m.get('art', [])
            if art:
                all_monsters[name] = art

    # Add defaults if not in overrides
    defaults = {
        "Giant Rat": ["  (\\_/)", "  (o.o)", "  (> <)"],
        "Kobold": ["  /\\_/\\", " ( o.o)", "  > ^ <"],
        "Skeleton": ["   _||_", "  /o  o\\", "  |_/\\_|", "   /||\\"],
        "Giant Spider": [" /\\(oo)/\\", "//\\\\||//\\\\"],
        "Zombie": ["  [x_x]", "  /|  |\\", "  / \\/ \\"],
        "Orc Warrior": ["  /O O\\", "  |__|", " /|==|\\"],
        "Dark Elf": ["   /\\", "  (--)", "  /|\\"],
        "Ghoul": [" /x  x\\", " | \\/ |", " |____|"],
        "Minotaur": [" (\\  /)", "  (oo)", " /|==|\\"],
        "Lich": ["  _--_", " /o  o\\", " |\\__/|"],
        "Dragon Whelp": ["  /\\/\\", " / OO\\", "< \\/ >"],
        "Death Knight": ["  ---", " [o o]", " /||\\"],
        "Demon Lord": [" \\\\/\\_/\\//", "  ( O O )", "  \\ == /", "  /||||\\"],
        "Treasure": ["  ____", " |$$$$|", " |____|"],
        "Fountain": ["  {~~}", " {~~~~}", "  {~~}"],
        "Stairs Down": ["  >>>>", " >>>>>>", ">>>>>>>>"],
        "Stairs Up": ["  <<<<", " <<<<<<", "<<<<<<<<"],
    }

    for name, art in defaults.items():
        if name not in all_monsters:
            all_monsters[name] = art

    print(f"\nGenerating {len(all_monsters)} sprites:")
    for name, art in all_monsters.items():
        safe_name = name.lower().replace(' ', '_').replace("'", "")
        filename = os.path.join(ASSET_DIR, f"{safe_name}.ppm")
        render_ascii_to_ppm(art, filename)

    print(f"\nDone! Sprites in {ASSET_DIR}")
    print("Note: PPM format — convert to PNG with: mogrify -format png *.ppm")


if __name__ == '__main__':
    main()
