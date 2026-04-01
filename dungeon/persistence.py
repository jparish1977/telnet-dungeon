"""JSON file I/O for saves, bans, custom monsters, custom floors, and scene themes."""

import json
import os

# ── File paths (relative to project root) ─────────────────────────
_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SAVE_DIR = os.path.join(_PROJECT_DIR, "saves")
os.makedirs(SAVE_DIR, exist_ok=True)

BAN_FILE = os.path.join(_PROJECT_DIR, "banned.json")

CUSTOM_MONSTERS_FILE = os.path.join(_PROJECT_DIR, "custom_monsters.json")

CUSTOM_FLOORS_DIR = os.path.join(_PROJECT_DIR, "custom_floors")
os.makedirs(CUSTOM_FLOORS_DIR, exist_ok=True)

SCENE_THEMES_FILE = os.path.join(_PROJECT_DIR, "scene_themes.json")

BUILTIN_OVERRIDES_FILE = os.path.join(_PROJECT_DIR, "builtin_overrides.json")


# ── Character saves ───────────────────────────────────────────────

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


def delete_save(name):
    path = os.path.join(SAVE_DIR, f"{name.lower()}.json")
    if os.path.exists(path):
        os.remove(path)


# ── Bans ──────────────────────────────────────────────────────────

def load_bans():
    if os.path.exists(BAN_FILE):
        with open(BAN_FILE) as f:
            return json.load(f)
    return []


def save_bans(bans):
    with open(BAN_FILE, 'w') as f:
        json.dump(bans, f, indent=2)


# ── Custom monsters ──────────────────────────────────────────────

def load_custom_monsters():
    if os.path.exists(CUSTOM_MONSTERS_FILE):
        with open(CUSTOM_MONSTERS_FILE) as f:
            return json.load(f)
    return []


def save_custom_monsters(monsters):
    with open(CUSTOM_MONSTERS_FILE, 'w') as f:
        json.dump(monsters, f, indent=2)


# ── Builtin monster overrides ────────────────────────────────────

def save_builtin_overrides(monsters_by_floor):
    """Save all built-in monster data to disk."""
    data = {}
    for fl, mlist in monsters_by_floor.items():
        data[str(fl)] = mlist
    with open(BUILTIN_OVERRIDES_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def load_builtin_overrides():
    """Load saved overrides for built-in monsters."""
    if not os.path.exists(BUILTIN_OVERRIDES_FILE):
        return None
    with open(BUILTIN_OVERRIDES_FILE) as f:
        return json.load(f)


# ── Custom floors ────────────────────────────────────────────────

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


# ── Scene themes ─────────────────────────────────────────────────

def load_scene_themes():
    if os.path.exists(SCENE_THEMES_FILE):
        with open(SCENE_THEMES_FILE) as f:
            return json.load(f)
    return {}


def save_scene_themes(themes):
    with open(SCENE_THEMES_FILE, 'w') as f:
        json.dump(themes, f, indent=2)
