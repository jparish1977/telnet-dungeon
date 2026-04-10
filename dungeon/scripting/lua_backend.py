"""Lua scripting backend — sandboxed Lua execution via lupa."""

from lupa import LuaRuntime

from dungeon.scripting.base import ScriptingBackend


# Whitelist of safe Lua globals — no os, io, loadfile, dofile, etc.
_SAFE_GLOBALS = {
    'math', 'string', 'table', 'type', 'tostring', 'tonumber',
    'pairs', 'ipairs', 'next', 'select', 'unpack',
    'print',  # overridden to capture output
}


class LuaBackend(ScriptingBackend):
    """Sandboxed Lua 5.4 scripting via lupa."""

    @property
    def name(self) -> str:
        return "Lua (lupa)"

    def create_sandbox(self, game_state: dict) -> LuaRuntime:
        """Create a fresh Lua runtime with game state exposed."""
        lua = LuaRuntime(unpack_returned_tuples=True)

        # Remove dangerous globals
        for unsafe in ['os', 'io', 'loadfile', 'dofile', 'require',
                       'rawget', 'rawset', 'rawequal', 'rawlen',
                       'collectgarbage', 'debug', 'load', 'package']:
            lua.execute(f'{unsafe} = nil')

        # Inject game state as Lua tables
        mob = game_state.get('mob', {})
        lua.execute('mob = {}')
        mob_table = lua.eval('mob')
        for key, val in mob.items():
            if isinstance(val, (int, float, str, bool)):
                mob_table[key] = val

        # Compute derived values
        max_hp = mob.get('max_hp', mob.get('hp', 1))
        current_hp = mob.get('hp', max_hp)
        if max_hp > 0:
            lua.execute(f'mob.hp_pct = {int(current_hp / max_hp * 100)}')
        else:
            lua.execute('mob.hp_pct = 100')

        # Player info — expose nearest player and player list
        players = game_state.get('players', [])
        lua.execute('players = {}')
        if players:
            nearest = players[0]
            lua.execute('player = {}')
            player_table = lua.eval('player')
            for key, val in nearest.items():
                if isinstance(val, (int, float, str, bool)):
                    player_table[key] = val

            # Player distance (Manhattan)
            mx, my = mob.get('x', 0), mob.get('y', 0)
            px, py = nearest.get('x', 0), nearest.get('y', 0)
            lua.execute(f'player_distance = {abs(mx - px) + abs(my - py)}')

            # Player HP percentage
            p_max_hp = nearest.get('max_hp', 1)
            p_hp = nearest.get('hp', p_max_hp)
            lua.execute(f'player_hp_pct = {int(p_hp / max(1, p_max_hp) * 100)}')
            lua.execute(f'player_class = "{nearest.get("class", "")}"')
        else:
            lua.execute('player = nil')
            lua.execute('player_distance = 999')
            lua.execute('player_hp_pct = 100')
            lua.execute('player_class = ""')

        # Ally count (other mobs on same floor that are alive)
        lua.execute(f'ally_count = {game_state.get("ally_count", 0)}')

        # Quest/world flags
        flags = game_state.get('flags', {})
        lua.execute('flags = {}')
        flags_table = lua.eval('flags')
        for key, val in flags.items():
            flags_table[key] = val

        # has_flag helper
        lua.execute('''
            function has_flag(name)
                return flags[name] == true
            end
        ''')

        # Random helper (percentage check)
        lua.execute('''
            function random(pct)
                return math.random(100) <= pct
            end
        ''')

        # Floor info
        lua.execute(f'floor_num = {game_state.get("floor_num", 0)}')

        # ── Construction context (for builder NPCs) ──────────────
        floor_grid = game_state.get('floor_grid')
        if floor_grid:
            floor_size = len(floor_grid)
            lua.execute(f'floor_size = {floor_size}')
            mx, my = mob.get('x', 0), mob.get('y', 0)
            current_tile = floor_grid[my][mx] if 0 <= my < floor_size and 0 <= mx < floor_size else -1
            lua.execute(f'current_tile = {current_tile}')

            # Tile-at helper: tile_at(x, y) returns tile code
            # Store grid as flat string for Lua access
            flat = ','.join(str(floor_grid[y][x])
                           for y in range(floor_size) for x in range(floor_size))
            lua.execute(f'_grid_flat = {{{flat}}}')
            lua.execute(f'_grid_size = {floor_size}')
            lua.execute('''
                function tile_at(x, y)
                    if x < 0 or x >= _grid_size or y < 0 or y >= _grid_size then return -1 end
                    return _grid_flat[y * _grid_size + x + 1]
                end
            ''')

            # Scan surroundings: count of each tile type within radius
            radius = 5
            tile_counts = {}
            features_nearby = []
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    sx, sy = mx + dx, my + dy
                    if 0 <= sx < floor_size and 0 <= sy < floor_size:
                        t = floor_grid[sy][sx]
                        tile_counts[t] = tile_counts.get(t, 0) + 1
                        if t in (5, 6) and (dx != 0 or dy != 0):
                            features_nearby.append((t, sx, sy))

            lua.execute(f'nearby_walls = {tile_counts.get(1, 0)}')
            lua.execute(f'nearby_floors = {tile_counts.get(0, 0)}')
            lua.execute(f'nearby_doors = {tile_counts.get(2, 0)}')
            lua.execute(f'nearby_chests = {tile_counts.get(5, 0)}')
            lua.execute(f'nearby_fountains = {tile_counts.get(6, 0)}')
            lua.execute(f'nearby_features = {len(features_nearby)}')

            # Room analysis: how many open tiles are connected to current position
            if current_tile in (0, 2, 5, 6):
                visited = set()
                stack = [(mx, my)]
                room_size = 0
                while stack and room_size < 200:
                    cx, cy = stack.pop()
                    if (cx, cy) in visited:
                        continue
                    if not (0 <= cx < floor_size and 0 <= cy < floor_size):
                        continue
                    if floor_grid[cy][cx] in (1,):
                        continue
                    visited.add((cx, cy))
                    room_size += 1
                    stack.extend([(cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)])
                lua.execute(f'room_size = {room_size}')
            else:
                lua.execute('room_size = 0')

            # Corridor detection: am I in a narrow passage?
            h_walls = (0 <= mx < floor_size and 0 < my < floor_size - 1
                       and floor_grid[my-1][mx] == 1 and floor_grid[my+1][mx] == 1)
            v_walls = (0 < mx < floor_size - 1 and 0 <= my < floor_size
                       and floor_grid[my][mx-1] == 1 and floor_grid[my][mx+1] == 1)
            lua.execute(f'in_corridor = {"true" if (h_walls or v_walls) and current_tile in (0, 2) else "false"}')

            # Count corridor length in current direction
            corridor_len = 0
            if h_walls:
                for d in (-1, 1):
                    cx = mx + d
                    while 0 < cx < floor_size - 1 and floor_grid[my][cx] != 1:
                        corridor_len += 1
                        cx += d
            elif v_walls:
                for d in (-1, 1):
                    cy = my + d
                    while 0 < cy < floor_size - 1 and floor_grid[cy][mx] != 1:
                        corridor_len += 1
                        cy += d
            lua.execute(f'corridor_length = {corridor_len}')

            # Tile name helpers
            lua.execute('''
                function nearby_tile(tile_code)
                    local count = 0
                    for dy = -5, 5 do
                        for dx = -5, 5 do
                            if tile_at(mob.x + dx, mob.y + dy) == tile_code then
                                count = count + 1
                            end
                        end
                    end
                    return count
                end
            ''')

            lua.execute('''
                function room_has_feature(tile_code)
                    return nearby_tile(tile_code) > 0
                end
            ''')

        # Guild job queue access
        lua.execute(f'pending_jobs = {game_state.get("pending_jobs", 0)}')

        # Action accumulator
        lua.execute('_actions = {}')
        lua.execute('''
            function action(act)
                table.insert(_actions, act)
            end
        ''')

        return lua

    def compile_rules(self, rules: list[dict]) -> str:
        """Compile JSON behavior rules into a Lua script.

        Input:
            [
                {"if": "hp_pct < 20", "then": ["heal 15", "say 'ouch'"]},
                {"if": "player_distance <= 5", "then": ["move_toward_player"]},
                {"else": true, "then": ["patrol"]}
            ]

        Output:
            if hp_pct < 20 then
                action("heal 15")
                action("say 'ouch'")
            elseif player_distance <= 5 then
                action("move_toward_player")
            else
                action("patrol")
            end
        """
        if not rules:
            return '-- no behavior rules'

        lines = []
        for i, rule in enumerate(rules):
            actions = rule.get('then', [])
            if isinstance(actions, str):
                actions = [actions]

            if rule.get('else'):
                if i == 0:
                    lines.append('do')
                else:
                    lines.append('else')
            elif i == 0:
                condition = rule.get('if', 'true')
                condition = self._normalize_condition(condition)
                lines.append(f'if {condition} then')
            else:
                condition = rule.get('if', 'true')
                condition = self._normalize_condition(condition)
                lines.append(f'elseif {condition} then')

            for act in actions:
                # Escape any double quotes in the action string
                escaped = act.replace('\\', '\\\\').replace('"', '\\"')
                lines.append(f'    action("{escaped}")')

        lines.append('end')
        return '\n'.join(lines)

    def _normalize_condition(self, cond: str) -> str:
        """Normalize condition syntax for Lua.

        Handles:
            'has_flag quest_done' -> 'has_flag("quest_done")'
            'random 30' -> 'random(30)'
            'player_class MAGE' -> 'player_class == "MAGE"'
            'tile_at 5 3 == 1' -> 'tile_at(5, 3) == 1'
            'room_has_feature 5' -> 'room_has_feature(5)'
            'nearby_tile 5 > 3' -> 'nearby_tile(5) > 3'
        """
        cond = cond.strip()

        if cond.startswith('has_flag '):
            flag_name = cond[9:].strip()
            return f'has_flag("{flag_name}")'

        if cond.startswith('random '):
            pct = cond[7:].strip()
            return f'random({pct})'

        if cond.startswith('player_class '):
            cls = cond[13:].strip()
            return f'player_class == "{cls}"'

        # tile_at X Y == TILE
        import re
        m = re.match(r'tile_at\s+(\d+)\s+(\d+)\s*(.*)', cond)
        if m:
            return f'tile_at({m.group(1)}, {m.group(2)}) {m.group(3)}'

        # room_has_feature TILE
        m = re.match(r'room_has_feature\s+(\d+)(.*)', cond)
        if m:
            rest = m.group(2).strip()
            if rest:
                return f'room_has_feature({m.group(1)}) {rest}'
            return f'room_has_feature({m.group(1)})'

        # nearby_tile TILE > N
        m = re.match(r'nearby_tile\s+(\d+)\s*(.*)', cond)
        if m:
            return f'nearby_tile({m.group(1)}) {m.group(2)}'

        return cond

    def execute(self, sandbox: LuaRuntime, script: str) -> list[str]:
        """Execute compiled Lua in the sandbox, return action list."""
        sandbox.execute('_actions = {}')
        sandbox.execute(script)
        actions_table = sandbox.eval('_actions')

        results = []
        if actions_table:
            i = 1
            while True:
                val = actions_table[i]
                if val is None:
                    break
                results.append(str(val))
                i += 1
        return results

    def validate(self, script: str) -> tuple[bool, str]:
        """Syntax-check a Lua script without executing."""
        lua = LuaRuntime(unpack_returned_tuples=True)
        try:
            lua.execute(f'load([[\n{script}\n]])')
            return True, ""
        except Exception as e:
            return False, str(e)
