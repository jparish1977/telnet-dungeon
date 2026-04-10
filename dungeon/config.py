"""Constants, ANSI helpers, tile codes, and telnet protocol bytes."""

import os
import sys

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

PORT = 2323
for _arg in sys.argv[1:]:
    if _arg.isdigit():
        PORT = int(_arg)
        break

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


# ── Dungeon Tiles ─────────────────────────────────────────────────
TILE_FLOOR = 0
TILE_WALL = 1
TILE_DOOR = 2
TILE_STAIRS_DOWN = 3
TILE_STAIRS_UP = 4
TILE_CHEST = 5
TILE_FOUNTAIN = 6
TILE_SECRET_WALL = 7  # renders as wall, but walkable — hidden passage

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

# ── GM Configuration ──────────────────────────────────────────────
GM_PASSWORD = os.environ.get("DUNGEON_GM_PASS", "dungeon")  # set via env var

# ── Color name mappings for theme editing ─────────────────────────
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
