"""Weapons, armor, spells, character classes, and direction constants."""

# ── Weapons ───────────────────────────────────────────────────────
WEAPONS = [
    {"name": "Rusty Dagger",   "atk": 2,  "price": 0},
    {"name": "Short Sword",    "atk": 5,  "price": 50},
    {"name": "Longsword",      "atk": 8,  "price": 150},
    {"name": "Battle Axe",     "atk": 11, "price": 300},
    {"name": "Flaming Sword",  "atk": 15, "price": 600},
    {"name": "Vorpal Blade",   "atk": 20, "price": 1200},
]

# ── Armor ─────────────────────────────────────────────────────────
ARMOR = [
    {"name": "Cloth Rags",     "def": 1,  "price": 0},
    {"name": "Leather Armor",  "def": 3,  "price": 40},
    {"name": "Chain Mail",     "def": 6,  "price": 120},
    {"name": "Plate Armor",    "def": 9,  "price": 350},
    {"name": "Mithril Plate",  "def": 13, "price": 800},
    {"name": "Dragon Scale",   "def": 18, "price": 1500},
]

# ── Spells ────────────────────────────────────────────────────────
SPELLS = {
    "HEAL":     {"cost": 3, "desc": "Restore 15-25 HP",     "min_level": 1},
    "FIREBALL": {"cost": 5, "desc": "Deal 12-20 fire dmg",  "min_level": 2},
    "SHIELD":   {"cost": 4, "desc": "+5 DEF for combat",    "min_level": 3},
    "LIGHTNING":{"cost": 7, "desc": "Deal 20-35 dmg",       "min_level": 4},
    "CURE":     {"cost": 6, "desc": "Remove poison",        "min_level": 2},
}

# ── Character classes ─────────────────────────────────────────────
CLASSES = {
    "FIGHTER": {"hp": 30, "mp": 0,  "atk": 8, "def": 6, "spd": 4, "desc": "Strong melee, high HP, no magic"},
    "MAGE":    {"hp": 16, "mp": 20, "atk": 3, "def": 3, "spd": 5, "desc": "Powerful spells, fragile body"},
    "THIEF":   {"hp": 22, "mp": 5,  "atk": 6, "def": 4, "spd": 8, "desc": "Fast, finds traps & treasure"},
    "CLERIC":  {"hp": 24, "mp": 15, "atk": 5, "def": 5, "spd": 4, "desc": "Healing magic, decent combat"},
}

# ── Directions ────────────────────────────────────────────────────
NORTH, EAST, SOUTH, WEST = 0, 1, 2, 3
DIR_NAMES = ["North", "East", "South", "West"]
DIR_DX = [0, 1, 0, -1]  # column delta
DIR_DY = [-1, 0, 1, 0]  # row delta
