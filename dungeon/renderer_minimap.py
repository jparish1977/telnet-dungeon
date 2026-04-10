"""Minimap renderer - small radar-style map around the player."""

from dungeon.config import (
    CSI, DIM, RED, GREEN, YELLOW, CYAN, WHITE,
    color,
    OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
    TILE_WALL, TILE_SECRET_WALL,
)
from dungeon.monsters import get_floor_monsters


def render_minimap(dungeon, px, py, facing, radius=3, other_players=None, floor_num=0,
                   quest_markers=None):
    """Render a small minimap around the player.
    quest_markers: list of (x, y, symbol, color_code) for quest entrances/NPCs."""
    lines = []
    dir_arrows = ['^', '>', 'v', '<']

    # Build set of other player positions for fast lookup
    player_positions = {}
    if other_players:
        for name, ox, oy, _of in other_players:
            player_positions[(ox, oy)] = name[0].upper()

    # Build monster positions
    monster_positions = {}
    for mob in get_floor_monsters(floor_num):
        if mob['alive']:
            monster_positions[(mob['x'], mob['y'])] = mob['symbol']

    # Build quest marker positions
    quest_positions = {}
    if quest_markers:
        for qx, qy, qsym, qcol in quest_markers:
            quest_positions[(qx, qy)] = (qsym, qcol)

    for dy in range(-radius, radius + 1):
        row = ""
        for dx in range(-radius, radius + 1):
            mx, my = px + dx, py + dy
            if dx == 0 and dy == 0:
                row += color(dir_arrows[facing], YELLOW)
            elif (mx, my) in player_positions:
                row += color(player_positions[(mx, my)], GREEN)
            elif (mx, my) in quest_positions:
                qsym, qcol = quest_positions[(mx, my)]
                row += color(qsym, qcol)
            elif (mx, my) in monster_positions:
                row += color(monster_positions[(mx, my)], RED)
            elif 0 <= my < len(dungeon) and 0 <= mx < len(dungeon[0]):
                tile = dungeon[my][mx]
                if tile == TILE_WALL or tile == TILE_SECRET_WALL:
                    row += color('#', DIM)
                elif tile == 0:
                    row += color('.', WHITE)
                elif tile == 2:
                    row += color('+', CYAN)
                elif tile == 3:
                    row += color('>', RED)
                elif tile == 4:
                    row += color('<', GREEN)
                elif tile == 5:
                    row += color('$', YELLOW)
                elif tile == 6:
                    row += color('~', CYAN)
                # Overworld tiles
                elif tile == OW_GRASS:
                    row += color('.', GREEN)
                elif tile == OW_FOREST:
                    row += color('T', f"{CSI}32m")
                elif tile == OW_MOUNTAIN:
                    row += color('^', WHITE)
                elif tile == OW_WATER:
                    row += color('~', f"{CSI}34m")
                elif tile == OW_ROAD:
                    row += color('=', YELLOW)
                elif tile == OW_TOWN:
                    row += color('@', f"{CSI}93m")
                elif tile == OW_DUNGEON:
                    row += color('D', RED)
                else:
                    row += color('.', DIM)
            else:
                row += ' '
        lines.append(row)

    return lines
