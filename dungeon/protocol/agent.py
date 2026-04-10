"""Agent protocol adapter — programmatic control for LLM-driven agents.

No terminal, no ANSI. Commands go in as method calls, game state comes
back as structured dicts. The agent drives a GameSession the same way
a human does — through the protocol adapter interface.
"""

import asyncio

from dungeon.protocol.base import ProtocolAdapter


class AgentAdapter(ProtocolAdapter):
    """Protocol adapter for programmatic (non-human) session control.

    Usage::

        adapter = AgentAdapter()
        session = GameSession(adapter=adapter)

        # Queue a keypress before the game loop reads it
        adapter.inject_char('w')          # move forward
        adapter.inject_input('Architect') # line input (character name, etc.)

        # The game's get_char()/get_input() calls will consume from the queue.
        # All ANSI output is captured but discarded — read state directly
        # from session.char, get_floor(), etc.
    """

    def __init__(self, term_width=120, term_height=40):
        self._term_width = term_width
        self._term_height = term_height
        self._resized = False
        self.notify_event = asyncio.Event()
        self.running = True

        # Queues for feeding input to the game engine
        self._char_queue: asyncio.Queue[str] = asyncio.Queue()
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()

        # Captured output (optional — mostly ignored, but useful for debug)
        self._output_lines: list[str] = []
        self._capture_output = False

    # ── Injecting input (agent → game) ───────────────────────────

    def inject_char(self, ch: str):
        """Queue a single keypress for the next get_char() call."""
        self._char_queue.put_nowait(ch)

    def inject_input(self, line: str):
        """Queue a line of text for the next get_input() call."""
        self._input_queue.put_nowait(line)

    async def wait_for_char_consumed(self, timeout: float = 5.0):
        """Wait until the char queue is empty (game consumed the input)."""
        for _ in range(int(timeout * 20)):
            if self._char_queue.empty():
                return True
            await asyncio.sleep(0.05)
        return False

    async def wait_for_input_consumed(self, timeout: float = 5.0):
        """Wait until the input queue is empty."""
        for _ in range(int(timeout * 20)):
            if self._input_queue.empty():
                return True
            await asyncio.sleep(0.05)
        return False

    # ── ProtocolAdapter interface (game → adapter) ───────────────

    async def send(self, text: str):
        if self._capture_output:
            self._output_lines.append(text)

    async def send_line(self, text: str = ""):
        if self._capture_output:
            self._output_lines.append(text + "\n")

    async def move_to(self, row: int, col: int):
        pass  # no cursor in agent mode

    async def clear_row(self, row: int):
        pass

    async def get_input(self, prompt: str = "> ", preserve_spaces=False, prefill="") -> str:
        line = await self._input_queue.get()
        if prefill:
            line = prefill + line
        return line.rstrip() if preserve_spaces else line.strip()

    async def get_char(self, prompt: str = "", redraw_on_resize=False) -> str:
        # Yield control so the agent loop can inject chars
        ch = await self._char_queue.get()
        return ch

    async def negotiate(self):
        pass  # no handshake needed

    async def close(self):
        self.running = False

    @property
    def term_width(self) -> int:
        return self._term_width

    @property
    def term_height(self) -> int:
        return self._term_height

    @property
    def resized(self) -> bool:
        return self._resized

    @resized.setter
    def resized(self, value: bool):
        self._resized = value
