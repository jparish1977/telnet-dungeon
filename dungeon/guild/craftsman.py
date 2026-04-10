"""Craftsman — a wandering NPC that scans the world for problems.

No LLM. Pure rules. Walks floors and overworld segments, identifies
issues (boring rooms, dead ends, missing water, etc.), and posts
jobs to the guild queue for the architect to review.

The craftsman is a regular game entity — visible to players, moves
at game speed, can be spectated.
"""

from dungeon.config import (
    OW_GRASS, OW_FOREST, OW_MOUNTAIN, OW_WATER, OW_ROAD, OW_TOWN, OW_DUNGEON,
    OVERWORLD_FLOOR,
)
from dungeon.floor import get_floor, is_overworld
from dungeon.guild.jobs import (
    post_job,
    BORING_ROOM, DEAD_END, EMPTY_FLOOR, LONG_CORRIDOR,
    SPARSE_TREASURES, ISOLATED_AREA,
    MISSING_WATER, DISCONNECTED_TOWN, DEAD_END_ROAD,
)


# ── Floor analysis helpers ────────────────────────────────────────

def _flood_reachable(grid, start_x, start_y, passable=None):
    """BFS from a point, return set of reachable (x,y) tuples."""
    size = len(grid)
    if passable is None:
        passable = {0, 2, 3, 4, 5, 6, 7}  # everything except walls (7=secret wall, passable)
    visited = set()
    stack = [(start_x, start_y)]
    while stack:
        x, y = stack.pop()
        if (x, y) in visited:
            continue
        if not (0 <= x < size and 0 <= y < size):
            continue
        if grid[y][x] not in passable:
            continue
        visited.add((x, y))
        stack.extend([(x+1, y), (x-1, y), (x, y+1), (x, y-1)])
    return visited


def _find_rooms(grid):
    """Find rectangular open areas (connected floor tiles).

    Returns list of dicts: {x1, y1, x2, y2, tiles, features}.
    Uses connected-component analysis on floor tiles.
    """
    size = len(grid)
    visited = set()
    rooms = []

    for y in range(1, size - 1):
        for x in range(1, size - 1):
            if grid[y][x] in (0, 5, 6) and (x, y) not in visited:
                # BFS to find this room's extent
                room_tiles = set()
                features = []
                queue = [(x, y)]
                while queue:
                    cx, cy = queue.pop(0)
                    if (cx, cy) in room_tiles or (cx, cy) in visited:
                        continue
                    if not (0 <= cx < size and 0 <= cy < size):
                        continue
                    t = grid[cy][cx]
                    if t in (1,):  # wall stops room
                        continue
                    if t == 2:  # door is a boundary but we note it
                        continue
                    room_tiles.add((cx, cy))
                    visited.add((cx, cy))
                    if t == 5:
                        features.append(('chest', cx, cy))
                    elif t == 6:
                        features.append(('fountain', cx, cy))
                    elif t == 3:
                        features.append(('stairs_down', cx, cy))
                    elif t == 4:
                        features.append(('stairs_up', cx, cy))
                    queue.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])

                if len(room_tiles) >= 4:  # skip tiny 1-2 tile spots
                    xs = [t[0] for t in room_tiles]
                    ys = [t[1] for t in room_tiles]
                    rooms.append({
                        'x1': min(xs), 'y1': min(ys),
                        'x2': max(xs), 'y2': max(ys),
                        'tile_count': len(room_tiles),
                        'features': features,
                    })

    return rooms


def _find_dead_ends(grid):
    """Find tiles with only one open neighbor (dead-end corridors)."""
    size = len(grid)
    dead_ends = []
    for y in range(1, size - 1):
        for x in range(1, size - 1):
            if grid[y][x] not in (0, 2):
                continue
            neighbors = 0
            for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < size and 0 <= ny < size and grid[ny][nx] != 1:
                    neighbors += 1
            if neighbors == 1:
                dead_ends.append((x, y))
    return dead_ends


def _find_long_corridors(grid, min_length=6):
    """Find straight corridors longer than min_length tiles."""
    size = len(grid)
    corridors = []

    # Horizontal
    for y in range(1, size - 1):
        run_start = None
        for x in range(1, size - 1):
            is_corridor = (grid[y][x] in (0, 2)
                           and grid[y-1][x] == 1
                           and grid[y+1][x] == 1)
            if is_corridor:
                if run_start is None:
                    run_start = x
            else:
                if run_start is not None and x - run_start >= min_length:
                    corridors.append({
                        'x1': run_start, 'y1': y,
                        'x2': x - 1, 'y2': y,
                        'length': x - run_start,
                        'direction': 'horizontal',
                    })
                run_start = None
        if run_start is not None and size - 1 - run_start >= min_length:
            corridors.append({
                'x1': run_start, 'y1': y,
                'x2': size - 2, 'y2': y,
                'length': size - 1 - run_start,
                'direction': 'horizontal',
            })

    # Vertical
    for x in range(1, size - 1):
        run_start = None
        for y in range(1, size - 1):
            is_corridor = (grid[y][x] in (0, 2)
                           and grid[y][x-1] == 1
                           and grid[y][x+1] == 1)
            if is_corridor:
                if run_start is None:
                    run_start = y
            else:
                if run_start is not None and y - run_start >= min_length:
                    corridors.append({
                        'x1': x, 'y1': run_start,
                        'x2': x, 'y2': y - 1,
                        'length': y - run_start,
                        'direction': 'vertical',
                    })
                run_start = None

    return corridors


# ── Dungeon floor inspection ─────────────────────────────────────

def inspect_dungeon_floor(floor_num):
    """Scan a dungeon floor and return a list of findings.

    Each finding is a dict ready to be posted as a job.
    """
    grid = get_floor(floor_num)
    size = len(grid)
    findings = []

    rooms = _find_rooms(grid)

    # Boring rooms: large area (>= 9 tiles) with zero features
    for room in rooms:
        if room['tile_count'] >= 9 and not room['features']:
            findings.append({
                'type': BORING_ROOM,
                'floor': floor_num,
                'area': [room['x1'], room['y1'], room['x2'], room['y2']],
                'context': f"Room of {room['tile_count']} tiles with no features",
                'priority': 1,
            })

    # Dead ends
    dead_ends = _find_dead_ends(grid)
    if dead_ends:
        # Group nearby dead ends
        for dx, dy in dead_ends:
            findings.append({
                'type': DEAD_END,
                'floor': floor_num,
                'area': [dx, dy, dx, dy],
                'context': f"Dead end at ({dx},{dy})",
                'priority': 0,
            })

    # Long boring corridors
    corridors = _find_long_corridors(grid)
    for c in corridors:
        findings.append({
            'type': LONG_CORRIDOR,
            'floor': floor_num,
            'area': [c['x1'], c['y1'], c['x2'], c['y2']],
            'context': f"{c['direction']} corridor, {c['length']} tiles long",
            'priority': 1,
        })

    # Sparse treasures: count chests vs floor size
    total_chests = sum(1 for y in range(size) for x in range(size) if grid[y][x] == 5)
    expected = max(3, size // 8)
    if total_chests < expected:
        findings.append({
            'type': SPARSE_TREASURES,
            'floor': floor_num,
            'area': None,
            'context': f"Only {total_chests} chests on a {size}x{size} floor (expected ~{expected})",
            'priority': 2,
        })

    # Check reachability from stairs up
    stairs_up = None
    for y in range(size):
        for x in range(size):
            if grid[y][x] == 4:
                stairs_up = (x, y)
                break
        if stairs_up:
            break

    if stairs_up:
        reachable = _flood_reachable(grid, stairs_up[0], stairs_up[1])
        # Count walkable tiles
        all_walkable = set()
        for y in range(size):
            for x in range(size):
                if grid[y][x] in (0, 2, 3, 4, 5, 6):
                    all_walkable.add((x, y))
        isolated = all_walkable - reachable
        if isolated:
            # Find bounding box of isolated area
            xs = [t[0] for t in isolated]
            ys = [t[1] for t in isolated]
            findings.append({
                'type': ISOLATED_AREA,
                'floor': floor_num,
                'area': [min(xs), min(ys), max(xs), max(ys)],
                'context': f"{len(isolated)} unreachable tiles",
                'priority': 3,  # high priority — broken gameplay
            })

    return findings


# ── Overworld segment inspection ─────────────────────────────────

def inspect_overworld(segment_meta=None):
    """Scan the current overworld segment for issues."""
    grid = get_floor(OVERWORLD_FLOOR)
    size = len(grid)
    findings = []

    # Count terrain types
    counts = {}
    town_positions = []
    road_positions = []
    dungeon_positions = []

    for y in range(size):
        for x in range(size):
            t = grid[y][x]
            counts[t] = counts.get(t, 0) + 1
            if t == OW_TOWN:
                town_positions.append((x, y))
            elif t == OW_ROAD:
                road_positions.append((x, y))
            elif t == OW_DUNGEON:
                dungeon_positions.append((x, y))

    # Missing water
    water_count = counts.get(OW_WATER, 0)
    water_pct = water_count / (size * size)
    if water_pct < 0.01 and segment_meta:
        # Check if this segment should have water (western edge = Lake Michigan)
        grid_pos = segment_meta.get('grid', [0, 0])
        if grid_pos[0] >= 4:  # western columns should have lake
            findings.append({
                'type': MISSING_WATER,
                'floor': OVERWORLD_FLOOR,
                'area': None,
                'context': f"Western segment ({grid_pos[0]},{grid_pos[1]}) has only {water_pct:.1%} water — Lake Michigan should be visible",
                'priority': 3,
            })

    # Disconnected towns — check if each town has road adjacent
    for tx, ty in town_positions:
        has_road = False
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1),
                        (1, 1), (-1, 1), (1, -1), (-1, -1)]:
            nx, ny = tx + dx, ty + dy
            if 0 <= nx < size and 0 <= ny < size and grid[ny][nx] == OW_ROAD:
                has_road = True
                break
        if not has_road:
            findings.append({
                'type': DISCONNECTED_TOWN,
                'floor': OVERWORLD_FLOOR,
                'area': [tx, ty, tx, ty],
                'context': f"Town at ({tx},{ty}) has no adjacent road",
                'priority': 2,
            })

    return findings


# ── Craftsman walk logic ──────────────────────────────────────────

class Craftsman:
    """A wandering NPC that inspects the world and posts jobs.

    Doesn't need a game session — just reads floor data directly.
    Can optionally be attached to a visible entity in the game world.
    """

    def __init__(self, name="Mason"):
        self.name = name
        self.floors_inspected = set()
        self.segments_inspected = set()
        self.total_jobs_posted = 0

    def inspect_floor(self, floor_num):
        """Inspect a dungeon floor and post any findings as jobs."""
        findings = inspect_dungeon_floor(floor_num)
        posted = 0
        for f in findings:
            job_id = post_job(
                f['type'], f['floor'], f.get('area'),
                f.get('context'), f.get('priority', 0),
            )
            if job_id:
                posted += 1
        self.floors_inspected.add(floor_num)
        self.total_jobs_posted += posted
        return findings, posted

    def inspect_segment(self, segment_meta=None):
        """Inspect the current overworld segment and post findings."""
        findings = inspect_overworld(segment_meta)
        posted = 0
        for f in findings:
            job_id = post_job(
                f['type'], f['floor'], f.get('area'),
                f.get('context'), f.get('priority', 0),
            )
            if job_id:
                posted += 1
        key = str(segment_meta.get('grid', [0, 0])) if segment_meta else 'default'
        self.segments_inspected.add(key)
        self.total_jobs_posted += posted
        return findings, posted

    def patrol_floors(self, start=0, end=20, verbose=False):
        """Walk a range of dungeon floors, inspecting each one."""
        results = []
        for f in range(start, end + 1):
            findings, posted = self.inspect_floor(f)
            if verbose and findings:
                print(f"[{self.name}] Floor {f}: {len(findings)} issues found, {posted} new jobs posted")
                for finding in findings:
                    print(f"  - {finding['type']}: {finding.get('context', '')}")
            results.append({
                'floor': f,
                'findings': len(findings),
                'posted': posted,
            })
        return results

    def status(self):
        return {
            'name': self.name,
            'floors_inspected': len(self.floors_inspected),
            'segments_inspected': len(self.segments_inspected),
            'total_jobs_posted': self.total_jobs_posted,
        }
