"""Abstract protocol adapter interface.

All game code communicates with clients through this interface.
Concrete implementations handle the transport details (telnet ANSI,
WebSocket JSON, etc.).
"""

import asyncio
from abc import ABC, abstractmethod


class ProtocolAdapter(ABC):
    """What the game engine needs from a client connection."""

    @abstractmethod
    async def send(self, text: str):
        """Send text to the client."""
        ...

    @abstractmethod
    async def send_line(self, text: str = ""):
        """Send text followed by a newline."""
        ...

    @abstractmethod
    async def move_to(self, row: int, col: int):
        """Move cursor to absolute position (1-based)."""
        ...

    @abstractmethod
    async def clear_row(self, row: int):
        """Clear a specific row."""
        ...

    @abstractmethod
    async def get_input(self, prompt: str = "> ", preserve_spaces=False, prefill="") -> str:
        """Read a line of input from the client."""
        ...

    @abstractmethod
    async def get_char(self, prompt: str = "", redraw_on_resize=False) -> str:
        """Get a single character without waiting for enter.
        Returns 'RESIZE' when terminal resizes or notifications arrive
        (if redraw_on_resize=True)."""
        ...

    @abstractmethod
    async def negotiate(self):
        """Perform initial connection handshake/negotiation."""
        ...

    @abstractmethod
    async def close(self):
        """Close the connection."""
        ...

    @property
    @abstractmethod
    def term_width(self) -> int:
        ...

    @property
    @abstractmethod
    def term_height(self) -> int:
        ...

    @property
    @abstractmethod
    def resized(self) -> bool:
        ...

    @resized.setter
    @abstractmethod
    def resized(self, value: bool):
        ...

    # Notification event for multiplayer updates (chat, broadcasts)
    notify_event: asyncio.Event
