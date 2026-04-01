"""Abstract scripting backend interface.

The behavior engine compiles JSON rules into scripts and evaluates them
in a sandbox. This interface allows different scripting languages
(Lua, Python, PHP, etc.) to be plugged in.
"""

from abc import ABC, abstractmethod


class ScriptingBackend(ABC):
    """What the behavior engine needs from a scripting language."""

    @abstractmethod
    def create_sandbox(self, game_state: dict) -> object:
        """Create a sandboxed execution environment with game state exposed.

        game_state contains:
            mob: dict — the monster/NPC being evaluated
            players: list[dict] — nearby players [{name, x, y, hp, max_hp, class, ...}]
            floor_num: int — current floor
            flags: dict — quest/world flags

        Returns an opaque sandbox handle used by execute().
        """
        ...

    @abstractmethod
    def compile_rules(self, rules: list[dict]) -> str:
        """Compile JSON behavior rules into a script string.

        Each rule is {"if": "condition", "then": ["action1", "action2"]}
        or {"else": true, "then": ["action1"]}.

        Returns the script source code as a string.
        """
        ...

    @abstractmethod
    def execute(self, sandbox: object, script: str) -> list[str]:
        """Execute a compiled script in the sandbox.

        Returns a list of action strings to perform, e.g.:
            ["attack", "poison 30"]
            ["move_toward_player"]
            ["say 'hello'", "set_flag quest_started"]
        """
        ...

    @abstractmethod
    def validate(self, script: str) -> tuple[bool, str]:
        """Check a script for syntax errors without executing.

        Returns (ok, error_message). error_message is "" if ok.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend (e.g. 'Lua 5.4')."""
        ...
