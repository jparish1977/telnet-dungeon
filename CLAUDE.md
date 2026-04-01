# Dungeon Crawler of Doom

## Project
Multiplayer telnet BBS dungeon crawler. Currently a single-file Python prototype — splitting it into proper modules is a priority. The language isn't locked to Python; a PHP backend is on the table, especially for web-facing pieces.

## Architecture
- `dungeon_server.py` - current monolith (4400+ lines, needs to be broken up)
- Target structure: server core, telnet protocol, websocket protocol, game engine, renderers, editors — each in their own module

## Key Design Decisions
- Pure asyncio, no threads - one event loop handles all connections
- Telnet protocol handled manually (IAC/WILL/DO/SB/SE) - no telnetlib
- ANSI escape codes for all rendering - cursor positioning, colors, backgrounds
- Game state is authoritative server-side - clients are dumb terminals
- Procedural floors use deterministic seeds so all players see the same dungeon
- Monster entities are world-level (shared across players), not per-session
- `get_char()` races user input against notification events for live multiplayer updates

## Conventions
- Floor numbers: -1 = overworld, 0+ = dungeon floors
- Tile codes: 0=floor, 1=wall, 2=door, 3=stairs down, 4=stairs up, 5=treasure, 6=fountain, 10-16=overworld terrain
- All persistent data is JSON files in the project directory
- Server binds 0.0.0.0 - accessible from any network interface

## Gotcha: Telnet Input
- Can't do interactive input on two sessions simultaneously (learned from PvP crash)
- `get_char` with `redraw_on_resize=True` returns 'RESIZE' on NAWS updates or notify events
- `get_input` with `preserve_spaces=True` keeps leading whitespace (for ASCII art)
- `get_input` with `prefill=` pre-populates the input buffer

## Future: WebSocket Frontend
The plan is to add a WebSocket layer that sends JSON game state to a Three.js web client.
Both telnet and web clients connect to the same World instance for cross-play.
The server should eventually be refactored to separate:
1. Game engine (world, combat, monsters, floors)
2. Protocol adapters (telnet ANSI, websocket JSON)
3. Renderers (ASCII for telnet, JSON state for web)
