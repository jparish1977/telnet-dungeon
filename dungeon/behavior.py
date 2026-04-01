"""Behavior engine — evaluates JSON behavior rules for monsters and NPCs.

Compiles rules to Lua (or other backend), evaluates against game state,
returns action strings for the game engine to execute.
"""

from dungeon.scripting.base import ScriptingBackend
from dungeon.scripting.lua_backend import LuaBackend

# Default backend — swappable
_backend: ScriptingBackend = LuaBackend()

# Cache compiled scripts: hash of rules -> script string
_script_cache: dict[str, str] = {}


def set_backend(backend: ScriptingBackend):
    """Swap the scripting backend (e.g. for testing or PHP sandbox)."""
    global _backend
    _backend = backend
    _script_cache.clear()


def get_backend() -> ScriptingBackend:
    """Get the current scripting backend."""
    return _backend


def _cache_key(rules: list[dict]) -> str:
    """Stable cache key for a rule set."""
    import json
    return json.dumps(rules, sort_keys=True)


def compile_behavior(rules: list[dict]) -> str:
    """Compile JSON rules to a script. Cached."""
    key = _cache_key(rules)
    if key not in _script_cache:
        _script_cache[key] = _backend.compile_rules(rules)
    return _script_cache[key]


def evaluate_behavior(mob: dict, players: list[dict],
                      floor_num: int = 0, flags: dict = None,
                      ally_count: int = 0) -> list[str]:
    """Evaluate a mob's behavior rules and return actions to perform.

    Args:
        mob: monster/NPC dict (must have 'behavior' key with rules list)
        players: nearby player dicts [{name, x, y, hp, max_hp, class, ...}]
        floor_num: current floor number
        flags: quest/world flags dict
        ally_count: number of alive allies on this floor

    Returns:
        list of action strings, e.g. ["attack", "poison 30"]
        Empty list if mob has no behavior rules.
    """
    rules = mob.get('behavior')
    if not rules:
        return []

    script = compile_behavior(rules)

    game_state = {
        'mob': mob,
        'players': players,
        'floor_num': floor_num,
        'flags': flags or {},
        'ally_count': ally_count,
    }

    sandbox = _backend.create_sandbox(game_state)
    return _backend.execute(sandbox, script)


def validate_behavior(rules: list[dict]) -> tuple[bool, str]:
    """Validate behavior rules without executing.

    Returns (ok, error_message).
    """
    script = _backend.compile_rules(rules)
    return _backend.validate(script)
