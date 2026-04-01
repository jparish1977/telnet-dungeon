# Luanti (Minetest) Bridge Mod Research

## Concept

A Luanti mod that connects to the Dungeon Crawler of Doom server, rendering the dungeon as a 3D voxel world. Players explore the same game state through either telnet ASCII, web browser, or Luanti's full 3D engine.

## Architecture

```
Luanti Client <-> Luanti Server + Bridge Mod <-HTTP polling-> Dungeon Server (Python)
```

## Key Luanti APIs

### HTTP (for server communication)

- `core.request_http_api()` — requires `secure.http_mods = dungeon_bridge` in minetest.conf
- `http.fetch({url, method, data}, callback)` — async HTTP requests
- `core.write_json()` / `core.parse_json()` — built-in JSON support
- Poll dungeon server every 0.5-1s via `core.register_globalstep`

### VoxelManip (for room generation)

- `core.get_voxel_manip()` — bulk read/write map data
- `vm:get_data()` / `vm:set_data()` — flat array of content IDs
- Dramatically faster than `core.set_node()` in loops
- Must call `vm:calc_lighting()` + `vm:update_map()` after changes

### Entities (for monsters)

- `core.add_entity(pos, "mymod:monster")` — spawn entities
- `core.register_entity()` — define entity with mesh, texture, AI callbacks
- `on_step`, `on_punch`, `on_death` callbacks

### Player Management

- `player:set_pos(pos)` — teleport
- `player:set_hp(hp)` — set health
- `player:hud_add({})` — custom HUD elements
- `player:set_sky({})` — dungeon atmosphere

## Limitations

- **No raw TCP/WebSocket** — HTTP polling only (unless using insecure environment)
- **Server-side only** — no client-side mod code
- **Entity count** — prefer nodes over entities for static geometry
- **Security whitelist** — admin must explicitly enable HTTP for the mod
- **Map block loading** — use `core.forceload_block()` to keep dungeon areas active

## Implementation Plan

1. Build HTTP status API on dungeon server (JSON endpoint for game state)
2. Create bridge mod that polls this API
3. Translate 2D tile grids → 3D voxel rooms (wall height = 3-4 blocks)
4. Map tile types to Minetest nodes (stone, wood doors, water, etc.)
5. Spawn monster entities from server mob data
6. Forward player actions back to dungeon server via HTTP POST
7. Sync combat, chat, and quest state bidirectionally

## Node Mapping (tile code → Minetest node)

- 0 (floor) → `default:stone_block` (floor) + `air` (above)
- 1 (wall) → `default:stone` (3 blocks high)
- 2 (door) → `doors:door_wood`
- 3 (stairs down) → `stairs:stair_stone` (descending)
- 4 (stairs up) → `stairs:stair_stone` (ascending)
- 5 (treasure) → `default:chest` with loot
- 6 (fountain) → `default:water_source` in stone basin

## References

- Lua API: https://github.com/minetest/minetest/blob/master/doc/lua_api.md
- Modding Book: https://rubenwardy.com/minetest_modding_book/
- ContentDB: https://content.minetest.net/
