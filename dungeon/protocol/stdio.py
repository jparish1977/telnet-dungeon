"""Local stdio adapter — play in a regular terminal, no telnet needed.

Uses ANSI escape codes just like the telnet adapter, but reads/writes
directly from stdin/stdout. Single-player only (no network).
"""

import asyncio
import os
import sys

from dungeon.protocol.base import ProtocolAdapter


class StdioAdapter(ProtocolAdapter):
    """Protocol adapter for local terminal play via stdin/stdout."""

    def __init__(self):
        self._term_width = 80
        self._term_height = 24
        self._resized = False
        self.notify_event = asyncio.Event()
        self.running = True
        self._detect_terminal_size()

    def _detect_terminal_size(self):
        try:
            cols, rows = os.get_terminal_size()
            self._term_width = max(40, min(200, cols))
            self._term_height = max(16, min(80, rows))
        except OSError:
            pass

    def _check_resize(self):
        """Poll terminal size and set resized flag if it changed."""
        try:
            cols, rows = os.get_terminal_size()
            cols = max(40, min(200, cols))
            rows = max(16, min(80, rows))
            if cols != self._term_width or rows != self._term_height:
                self._term_width = cols
                self._term_height = rows
                self._resized = True
        except OSError:
            pass

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

    async def send(self, text: str):
        sys.stdout.write(text)
        sys.stdout.flush()

    async def send_line(self, text: str = ""):
        sys.stdout.write(text + "\n")
        sys.stdout.flush()

    async def move_to(self, row: int, col: int):
        sys.stdout.write(f"\033[{row};{col}H")
        sys.stdout.flush()

    async def clear_row(self, row: int):
        await self.move_to(row, 1)
        sys.stdout.write("\033[2K")
        sys.stdout.flush()

    async def get_input(self, prompt: str = "> ", preserve_spaces=False, prefill="") -> str:
        sys.stdout.write(prompt)
        if prefill:
            sys.stdout.write(prefill)
        sys.stdout.flush()

        loop = asyncio.get_event_loop()
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            self.running = False
            return ""
        result = line.rstrip('\n').rstrip('\r')
        if prefill:
            result = prefill + result
        return result.rstrip() if preserve_spaces else result.strip()

    async def get_char(self, prompt: str = "", redraw_on_resize=False) -> str:
        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()

        # Check for terminal resize before reading input
        self._check_resize()
        if self._resized and redraw_on_resize:
            self._resized = False
            return 'RESIZE'

        loop = asyncio.get_event_loop()

        if sys.platform == 'win32':
            char = await loop.run_in_executor(None, self._read_char_windows)
        else:
            char = await loop.run_in_executor(None, self._read_char_unix)

        if not char:
            self.running = False
            return ''
        return char

    @staticmethod
    def _read_char_windows() -> str:
        import msvcrt
        byte = msvcrt.getwch()
        if byte in ('\r', '\n'):
            return '\r'
        # Arrow keys on Windows: msvcrt returns '\xe0' or '\x00' then the scan code
        if byte in ('\xe0', '\x00'):
            scan = msvcrt.getwch()
            if scan == 'H':
                return 'w'  # up
            elif scan == 'P':
                return 's'  # down
            elif scan == 'K':
                return 'a'  # left
            elif scan == 'M':
                return 'd'  # right
            return ''
        return byte

    @staticmethod
    def _read_char_unix() -> str:
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == '\x1b':
                seq = sys.stdin.read(2)
                if seq == '[A':
                    return 'w'
                elif seq == '[B':
                    return 's'
                elif seq == '[C':
                    return 'd'
                elif seq == '[D':
                    return 'a'
                return ''
            if ch in ('\r', '\n'):
                return '\r'
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    async def negotiate(self):
        self._detect_terminal_size()

    async def close(self):
        pass
