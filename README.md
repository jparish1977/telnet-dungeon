# Dungeon Crawler of Doom

A multiplayer dungeon crawler you play over telnet. Pure Python 3, zero dependencies.

Born from a stray thought while chatting with a teenager who was building a telnet BBS. Six or seven hours later, this existed — first-person ASCII dungeons, wandering monsters, co-op combat, PvP, and a GM toolkit, all running on the same protocol people used to dial into bulletin boards in the '90s.

Telnet-first by design. A Three.js web frontend is planned for cross-play, but the terminal is home.

## Quick Start

```bash
# Start the telnet server (no dependencies needed - pure Python 3)
python dungeon_server.py [port]

# Default port is 2323
python dungeon_server.py

# Connect via telnet
telnet localhost 2323

# Or play locally in your terminal — no telnet needed
python dungeon_server.py --local
```

## Architecture

```
                    +------------------+
                    |   Game Server    |
                    |  (Python/asyncio)|
                    |                  |
                    |  World State     |
                    |  Monster AI      |
                    |  Combat Engine   |
                    |  Floor Gen       |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
     +--------v--------+         +---------v---------+
     | Telnet Protocol  |         |  WebSocket API    |
     | Raw ANSI/ASCII   |         |  JSON messages    |
     | Port 2323        |         |  Port 8080        |
     +--------+---------+         +---------+---------+
              |                             |
     +--------v--------+         +---------v---------+
     | Telnet Client    |         |  Web Frontend     |
     | (any terminal)   |         |  Three.js 3D      |
     |                  |         |  HTML/CSS/JS       |
     +------------------+         +-------------------+
```

### Cross-play Design

Both frontends connect to the same game server and share the same world state. The server is authoritative - all game logic runs server-side. Frontends are just views.

**Telnet clients** get the ASCII/ANSI rendered view we have now.
**Web clients** get JSON game state and render it with Three.js in real 3D.

A telnet player and a web player can be in the same dungeon, chat, PvP, and co-op together.

## Features (POC - Current)

### Gameplay
- First-person ASCII 3D dungeon view with colored walls, textured bricks, perspective ground/sky
- Procedural overworld (128x128) with terrain: grass, forest, mountains, water, roads, towns
- Infinite procedural dungeon floors (16x16 to 256x256, scaling with depth)
- 3 hand-crafted starting dungeon floors
- Turn-based combat with Attack, Spells, Potions, Flee
- 4 character classes: Fighter, Mage, Thief, Cleric
- 5 spells: Heal, Fireball, Shield, Lightning, Cure
- 6 weapon tiers and 6 armor tiers
- Leveling system with stat gains and spell learning
- Visible wandering monsters with aggro AI (chase within 5 tiles)
- Monster ASCII art rendered in the 3D viewport (scales with distance)
- Treasure chests, fountains (heal/mana/poison/dry up)
- Poison system with natural wear-off chance
- Per-floor color themes (7 built-in + customizable)

### Multiplayer
- Multiple simultaneous players in shared world
- See other players on minimap (green initials)
- Direction indicators for distant players on same floor
- Real-time chat (T key) with instant delivery via async notifications
- Co-op combat (allies on same tile auto-attack, XP/gold shared)
- PvP combat (P key, defender auto-fights, winner takes 25% gold)
- PvP death: respawn with trash talk, no permadeath
- Join/leave/kill announcements broadcast to all
- Duplicate login prevention

### Game Modes
- **Normal**: Respawn on death at overworld town, lose 20% gold
- **Hardcore**: Permadeath, save deleted on death, +50% XP and gold

### GM/Admin System
- GM login with password (default: "dungeon", set via DUNGEON_GM_PASS env var)
- Teleport to/summon players
- Edit player stats, inventory, location
- Kick and ban players (persisted to banned.json)
- Broadcast messages
- Teleport to any floor
- **Monster Editor**: Create custom monsters with stats and ASCII art, edit built-in monsters, spawn monsters, grid-based art editor with plot/insert/line editing
- **Map Tile Editor**: Full-screen visual editor with cursor, WASD movement, brush palette, flood fill, grid resize (8-256), auto-scrolling camera
- **Viewport Theme Editor**: Per-floor color customization for walls, floors, ceilings, backgrounds

### Technical
- Pure Python 3, zero dependencies
- Async telnet server (asyncio)
- NAWS terminal size detection + resize redraw
- Aspect-ratio-aware viewport scaling
- Single-keypress controls (no enter needed)
- Character persistence (JSON save files)
- Deterministic procedural generation (same seed = same floor)
- Monster stat scaling for infinite depth
- Save file sanitization (prevents tampering/overflow)
- Floor limit: 99,999

## File Structure

```
telnet-dungeon/
  dungeon_server.py              # Entry point + thin GameSession shell (~290 lines)
  dungeon/                       # Game engine package (18 modules)
    config.py                    # Constants, ANSI colors, tile codes
    items.py                     # Weapons, armor, spells, character classes
    persistence.py               # All JSON file I/O (saves, bans, themes)
    floor.py                     # Dungeon generation, overworld, caching
    monsters.py                  # Monster definitions, scaling, wandering AI
    character.py                 # Stat validation, leveling helpers
    combat.py                    # PvE combat, PvP duels, death handling
    shop.py                      # Shop interaction + town teleport
    menus.py                     # Title screen, character creation/loading
    session.py                   # Main game loop, screen rendering
    world.py                     # Shared world state, player registry
    renderer_3d.py               # First-person 3D viewport engine
    renderer_minimap.py          # Minimap renderer
    protocol/
      base.py                    # Abstract protocol adapter interface
      telnet.py                  # Telnet I/O (IAC, NAWS, ANSI)
      stdio.py                   # Local terminal adapter (--local mode)
    gm/
      tools.py                   # GM tools (player admin, editors)
  saves/                         # Character save files (JSON)
  custom_floors/                 # GM-edited floor overrides (JSON)
  quests/                        # Quest definitions (JSON)
  builtin_overrides.json         # Edited built-in monster stats/art
  custom_monsters.json           # GM-created custom monsters
  scene_themes.json              # Per-floor viewport color themes
```

## Roadmap

### v1.0 - Polish the Telnet Experience
- [ ] In-viewport combat (no screen clear, fight in the log panel)
- [ ] More overworld content (NPCs, quests, random events)
- [ ] Inventory system (carry multiple items, equip slots)
- [ ] Party system (formal groups, shared XP radius)
- [ ] Better procedural dungeons (themed rooms, traps, secret doors)
- [ ] Sound cues via terminal bell
- [ ] Terminal protocol negotiation (TTYPE, MCCP, 256-color)
- [ ] HTTP status API (JSON game state on a second port for monitoring)

### v2.0 - Web Frontend (Three.js)
- [ ] WebSocket protocol adapter (same ProtocolAdapter interface as telnet)
- [ ] JSON game state API (player state, visible tiles, monsters, chat)
- [ ] Three.js renderer:
  - Actual 3D first-person dungeon (walls, floors, ceilings as geometry)
  - Monster sprites as billboarded textures
  - Dynamic lighting (torches, spells)
  - Particle effects (combat, magic, fountains)
  - Fog of war
- [ ] HTML UI overlay (HP/MP bars, inventory, chat, minimap)
- [ ] Touch controls for mobile
- [ ] Cross-play: telnet and web clients in same world

### v3.0 - Server Federation
Each server instance owns a realm (overworld + dungeons). Dungeon entrances become inter-server portals — step in, your character serializes to JSON and transfers to another host. Step out, you're back where you left.

- [ ] Inter-server transfer protocol (character JSON handoff over TCP)
- [ ] Portal tile type linking to remote servers
- [ ] Server registry (name, host, port, description)
- [ ] Seamless return — exit a remote dungeon, land back at the entrance you came from
- [ ] Cross-server chat / announcements

### v4.0 - Full MUD
- [ ] Scripting engine for quests/NPCs (Lua or Python)
- [ ] Guild/clan system
- [ ] Economy (player shops, auction house)
- [ ] World persistence (server state snapshots)
- [ ] Admin web dashboard

## Configuration

| Env Variable | Default | Description |
|---|---|---|
| DUNGEON_GM_PASS | "dungeon" | GM login password |

## Controls

### Exploration
| Key | Action |
|---|---|
| W / Up Arrow | Move forward |
| A / Left Arrow | Turn left |
| D / Right Arrow | Turn right |
| S / Down Arrow | Turn around |
| T | Chat (talk to all players) |
| C | Character sheet |
| H | Shop (at stairs up / towns) |
| P | PvP attack (when player nearby) |
| R | Drink from fountain |
| < | Go upstairs / exit dungeon |
| > | Go downstairs / enter dungeon |
| / | GM menu (if authenticated) |
| Q | Save and quit |

### Combat
| Key | Action |
|---|---|
| A | Attack |
| S | Cast spell |
| P | Use potion |
| F | Flee |

## License

Built for fun. Do whatever you want with it.
