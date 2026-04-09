"""Telnet protocol adapter — ANSI terminal I/O over raw telnet."""

import asyncio

from dungeon.config import IAC, WILL, WONT, DO, DONT, SB, SE, ECHO, SGA, NAWS
from dungeon.protocol.base import ProtocolAdapter


class TelnetAdapter(ProtocolAdapter):
    """Handles telnet protocol: IAC negotiation, NAWS, ANSI cursor, character-at-a-time input."""

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self._term_width = 80
        self._term_height = 24
        self._resized = False
        self.notify_event = asyncio.Event()
        self.running = True
        self._leftover = None  # byte pushed back by get_char's newline drain

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

    async def _read1(self, timeout=300):
        """Read one byte, returning any leftover from get_char's newline drain first."""
        if self._leftover is not None:
            b = self._leftover
            self._leftover = None
            return b
        return await asyncio.wait_for(self.reader.read(1), timeout=timeout)

    async def send(self, text: str):
        text = text.replace('\r\n', '\n').replace('\n', '\r\n')
        self.writer.write(text.encode('utf-8'))
        await self.writer.drain()

    async def send_line(self, text: str = ""):
        await self.send(text + "\r\n")

    async def move_to(self, row: int, col: int):
        self.writer.write(f"\033[{row};{col}H".encode('utf-8'))
        await self.writer.drain()

    async def clear_row(self, row: int):
        await self.move_to(row, 1)
        self.writer.write(b"\033[2K")
        await self.writer.drain()

    def _parse_naws(self, data):
        """Parse NAWS subnegotiation data to get terminal width/height."""
        if len(data) >= 4:
            w = (data[0] << 8) | data[1]
            h = (data[2] << 8) | data[3]
            w = max(40, min(200, w))
            h = max(16, min(80, h))
            if w != self._term_width or h != self._term_height:
                self._term_width = w
                self._term_height = h
                self._resized = True

    async def _read_subnegotiation(self):
        """Read IAC subnegotiation data until IAC SE."""
        sb_option = await self.reader.read(1)
        sb_data = bytearray()
        while True:
            sb = await self.reader.read(1)
            if sb == IAC:
                se = await self.reader.read(1)
                if se == SE:
                    break
                sb_data.append(sb[0])
            else:
                sb_data.append(sb[0])
        if sb_option == NAWS:
            self._parse_naws(sb_data)

    async def _handle_iac(self):
        """Handle an IAC command sequence. Returns True if handled."""
        cmd = await self.reader.read(1)
        if cmd in (WILL, WONT, DO, DONT):
            await self.reader.read(1)  # option byte
        elif cmd == SB:
            await self._read_subnegotiation()

    async def get_input(self, prompt: str = "> ", preserve_spaces=False, prefill="") -> str:
        await self.send(prompt)
        if prefill:
            await self.send(prefill)
            data = prefill.encode('utf-8')
        else:
            data = b""

        while True:
            try:
                byte = await self._read1(timeout=300)
            except asyncio.TimeoutError:
                await self.send_line("\r\nConnection timed out. Farewell!")
                self.running = False
                return ""
            if not byte:
                self.running = False
                return ""

            if byte == IAC:
                await self._handle_iac()
                continue

            # Backspace
            if byte in (b'\x7f', b'\x08'):
                if data:
                    data = data[:-1]
                    await self.send('\b \b')
                continue

            # Enter
            if byte in (b'\r', b'\n'):
                if byte == b'\r':
                    try:
                        next_byte = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                        if next_byte != b'\n':
                            data += next_byte
                    except asyncio.TimeoutError:
                        pass
                # Ignore stale \r\n left in buffer from a previous get_char call
                if not data:
                    continue
                await self.send("\r\n")
                result = data.decode('utf-8', errors='ignore')
                return result.rstrip() if preserve_spaces else result.strip()

            # Arrow keys -> wasd
            if byte == b'\x1b':
                try:
                    seq1 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                    if seq1 == b'[':
                        seq2 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                        if seq2 == b'A':
                            return 'w'
                        elif seq2 == b'B':
                            return 's'
                        elif seq2 == b'C':
                            return 'd'
                        elif seq2 == b'D':
                            return 'a'
                except asyncio.TimeoutError:
                    pass
                continue

            # Regular character
            if 32 <= byte[0] < 127:
                data += byte
                await self.send(byte.decode('utf-8', errors='ignore'))

        result = data.decode('utf-8', errors='ignore')
        return result.rstrip() if preserve_spaces else result.strip()

    async def get_char(self, prompt: str = "", redraw_on_resize=False) -> str:
        if prompt:
            await self.send(prompt)
        self._resized = False
        self.notify_event.clear()

        while True:
            read_task = asyncio.ensure_future(self.reader.read(1))
            notify_task = asyncio.ensure_future(self.notify_event.wait())
            try:
                done, pending = await asyncio.wait(
                    [read_task, notify_task],
                    timeout=300,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                read_task.cancel()
                notify_task.cancel()
                return ''

            for task in pending:
                task.cancel()

            if not done:
                return ''

            # Notification won (chat/broadcast arrived)
            if notify_task in done:
                if redraw_on_resize:
                    self.notify_event.clear()
                    if read_task not in done:
                        return 'RESIZE'

            if read_task not in done:
                continue

            try:
                byte = read_task.result()
            except Exception:
                self.running = False
                return ''
            if not byte:
                self.running = False
                return ''

            if byte == IAC:
                await self._handle_iac()
                continue

            if self._resized and redraw_on_resize:
                self._resized = False
                return 'RESIZE'

            # Arrow keys
            if byte == b'\x1b':
                try:
                    seq1 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                    if seq1 == b'[':
                        seq2 = await asyncio.wait_for(self.reader.read(1), timeout=0.1)
                        if seq2 == b'A':
                            return 'w'
                        elif seq2 == b'B':
                            return 's'
                        elif seq2 == b'C':
                            return 'd'
                        elif seq2 == b'D':
                            return 'a'
                except asyncio.TimeoutError:
                    pass
                continue

            if byte in (b'\r', b'\n'):
                return '\r'
            if 32 <= byte[0] < 127:
                # Drain trailing \r/\n from line-mode telnet clients
                for _ in range(2):
                    try:
                        peek = await asyncio.wait_for(self.reader.read(1), timeout=0.05)
                        if peek not in (b'\r', b'\n'):
                            # Real data — leave it for the next read by storing it
                            self._leftover = peek
                            break
                    except asyncio.TimeoutError:
                        break
                return byte.decode('utf-8', errors='ignore')

        return ''

    async def _query_terminal_size(self):
        """Fallback: query terminal size via ANSI cursor position report.
        Works on terminals that don't support NAWS (e.g. Git Bash/mintty)."""
        # Save cursor, move to bottom-right corner, request cursor position, restore
        self.writer.write(b"\0337\033[999;999H\033[6n\0338")
        await self.writer.drain()
        # Read response: ESC [ rows ; cols R
        buf = b""
        try:
            while True:
                b = await asyncio.wait_for(self.reader.read(1), timeout=0.5)
                if not b:
                    break
                buf += b
                if b == b'R':
                    break
        except asyncio.TimeoutError:
            return
        # Parse \033[rows;colsR
        resp = buf.decode('ascii', errors='ignore')
        start = resp.find('\033[')
        if start == -1 or not resp.endswith('R'):
            return
        inner = resp[start + 2:-1]  # "rows;cols"
        parts = inner.split(';')
        if len(parts) == 2:
            try:
                h, w = int(parts[0]), int(parts[1])
                w = max(40, min(200, w))
                h = max(16, min(80, h))
                self._term_width = w
                self._term_height = h
            except ValueError:
                pass

    async def negotiate(self):
        """Perform telnet negotiation: enable echo, SGA, request NAWS."""
        self.writer.write(IAC + WILL + ECHO)
        self.writer.write(IAC + WILL + SGA)
        self.writer.write(IAC + DO + NAWS)
        await self.writer.drain()

        # Give client time to respond with NAWS
        await asyncio.sleep(0.3)
        try:
            while True:
                byte = await asyncio.wait_for(self.reader.read(1), timeout=0.2)
                if not byte:
                    break
                if byte == IAC:
                    await self._handle_iac()
        except asyncio.TimeoutError:
            pass

        # If NAWS didn't work (still at defaults), try ANSI cursor position query
        if self._term_width == 80 and self._term_height == 24:
            await self._query_terminal_size()

    async def close(self):
        try:
            self.writer.close()
        except Exception:
            pass
