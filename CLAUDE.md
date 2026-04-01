# Dungeon Crawler of Doom

## Project
Multiplayer telnet BBS dungeon crawler. Modular Python package with 18 modules, zero dependencies. The language isn't locked to Python; a PHP backend is on the table, especially for web-facing pieces.

## Architecture
- `dungeon_server.py` — thin entry point + GameSession shell (~290 lines)
- `dungeon/` — game engine package, fully extracted from the original monolith
- Protocol adapter pattern: `protocol/base.py` defines the interface, `telnet.py` and `stdio.py` implement it
- All game logic talks to sessions through the adapter — transport is swappable

### Module Map
- **Data**: `config.py`, `items.py`, `persistence.py` — constants, game data, JSON I/O
- **Engine**: `floor.py`, `monsters.py`, `character.py`, `world.py` — game state and logic
- **Combat**: `combat.py` — PvE, PvP, death handling
- **UI flows**: `menus.py`, `shop.py`, `session.py` — player-facing flows
- **Rendering**: `renderer_3d.py`, `renderer_minimap.py` — pure functions, string in/string out
- **Protocol**: `protocol/base.py`, `protocol/telnet.py`, `protocol/stdio.py` — I/O adapters
- **GM tools**: `gm/tools.py` — player admin, monster/map/theme editors

## Key Design Decisions
- Pure asyncio, no threads — one event loop handles all connections
- Telnet protocol handled manually (IAC/WILL/DO/SB/SE) — no telnetlib
- Protocol adapter abstraction: game code never touches raw bytes
- ANSI escape codes for all rendering — cursor positioning, colors, backgrounds
- Game state is authoritative server-side — clients are dumb terminals
- Procedural floors use deterministic seeds so all players see the same dungeon
- Monster entities are world-level (shared across players), not per-session
- `get_char()` races user input against notification events for live multiplayer updates
- Death respawns on same floor (stairs-up), not overworld

## Conventions
- Floor numbers: -1 = overworld, 0+ = dungeon floors
- Tile codes: 0=floor, 1=wall, 2=door, 3=stairs down, 4=stairs up, 5=treasure, 6=fountain, 10-16=overworld terrain
- All persistent data is JSON files in the project directory
- Server binds 0.0.0.0 — accessible from any network interface
- Standalone functions take `session` as first arg (not methods on GameSession)
- Renderer functions are pure: data in, strings out — no I/O side effects

## Gotcha: Telnet Input
- Can't do interactive input on two sessions simultaneously (learned from PvP crash)
- `get_char` with `redraw_on_resize=True` returns 'RESIZE' on NAWS updates or notify events
- `get_input` with `preserve_spaces=True` keeps leading whitespace (for ASCII art)
- `get_input` with `prefill=` pre-populates the input buffer

## Future
- WebSocket protocol adapter for Three.js web client (cross-play with telnet)
- HTTP status API on a second port (JSON game state for monitoring/tooling)
- Server federation: dungeon entrances as inter-server portals, player handoff via JSON
- Split `gm/tools.py` (~1000 lines) into sub-modules
