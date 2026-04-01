"""Monster definitions, scaling for deep floors, floor mob spawning and AI movement."""

import random

from dungeon.persistence import load_custom_monsters, load_builtin_overrides
from dungeon.floor import get_floor

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

# Apply builtin overrides on import
_overrides = load_builtin_overrides()
if _overrides:
    for fl_str, mlist in _overrides.items():
        fl = int(fl_str)
        if fl in MONSTERS_BY_FLOOR:
            MONSTERS_BY_FLOOR[fl] = mlist


# ── Monster scaling for deep floors ──────────────────────────────

def get_monsters_for_floor(floor_num):
    """Get monster list for a floor, scaling stats for deep floors. Includes custom monsters."""
    customs = load_custom_monsters()
    floor_customs = [m for m in customs if m.get('floor', -1) in (-1, floor_num)]

    if floor_num in MONSTERS_BY_FLOOR:
        return MONSTERS_BY_FLOOR[floor_num] + floor_customs

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
        depth_prefix = ["Ancient ", "Elder ", "Abyssal ", "Void ", "Eternal "]
        prefix = depth_prefix[min((floor_num - 3) // 2, len(depth_prefix) - 1)]
        sm['name'] = prefix + m['name']
        scaled.append(sm)
    return scaled + floor_customs


# ── Floor monsters (visible wandering mobs) ──────────────────────

_floor_monsters = {}


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

    num_mobs = max(3, size // 4)
    num_mobs = min(num_mobs, 40)

    monsters = []
    for _ in range(num_mobs):
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
                for _ in range(30):
                    rx = random.randint(1, size - 2)
                    ry = random.randint(1, size - 2)
                    if floor[ry][rx] == 0:
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

        # Find nearest player
        nearest_dist = 999
        nearest_px, nearest_py = mob['x'], mob['y']
        for px, py in player_positions:
            dist = abs(px - mob['x']) + abs(py - mob['y'])
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_px, nearest_py = px, py

        # Behavior-driven AI (if mob has rules)
        if mob.get('behavior'):
            from dungeon.behavior import evaluate_behavior
            players_info = [{'x': px, 'y': py, 'hp': 1, 'max_hp': 1, 'class': ''}
                            for px, py in player_positions]
            alive_allies = sum(1 for m in monsters if m['alive'] and m is not mob)
            actions = evaluate_behavior(
                mob, players_info, floor_num, ally_count=alive_allies,
            )
            nx, ny = _execute_movement_action(
                actions, mob, nearest_px, nearest_py, size,
            )
            if nx is None:
                continue
        # Default hardcoded AI (chase/wander)
        elif nearest_dist <= 5 and random.random() < 0.6:
            dx = 0
            dy = 0
            if nearest_px > mob['x']:
                dx = 1
            elif nearest_px < mob['x']:
                dx = -1
            if nearest_py > mob['y']:
                dy = 1
            elif nearest_py < mob['y']:
                dy = -1
            if random.random() < 0.5:
                nx, ny = mob['x'] + dx, mob['y']
            else:
                nx, ny = mob['x'], mob['y'] + dy
        elif random.random() < 0.3:
            direction = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            nx, ny = mob['x'] + direction[0], mob['y'] + direction[1]
        else:
            continue

        if 0 < nx < size - 1 and 0 < ny < size - 1:
            tile = floor[ny][nx]
            if tile != 1:
                occupied = any(m['x'] == nx and m['y'] == ny and m['alive'] and m is not mob
                              for m in monsters)
                if not occupied:
                    mob['x'] = nx
                    mob['y'] = ny


def _execute_movement_action(actions, mob, target_x, target_y, floor_size):
    """Translate behavior actions into a movement target.

    Returns (nx, ny) or (None, None) if no movement.
    """
    for act in actions:
        if act == 'move_toward_player':
            dx = 0
            dy = 0
            if target_x > mob['x']:
                dx = 1
            elif target_x < mob['x']:
                dx = -1
            if target_y > mob['y']:
                dy = 1
            elif target_y < mob['y']:
                dy = -1
            if random.random() < 0.5:
                return mob['x'] + dx, mob['y']
            else:
                return mob['x'], mob['y'] + dy

        elif act == 'flee_from_player':
            dx = 0
            dy = 0
            if target_x > mob['x']:
                dx = -1
            elif target_x < mob['x']:
                dx = 1
            if target_y > mob['y']:
                dy = -1
            elif target_y < mob['y']:
                dy = 1
            if random.random() < 0.5:
                return mob['x'] + dx, mob['y']
            else:
                return mob['x'], mob['y'] + dy

        elif act == 'patrol' or act.startswith('patrol '):
            direction = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            return mob['x'] + direction[0], mob['y'] + direction[1]

        elif act == 'idle':
            return None, None

        elif act.startswith('teleport '):
            parts = act.split()
            if len(parts) == 3:
                try:
                    tx, ty = int(parts[1]), int(parts[2])
                    if 0 < tx < floor_size - 1 and 0 < ty < floor_size - 1:
                        return tx, ty
                except ValueError:
                    pass

    # No movement action found — stay put
    return None, None


def get_monster_at(floor_num, x, y):
    """Get the first alive monster at a position, or None."""
    for mob in get_floor_monsters(floor_num):
        if mob['alive'] and mob['x'] == x and mob['y'] == y:
            return mob
    return None


def kill_monster(mob):
    """Mark a monster as dead and start respawn timer."""
    mob['alive'] = False
    mob['respawn_timer'] = random.randint(15, 30)
