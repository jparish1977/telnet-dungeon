"""Character validation, sanitization, and stat helpers."""

from dungeon.config import OVERWORLD_FLOOR
from dungeon.items import WEAPONS, ARMOR
from dungeon.persistence import save_character
from dungeon.floor import (
    get_floor, get_floor_spawn, get_overworld_spawn,
    is_tile_blocked, MAX_FLOOR,
)


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


def validate_position(char):
    """Make sure a character isn't stuck in a wall/water/mountain. Fix if so."""
    sanitize_character(char)
    floor_num = char['floor']
    floor = get_floor(floor_num)
    size = len(floor)
    x, y = char['x'], char['y']
    if x < 0 or y < 0 or x >= size or y >= size or is_tile_blocked(floor[y][x], floor_num):
        if floor_num == OVERWORLD_FLOOR:
            sx, sy = get_overworld_spawn()
        else:
            sx, sy = get_floor_spawn(floor_num)
        char['x'] = sx
        char['y'] = sy
        save_character(char)
        return True
    return False


def get_atk(char):
    """Calculate total attack power."""
    return char['base_atk'] + WEAPONS[char['weapon']]['atk']


def get_def(char, shield_bonus=0):
    """Calculate total defense."""
    return char['base_def'] + ARMOR[char['armor']]['def'] + shield_bonus
