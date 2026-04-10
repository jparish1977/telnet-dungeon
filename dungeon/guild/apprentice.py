"""Apprentice — scripted builder NPCs that execute work orders.

Apprentices take planned jobs from the queue and apply the operations
to the game world. They're not dumb stampers — they validate each op
and solve simple problems on their own:

- Target tile is a wall? Dig a corridor to reach it.
- Placement would be unreachable? Find the nearest reachable spot.
- Problem too complex? Post a new job back to the architect.

In game mode (future), they walk to the site and place tiles one at a
time, so players can spectate them building.
"""

from dungeon.floor import get_floor, set_floor, is_overworld
from dungeon.gm.map_ops import apply_ops, save_floor, set_tile, carve_corridor
from dungeon.guild.jobs import (
    get_planned_jobs, start_work, finish_work, post_job,
)
from dungeon.guild.craftsman import _flood_reachable


def _find_nearest_open(grid, x, y, max_search=10):
    """Find the nearest walkable tile to (x,y). Returns (nx, ny) or None."""
    size = len(grid)
    walkable = {0, 2, 3, 4, 5, 6}
    for radius in range(1, max_search + 1):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue  # only check the perimeter of each ring
                nx, ny = x + dx, y + dy
                if 0 < nx < size - 1 and 0 < ny < size - 1:
                    if grid[ny][nx] in walkable:
                        return nx, ny
    return None


def _is_reachable_from_stairs(grid, x, y):
    """Check if (x,y) is reachable from stairs up."""
    size = len(grid)
    # Find stairs up
    stairs = None
    for sy in range(size):
        for sx in range(size):
            if grid[sy][sx] == 4:
                stairs = (sx, sy)
                break
        if stairs:
            break
    if not stairs:
        return True  # no stairs, can't check
    reachable = _flood_reachable(grid, stairs[0], stairs[1])
    return (x, y) in reachable


class Apprentice:
    """A scripted NPC builder that executes work orders from the architect.

    Smart enough to handle simple problems:
    - Wall in the way? Dig a tunnel.
    - Unreachable spot? Find nearby open tile or dig to it.
    - Can't figure it out? Escalate back to the architect.
    """

    def __init__(self, name="Hodge"):
        self.name = name
        self.jobs_completed = 0
        self.total_ops_applied = 0
        self.ops_fixed = 0
        self.ops_escalated = 0
        self.current_job = None

    def _validate_and_fix_op(self, grid, op, floor_num, verbose=False):
        """Check a single op and fix it if possible.

        Returns (fixed_ops, ok) where fixed_ops is a list of ops to
        execute (may be more than one if we added a tunnel), and ok
        is False if we should escalate to the architect.
        """
        size = len(grid)
        action = op.get('action', '')

        if action == 'set_tile':
            x, y, tile = op.get('x', -1), op.get('y', -1), op.get('tile', 0)

            # Bounds check
            if not (0 < x < size - 1 and 0 < y < size - 1):
                if verbose:
                    print(f"    [{self.name}] Skipping out-of-bounds tile at ({x},{y})")
                return [], True  # skip silently, not worth escalating

            # Don't overwrite stairs
            if grid[y][x] in (3, 4):
                if verbose:
                    print(f"    [{self.name}] Skipping — won't overwrite stairs at ({x},{y})")
                return [], True

            # Don't place a door if there's already one within 2 tiles
            if tile == 2:
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        if dx == 0 and dy == 0:
                            continue
                        cx, cy = x + dx, y + dy
                        if 0 <= cx < size and 0 <= cy < size and grid[cy][cx] == 2:
                            if verbose:
                                print(f"    [{self.name}] Skipping door at ({x},{y}) — door already nearby at ({cx},{cy})")
                            return [], True

            # Placing a feature (chest, fountain) in a wall?
            if tile in (5, 6) and grid[y][x] == 1:
                # Find nearest open tile and dig a tunnel
                nearest = _find_nearest_open(grid, x, y)
                if nearest:
                    nx, ny = nearest
                    if verbose:
                        print(f"    [{self.name}] Wall at ({x},{y}) — digging tunnel from ({nx},{ny})")
                    self.ops_fixed += 1
                    return [
                        {"action": "carve_corridor", "x1": nx, "y1": ny, "x2": x, "y2": y},
                        op,
                    ], True
                else:
                    if verbose:
                        print(f"    [{self.name}] Can't reach ({x},{y}) — escalating")
                    self.ops_escalated += 1
                    return [], False

            return [op], True

        elif action == 'place_room':
            x, y = op.get('x', -1), op.get('y', -1)
            w, h = op.get('w', 3), op.get('h', 3)
            x2, y2 = x + w - 1, y + h - 1

            # Bounds check
            if x < 1 or y < 1 or x2 >= size - 1 or y2 >= size - 1:
                if verbose:
                    print(f"    [{self.name}] Room at ({x},{y}) {w}x{h} out of bounds — shrinking")
                # Clamp to valid area
                x = max(1, x)
                y = max(1, y)
                w = min(w, size - 2 - x)
                h = min(h, size - 2 - y)
                if w < 3 or h < 3:
                    return [], True  # too small, skip
                op = dict(op, x=x, y=y, w=w, h=h)
                self.ops_fixed += 1

            # Check if room connects to existing dungeon
            door_side = op.get('door_side')
            if door_side:
                # The door should connect to walkable space
                mid_x = (x + x + w - 1) // 2
                mid_y = (y + y + h - 1) // 2
                door_check = {
                    'north': (mid_x, y - 1),
                    'south': (mid_x, y + h),
                    'east': (x + w, mid_y),
                    'west': (x - 1, mid_y),
                }
                check = door_check.get(door_side)
                if check:
                    cx, cy = check
                    if 0 < cx < size - 1 and 0 < cy < size - 1:
                        if grid[cy][cx] == 1:
                            # Door opens into wall — dig a corridor to nearest open
                            nearest = _find_nearest_open(grid, cx, cy)
                            if nearest:
                                nx, ny = nearest
                                if verbose:
                                    print(f"    [{self.name}] Room door opens into wall — digging access tunnel from ({nx},{ny})")
                                self.ops_fixed += 1
                                return [
                                    op,
                                    {"action": "carve_corridor", "x1": nx, "y1": ny, "x2": cx, "y2": cy},
                                ], True

            return [op], True

        # All other ops — pass through
        return [op], True

    def execute_one(self, verbose=False):
        """Pick up one planned job and execute its ops with validation.

        Returns the completed job dict, or None.
        """
        planned = get_planned_jobs(limit=1)
        if not planned:
            if verbose:
                print(f"[{self.name}] No planned work.")
            return None

        job = planned[0]
        started = start_work(job['id'])
        if not started:
            return None

        self.current_job = job
        floor_num = job['floor']
        ops = job.get('ops', [])

        if verbose:
            print(f"[{self.name}] Job #{job['id']}: {job['type']} on floor {floor_num}")
            print(f"  Validating {len(ops)} operations...")

        if ops:
            grid = get_floor(floor_num)
            validated_ops = []
            escalate_needed = False

            for op in ops:
                fixed, ok = self._validate_and_fix_op(grid, op, floor_num, verbose)
                if not ok:
                    escalate_needed = True
                validated_ops.extend(fixed)

            if verbose and self.ops_fixed:
                print(f"  Fixed {self.ops_fixed} ops (dug tunnels, clamped bounds, etc.)")

            if validated_ops:
                result = apply_ops(floor_num, validated_ops)
                self.total_ops_applied += result['applied']

                if verbose:
                    print(f"  Applied {result['applied']} ops.")
                    if result['errors']:
                        for err in result['errors'][:5]:
                            print(f"  [WARN] {err}")

                # Verify reachability after all ops applied
                grid = get_floor(floor_num)
                stairs = None
                for y in range(len(grid)):
                    for x in range(len(grid[0])):
                        if grid[y][x] == 4:
                            stairs = (x, y)
                            break
                    if stairs:
                        break

                if stairs:
                    reachable = _flood_reachable(grid, stairs[0], stairs[1])
                    # Check all features are reachable
                    for y in range(len(grid)):
                        for x in range(len(grid[0])):
                            if grid[y][x] in (3, 5, 6) and (x, y) not in reachable:
                                if verbose:
                                    tile_name = {3: 'stairs_down', 5: 'chest', 6: 'fountain'}[grid[y][x]]
                                    print(f"  [FIX] Unreachable {tile_name} at ({x},{y}) — digging access")
                                nearest = _find_nearest_open_reachable(grid, x, y, reachable)
                                if nearest:
                                    carve_corridor(grid, nearest[0], nearest[1], x, y)
                                    set_floor(floor_num, grid)
                                    self.ops_fixed += 1

                save_floor(floor_num)
                if verbose:
                    print(f"  Floor {floor_num} saved.")

            if escalate_needed and verbose:
                print(f"  [{self.name}] Some ops couldn't be fixed — would escalate to architect")

        finish_work(job['id'])
        self.jobs_completed += 1
        self.current_job = None

        if verbose:
            notes = job.get('notes', '')
            if notes:
                print(f"  Architect's notes: {notes}")

        return job

    def execute_all(self, verbose=False):
        """Execute all planned jobs."""
        count = 0
        while True:
            result = self.execute_one(verbose=verbose)
            if result is None:
                break
            count += 1
        if verbose and count:
            print(f"[{self.name}] Completed {count} jobs, {self.total_ops_applied} total ops"
                  f" ({self.ops_fixed} fixed, {self.ops_escalated} escalated).")
        return count

    def status(self):
        return {
            'name': self.name,
            'jobs_completed': self.jobs_completed,
            'total_ops_applied': self.total_ops_applied,
            'ops_fixed': self.ops_fixed,
            'ops_escalated': self.ops_escalated,
            'current_job': self.current_job['id'] if self.current_job else None,
        }


def _find_nearest_open_reachable(grid, x, y, reachable):
    """Find nearest tile that's both walkable and in the reachable set."""
    size = len(grid)
    for radius in range(1, 20):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) != radius and abs(dy) != radius:
                    continue
                nx, ny = x + dx, y + dy
                if 0 < nx < size - 1 and 0 < ny < size - 1:
                    if (nx, ny) in reachable:
                        return nx, ny
    return None
