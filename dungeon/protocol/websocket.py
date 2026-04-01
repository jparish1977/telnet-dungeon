"""WebSocket protocol adapter — sends JSON game state to web clients.

Implements WebSocket framing (RFC 6455) with zero dependencies.
The web client receives structured game state instead of ANSI strings.
"""

import asyncio
import base64
import hashlib
import json
import struct

from dungeon.protocol.base import ProtocolAdapter


# WebSocket opcodes
_OP_TEXT = 0x1
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA

# WebSocket magic GUID for handshake
_WS_GUID = "258EAFA5-E914-47DA-95CA-5AB5E0B45CF3"


class WebSocketAdapter(ProtocolAdapter):
    """Protocol adapter for web clients via WebSocket.

    Instead of ANSI rendering, sends JSON messages:
        {"type": "screen", "data": {...game state...}}
        {"type": "prompt", "text": "Your choice: "}
        {"type": "message", "text": "..."}

    Receives JSON commands:
        {"type": "input", "text": "w"}
        {"type": "char", "char": "a"}
    """

    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer
        self._term_width = 120
        self._term_height = 40
        self._resized = False
        self.notify_event = asyncio.Event()
        self.running = True
        self._input_queue = asyncio.Queue()
        self._recv_task = None
        self._handshake_done = False

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

    async def _ws_send(self, data: str):
        """Send a WebSocket text frame."""
        try:
            payload = data.encode('utf-8')
            length = len(payload)

            if length < 126:
                header = struct.pack('!BB', 0x81, length)
            elif length < 65536:
                header = struct.pack('!BBH', 0x81, 126, length)
            else:
                header = struct.pack('!BBQ', 0x81, 127, length)

            self.writer.write(header + payload)
            await self.writer.drain()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            self.running = False

    async def _ws_recv(self) -> str | None:
        """Receive a WebSocket text frame. Returns None on close/error."""
        try:
            first_two = await self.reader.readexactly(2)
        except (asyncio.IncompleteReadError, ConnectionError):
            return None

        opcode = first_two[0] & 0x0F
        masked = bool(first_two[1] & 0x80)
        length = first_two[1] & 0x7F

        if length == 126:
            raw = await self.reader.readexactly(2)
            length = struct.unpack('!H', raw)[0]
        elif length == 127:
            raw = await self.reader.readexactly(8)
            length = struct.unpack('!Q', raw)[0]

        if masked:
            mask_key = await self.reader.readexactly(4)

        payload = await self.reader.readexactly(length)

        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        if opcode == _OP_CLOSE:
            return None
        if opcode == _OP_PING:
            # Send pong
            pong = struct.pack('!BB', 0x80 | _OP_PONG, len(payload)) + payload
            self.writer.write(pong)
            await self.writer.drain()
            return await self._ws_recv()

        return payload.decode('utf-8', errors='replace')

    async def _recv_loop(self):
        """Background task: receive WebSocket messages and queue them."""
        try:
            while self.running:
                msg = await self._ws_recv()
                if msg is None:
                    self.running = False
                    await self._input_queue.put(None)
                    break
                try:
                    data = json.loads(msg)
                    if data.get('type') == 'resize':
                        w = max(40, min(200, data.get('width', 120)))
                        h = max(16, min(80, data.get('height', 40)))
                        if w != self._term_width or h != self._term_height:
                            self._term_width = w
                            self._term_height = h
                            self._resized = True
                            self.notify_event.set()
                    else:
                        await self._input_queue.put(data)
                except json.JSONDecodeError:
                    await self._input_queue.put({'type': 'char', 'char': msg})
        except Exception as e:
            print(f"[WS] recv_loop error: {e}")
            self.running = False
            await self._input_queue.put(None)

    async def _send_json(self, msg_type: str, **kwargs):
        """Send a typed JSON message to the client."""
        msg = {'type': msg_type, **kwargs}
        await self._ws_send(json.dumps(msg))

    async def send(self, text: str):
        # Normalize line endings and send as ANSI text
        text = text.replace('\r\n', '\n').replace('\n', '\r\n')
        await self._send_json('text', text=text)

    async def send_line(self, text: str = ""):
        await self._send_json('text', text=text + '\r\n')

    async def move_to(self, row: int, col: int):
        # Send as ANSI escape code so the terminal renderer handles it
        await self._send_json('text', text=f'\033[{row};{col}H')

    async def clear_row(self, row: int):
        await self._send_json('text', text=f'\033[{row};1H\033[2K')

    async def get_input(self, prompt: str = "> ", preserve_spaces=False, prefill="") -> str:
        await self._send_json('prompt', text=prompt, mode='line', prefill=prefill)
        while True:
            try:
                data = await asyncio.wait_for(self._input_queue.get(), timeout=300)
            except asyncio.TimeoutError:
                self.running = False
                return ""
            if data is None:
                self.running = False
                return ""
            if data.get('type') in ('input', 'char'):
                result = data.get('text', data.get('char', ''))
                return result.rstrip() if preserve_spaces else result.strip()

    async def get_char(self, prompt: str = "", redraw_on_resize=False) -> str:
        if prompt:
            await self._send_json('prompt', text=prompt, mode='char')

        self._resized = False
        self.notify_event.clear()

        while True:
            # Race input vs notification
            input_task = asyncio.ensure_future(self._input_queue.get())
            notify_task = asyncio.ensure_future(self.notify_event.wait())

            try:
                done, pending = await asyncio.wait(
                    [input_task, notify_task],
                    timeout=300,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError:
                input_task.cancel()
                notify_task.cancel()
                return ''

            for task in pending:
                task.cancel()

            if not done:
                return ''

            if notify_task in done:
                if redraw_on_resize:
                    self.notify_event.clear()
                    if input_task not in done:
                        return 'RESIZE'

            if input_task not in done:
                continue

            data = input_task.result()
            if data is None:
                self.running = False
                return ''

            char = data.get('char', data.get('text', ''))
            if char:
                return char[0] if len(char) == 1 else char

        return ''

    async def negotiate(self):
        """Perform WebSocket HTTP upgrade handshake."""
        if self._handshake_done:
            return  # already handled externally (e.g. by handle_web_client)
        # Read HTTP request line-by-line to avoid over-reading into WS frames
        request_lines = []
        while True:
            try:
                line = await asyncio.wait_for(self.reader.readline(), timeout=10)
            except asyncio.TimeoutError:
                self.running = False
                return
            if not line:
                self.running = False
                return
            request_lines.append(line.decode('utf-8', errors='replace').rstrip('\r\n'))
            if line == b'\r\n' or line == b'\n':
                break  # end of HTTP headers

        # Parse headers
        headers = {}
        for line in request_lines[1:]:  # skip GET line
            if ':' in line:
                key, val = line.split(':', 1)
                headers[key.strip().lower()] = val.strip()

        # Verify this is a WebSocket upgrade
        if 'sec-websocket-key' not in headers:
            # Not a WS request - send 400 and bail
            self.writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\nNot a WebSocket request\r\n")
            await self.writer.drain()
            self.running = False
            return

        # Compute accept key
        ws_key = headers['sec-websocket-key']
        accept = base64.b64encode(
            hashlib.sha1((ws_key + _WS_GUID).encode()).digest()
        ).decode()

        # Send upgrade response
        origin = headers.get('origin', '*')
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            f"Access-Control-Allow-Origin: {origin}\r\n"
            "\r\n"
        )
        self.writer.write(response.encode())
        await self.writer.drain()

        print(f"[WS] Handshake complete, origin={origin}")

        # Start background receiver
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def close(self):
        if self._recv_task:
            self._recv_task.cancel()
        try:
            # Send close frame
            self.writer.write(struct.pack('!BB', 0x88, 0))
            await self.writer.drain()
            self.writer.close()
        except Exception:
            pass
