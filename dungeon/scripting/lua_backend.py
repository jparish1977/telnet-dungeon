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
