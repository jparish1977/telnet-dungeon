# Carnage Heart-style AI Editor for NPCs/Monsters

## Concept

A visual-logic behavior editor for monsters and NPCs, inspired by Carnage Heart (PS1, 1995). Behaviors are defined as a list of rules: condition(s) -> action(s). Rules evaluated top-to-bottom, first match wins. No code required — GMs and quest designers define complex behaviors in JSON.

## Rule Format

```json
{
  "name": "Verdant Blight",
  "behavior": [
    {
      "if": "hp_pct < 20",
      "then": ["say 'YOU CANNOT KILL WHAT GROWS ETERNAL'", "heal 15"]
    },
    { "if": "player_distance <= 1", "then": ["attack", "poison 30"] },
    { "if": "player_distance <= 5", "then": ["move_toward_player"] },
    { "if": "ally_count < 3", "then": ["summon vine_horror"] },
    { "else": true, "then": ["patrol waypoints"] }
  ]
}
```

## Available Conditions

- `player_distance < N` — tiles from nearest player
- `hp_pct < N` — health percentage
- `player_hp_pct < N` — target's health
- `ally_count < N` — nearby friendlies
- `has_flag FLAG` — quest/world flag is set
- `time_of_day DAY|NIGHT` — if we add day/night
- `random N` — N% chance of being true
- `player_class CLASS` — target is Fighter/Mage/etc

## Available Actions

- `move_toward_player` / `flee_from_player` / `patrol WAYPOINTS`
- `attack` / `attack_strongest` / `attack_weakest`
- `cast SPELL` — use a named ability
- `heal N` — self-heal
- `poison N` — % chance to poison on hit
- `summon MOB_NAME` — spawn an ally
- `say "TEXT"` — speak/emote (shown in combat log or viewport)
- `drop ITEM` — drop loot on death
- `set_flag FLAG` / `clear_flag FLAG` — quest state
- `teleport X Y` — blink to position
- `dialog DIALOG_ID` — trigger NPC dialog tree

## Telnet Editor UI

```
=== BEHAVIOR EDITOR: Verdant Blight ===

  Rule 1: IF hp_pct < 20
          THEN say "YOU CANNOT KILL WHAT GROWS ETERNAL"
               heal 15

  Rule 2: IF player_distance <= 1
          THEN attack
               poison 30

  Rule 3: IF player_distance <= 5
          THEN move_toward_player

  Rule 4: IF ally_count < 3
          THEN summon vine_horror

  Rule 5: ELSE
          THEN patrol waypoints

  [A]dd rule  [E]dit rule  [D]elete  [M]ove up/down  [T]est  [S]ave  [Q]uit
```

## Quest NPC Example

```json
{
  "name": "Ginger",
  "behavior": [
    { "if": "has_flag quest_complete", "then": ["dialog complete_dialog"] },
    { "if": "has_flag hobbles_found", "then": ["dialog hobbles_dialog"] },
    { "if": "player_distance <= 2", "then": ["dialog start_dialog"] },
    { "else": true, "then": ["idle"] }
  ]
}
```

## Construction Conditions (Builder NPCs)

Available when `floor_grid` is passed (mob has `"builder": true`):

- `current_tile == N` — tile under the NPC's feet
- `tile_at X Y == N` — check any tile on the floor
- `room_size > N` — connected floor tiles from current position
- `in_corridor` — am I in a narrow 1-tile-wide passage?
- `corridor_length > N` — how long is this corridor?
- `nearby_walls > N` — wall tile count within 5 tiles
- `nearby_floors > N` — floor tile count within 5 tiles
- `nearby_chests > N` — chest count within 5 tiles
- `nearby_fountains > N` — fountain count within 5 tiles
- `nearby_features > N` — total features within 5 tiles
- `nearby_tile TILE > N` — count of specific tile type within 5 tiles
- `room_has_feature TILE` — is there a specific tile nearby?
- `pending_jobs > N` — guild job queue depth

## Construction Actions (Builder NPCs)

- `set_tile X Y TILE` — place a single tile (won't overwrite stairs)
- `place_room X Y W H [door_side]` — build a walled room with floor inside
- `carve_corridor X1 Y1 X2 Y2` — dig a passage between two points
- `post_job TYPE [context]` — escalate to the guild architect (LLM)
- `inspect` — run craftsman rules on current floor, post all findings as jobs

## Builder NPC Example

```json
{
  "name": "Hodge",
  "builder": true,
  "behavior": [
    { "if": "room_size > 9 and nearby_features == 0", "then": ["post_job boring_room needs features"] },
    { "if": "in_corridor and corridor_length > 6", "then": ["post_job long_corridor needs variety"] },
    { "if": "nearby_chests == 0 and room_size > 4", "then": ["set_tile mob.x mob.y 5"] },
    { "else": true, "then": ["patrol"] }
  ]
}
```

## Integration Points

- Behaviors stored in `quests/*.json` or `monsters/behaviors/*.json`
- `move_floor_monsters()` evaluates behaviors instead of hardcoded chase/wander
- Builder NPCs (`"builder": true`) get floor grid context and construction actions
- Construction actions validated by apprentice logic (dig tunnels, skip duplicates)
- Combat AI evaluates behaviors for attack patterns instead of random rolls
- Quest NPCs use behaviors for dialog triggers
- Existing monster editor (`/` -> `M`) gets `[B]ehavior` option
- Behaviors are JSON — portable, editable, no code required
- Guild system: craftsman inspects → architect plans (LLM) → apprentice builds
- Player-created apprentices use same behavior system + guild job queue

## Implementation Status

### Done:
- `dungeon/behavior.py` — rule interpreter, compiles to Lua, caches scripts
- `dungeon/scripting/lua_backend.py` — sandboxed Lua with combat + construction context
- `dungeon/scripting/base.py` — pluggable backend interface
- `dungeon/monsters.py` — `move_floor_monsters()` evaluates behavior rules + builder actions
- `dungeon/guild/` — craftsman, architect (LLM), apprentice, job queue

### Not yet built:
- `dungeon/gm/behavior_editor.py` — telnet UI for editing behavior rules
- Combat AI integration (behavior rules during fight turns)
- Player-facing apprentice creation (Coding skill tree)
