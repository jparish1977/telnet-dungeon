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

## Integration Points

- Behaviors stored in `quests/*.json` or `monsters/behaviors/*.json`
- `move_floor_monsters()` evaluates behaviors instead of hardcoded chase/wander
- Combat AI evaluates behaviors for attack patterns instead of random rolls
- Quest NPCs use behaviors for dialog triggers
- Existing monster editor (`/` -> `M`) gets `[B]ehavior` option
- Behaviors are JSON — portable, editable, no code required

## Implementation Plan

### New modules needed:

- `dungeon/behavior.py` — rule interpreter (parse conditions, evaluate against game state, execute actions)
- `dungeon/gm/behavior_editor.py` — telnet UI for editing behavior rules

### Modules to modify:

- `dungeon/monsters.py` — `move_floor_monsters()` checks for behavior rules before hardcoded AI
- `dungeon/combat.py` — monster combat turns evaluate behavior rules
- `dungeon/gm/tools.py` — add [B]ehavior option to monster editor
- `dungeon/session.py` — NPC interaction in main loop (dialog triggers)
