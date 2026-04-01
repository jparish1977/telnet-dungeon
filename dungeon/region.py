"""Region system — manages connected overworld map segments.

When a player walks off the edge of an overworld map, this module
loads the adjacent segment and repositions the player on the opposite edge.
"""

import json
import os

from dungeon.config import OVERWORLD_FLOOR

REGION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "region_maps")
_region_index = None


def load_region_index():
    """Load the region index (cached)."""
    global _region_index
    if _region_index is not None:
        return _region_index
    path = os.path.join(REGION_DIR, "region_index.json")
    if os.path.exists(path):
        with open(path) as f:
            _region_index = json.load(f)
    else:
        _region_index = {"segments": [], "cols": 0, "rows": 0}
    return _region_index


def get_current_segment(char):
    """Get the segment grid coords for a character's current position."""
    return (
        char.get('region_col', 3),  # default: Buchanan column
        char.get('region_row', 0),  # default: Buchanan row
    )


def get_segment_name(col, row):
    """Get segment filename for grid position."""
    return f"seg_{col}_{row}"


def load_segment(col, row):
    """Load a segment map grid. Returns None if doesn't exist."""
    name = get_segment_name(col, row)
    path = os.path.join(REGION_DIR, f"{name}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def has_adjacent_segment(col, row, direction):
    """Check if there's a segment in the given direction (north/south/east/west)."""
    idx = load_region_index()
    max_col = idx.get('cols', 6) - 1
    max_row = idx.get('rows', 8) - 1

    if direction == 'north':
        return row < max_row
    elif direction == 'south':
        return row > 0
    elif direction == 'east':
        return col < max_col
    elif direction == 'west':
        return col > 0
    return False


def try_zone_transition(char, new_x, new_y, map_size):
    """Check if movement goes off the map edge and handle zone transition.

    Returns (transitioned, new_grid) where:
        transitioned: True if a zone change happened
        new_grid: the new map grid if transitioned, None otherwise
    """
    if char.get('floor') != OVERWORLD_FLOOR:
        return False, None

    col, row = get_current_segment(char)

    direction = None
    if new_y < 0:
        direction = 'north'
    elif new_y >= map_size:
        direction = 'south'
    elif new_x < 0:
        direction = 'west'
    elif new_x >= map_size:
        direction = 'east'

    if direction is None:
        return False, None

    if not has_adjacent_segment(col, row, direction):
        return False, None

    # Calculate new segment coords
    new_col, new_row = col, row
    if direction == 'north':
        new_row += 1
    elif direction == 'south':
        new_row -= 1
    elif direction == 'east':
        new_col += 1
    elif direction == 'west':
        new_col -= 1

    # Load new segment
    new_grid = load_segment(new_col, new_row)
    if new_grid is None:
        return False, None

    new_size = len(new_grid)

    # Position on opposite edge
    if direction == 'north':
        char['y'] = new_size - 2  # near south edge
        char['x'] = min(char['x'], new_size - 2)
    elif direction == 'south':
        char['y'] = 1  # near north edge
        char['x'] = min(char['x'], new_size - 2)
    elif direction == 'east':
        char['x'] = 1  # near west edge
        char['y'] = min(char['y'], new_size - 2)
    elif direction == 'west':
        char['x'] = new_size - 2  # near east edge
        char['y'] = min(char['y'], new_size - 2)

    char['region_col'] = new_col
    char['region_row'] = new_row

    return True, new_grid


def get_segment_display_name(col, row):
    """Get a human-readable name for a segment."""
    idx = load_region_index()
    for seg in idx.get('segments', []):
        if seg.get('grid') == [col, row]:
            towns = seg.get('towns', [])
            if towns:
                return ', '.join(towns)
            return seg.get('name', f'({col},{row})')
    return f'Wilderness ({col},{row})'
