"""Quest engine — loads quest definitions, tracks player state, manages
hidden entrances and NPC interactions."""

import json
import os

from dungeon.config import (
    CYAN, GREEN, YELLOW, MAGENTA, DIM, WHITE,
    color, OVERWORLD_FLOOR,
)
from dungeon.persistence import save_character

QUESTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quests")

# ── Quest data cache ──────────────────────────────────────────────
_quest_cache = {}


def load_quest(quest_id):
    """Load a quest definition from JSON."""
    if quest_id in _quest_cache:
        return _quest_cache[quest_id]
    path = os.path.join(QUESTS_DIR, f"{quest_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        _quest_cache[quest_id] = data
        return data
    return None


def list_quests():
    """List all available quest IDs."""
    if not os.path.isdir(QUESTS_DIR):
        return []
    return [f[:-5] for f in os.listdir(QUESTS_DIR) if f.endswith('.json')]


# ── Player quest state ────────────────────────────────────────────

def get_quest_state(char, quest_id):
    """Get a player's state for a specific quest."""
    flags = char.get('quest_flags', {})
    return flags.get(quest_id, {})


def set_quest_flag(char, quest_id, flag, value=True):
    """Set a flag on a player's quest state."""
    if 'quest_flags' not in char:
        char['quest_flags'] = {}
    if quest_id not in char['quest_flags']:
        char['quest_flags'][quest_id] = {}
    char['quest_flags'][quest_id][flag] = value
    save_character(char)


def has_quest_flag(char, quest_id, flag):
    """Check if a player has a quest flag set."""
    return get_quest_state(char, quest_id).get(flag, False)


def get_quest_stage(char, quest_id):
    """Get the current stage name for a quest."""
    return get_quest_state(char, quest_id).get('stage', None)


def set_quest_stage(char, quest_id, stage):
    """Set the current stage for a quest."""
    set_quest_flag(char, quest_id, 'stage', stage)
    apply_map_modifications(quest_id, stage)


def is_quest_active(char, quest_id):
    """Check if a player has started this quest."""
    return get_quest_stage(char, quest_id) is not None


def is_quest_complete(char, quest_id):
    """Check if a player has completed this quest."""
    return get_quest_stage(char, quest_id) == 'complete'


# ── Map modifications ─────────────────────────────────────────────
_applied_mods = set()  # track which mods have been applied globally


def apply_all_active_mods(char):
    """Apply all map modifications for a player's active quests.
    Call on login to ensure the world matches their quest state."""
    for quest_id in list_quests():
        stage = get_quest_stage(char, quest_id)
        if stage:
            quest = load_quest(quest_id)
            if quest:
                for s in quest.get('stages', []):
                    sid = s['id']
                    # Apply all mods for stages up to current
                    apply_map_modifications(quest_id, sid)
                    if sid == stage:
                        break


def apply_map_modifications(quest_id, stage):
    """Apply map modifications for a quest stage.
    Modifications are defined in the quest JSON under 'map_mods'.
    Each mod has a trigger stage and a list of tile changes."""
    from dungeon.floor import get_floor

    if (quest_id, stage) in _applied_mods:
        return
    _applied_mods.add((quest_id, stage))

    quest = load_quest(quest_id)
    if not quest:
        return

    for mod in quest.get('map_mods', []):
        if mod.get('trigger') != stage:
            continue
        target_floor = mod.get('floor', OVERWORLD_FLOOR)
        floor_grid = get_floor(target_floor)
        changes = mod.get('tiles', [])
        for change in changes:
            x, y, tile = change['x'], change['y'], change['tile']
            if 0 <= y < len(floor_grid) and 0 <= x < len(floor_grid[0]):
                floor_grid[y][x] = tile
        print(f"[QUEST] Applied {len(changes)} tile changes to floor {target_floor}", flush=True)


# ── Quest entrances (per-player visibility) ───────────────────────

def get_visible_entrances(char, floor_num):
    """Get quest entrances visible to this player on this floor.
    Returns list of (x, y, quest_id, entrance_data)."""
    visible = []
    for quest_id in list_quests():
        quest = load_quest(quest_id)
        if not quest:
            continue
        for entrance in quest.get('entrances', []):
            # Check floor match
            ent_floor = entrance.get('floor', OVERWORLD_FLOOR)
            if ent_floor != floor_num:
                continue
            # Check visibility condition
            if not _check_condition(char, quest_id, entrance.get('visible_if', 'true')):
                continue
            visible.append((
                entrance['x'], entrance['y'],
                quest_id, entrance,
            ))
    return visible


def _check_condition(char, quest_id, condition):
    """Evaluate a simple condition string against player state."""
    if condition == 'true':
        return True
    if condition == 'false':
        return False

    # "quest_stage >= started"
    if 'quest_stage' in condition:
        stage = get_quest_stage(char, quest_id)
        if '>=' in condition:
            # Any non-None stage means started
            target = condition.split('>=')[1].strip()
            if target == 'started':
                return stage is not None
            return stage == target
        if '==' in condition:
            target = condition.split('==')[1].strip()
            return stage == target

    # "has_flag flag_name"
    if condition.startswith('has_flag '):
        flag = condition[9:].strip()
        return has_quest_flag(char, quest_id, flag)

    # "not_flag flag_name"
    if condition.startswith('not_flag '):
        flag = condition[9:].strip()
        return not has_quest_flag(char, quest_id, flag)

    return False


# ── Quest NPCs ────────────────────────────────────────────────────

def get_npcs_on_floor(char, quest_id, floor_num):
    """Get NPCs that should appear on this floor for this player's quest state.
    Returns list of NPC dicts with x, y positions."""
    quest = load_quest(quest_id)
    if not quest:
        return []
    npcs = []
    for npc_id, npc in quest.get('npcs', {}).items():
        npc_floor = npc.get('floor', OVERWORLD_FLOOR)
        if npc_floor != floor_num:
            continue
        # Check if NPC should be visible based on quest state
        requires = npc.get('requires')
        if requires and not has_quest_flag(char, quest_id, requires):
            continue
        # Don't show if already completed this NPC's interaction
        found_flag = npc.get('found_flag')
        if found_flag and npc.get('hide_after_found', False):
            if has_quest_flag(char, quest_id, found_flag):
                continue
        npcs.append({
            'id': npc_id,
            'quest_id': quest_id,
            'name': npc.get('name', npc_id),
            'x': npc.get('x', 1),
            'y': npc.get('y', 1),
            'art': npc.get('art', []),
            'symbol': npc.get('name', '?')[0].upper(),
            **npc,
        })
    return npcs


def get_all_visible_npcs(char, floor_num):
    """Get all quest NPCs visible to this player on this floor.
    Quest givers (location=town) are always visible.
    Other NPCs only show if quest is active."""
    all_npcs = []
    for quest_id in list_quests():
        quest = load_quest(quest_id)
        if not quest:
            continue
        active = is_quest_active(char, quest_id)
        for npc_id, npc in quest.get('npcs', {}).items():
            # Quest givers are always visible (they start the quest)
            is_quest_giver = npc.get('location') == 'town'
            if not active and not is_quest_giver:
                continue
            # Skip if already complete and not the quest giver
            if is_quest_complete(char, quest_id) and not is_quest_giver:
                continue
            npc_floor = npc.get('floor', OVERWORLD_FLOOR)
            if npc_floor != floor_num:
                continue
            # Check requires flag
            requires = npc.get('requires')
            if requires and not has_quest_flag(char, quest_id, requires):
                continue
            all_npcs.append({
                'id': npc_id,
                'quest_id': quest_id,
                'name': npc.get('name', npc_id),
                'x': npc.get('x', 1),
                'y': npc.get('y', 1),
                'art': npc.get('art', []),
                'symbol': npc.get('symbol', npc.get('name', '?')[0].upper()),
                **npc,
            })
    return all_npcs


# ── NPC Dialog ────────────────────────────────────────────────────

async def run_npc_dialog(session, npc, quest_id):
    """Display NPC dialog based on current quest state."""
    quest = load_quest(quest_id)
    if not quest:
        return

    char = session.char
    npc_name = npc.get('name', '???')
    art = npc.get('art', [])

    # Show NPC art
    await session.send_line()
    for line in art:
        await session.send_line(color(f"    {line}", CYAN))
    await session.send_line()

    # Pick dialog based on quest state
    stage = get_quest_stage(char, quest_id)
    found_flag = npc.get('found_flag')
    requires = npc.get('requires')

    # Determine which dialog to show
    dialog_lines = []

    if npc.get('id') == 'ginger' or npc.get('location') == 'town':
        # Quest giver — dialog changes with progress
        if is_quest_complete(char, quest_id):
            dialog_lines = npc.get('dialog_complete', [f"{npc_name}: Thank you."])
        elif has_quest_flag(char, quest_id, 'hobbles_found'):
            dialog_lines = npc.get('dialog_hobbles_found', [f"{npc_name}: Keep going!"])
        elif stage is not None:
            dialog_lines = npc.get('dialog_start', [f"{npc_name}: ..."])
        else:
            # First meeting — start the quest
            dialog_lines = npc.get('dialog_start', [f"{npc_name}: I need your help."])
            set_quest_stage(char, quest_id, 'started')

    elif requires and not has_quest_flag(char, quest_id, requires):
        # NPC requires a flag the player doesn't have
        dialog_lines = npc.get('dialog_before_hobbles',
                              npc.get('dialog', [f"{npc_name}: ..."]))

    elif found_flag and has_quest_flag(char, quest_id, found_flag):
        # Already found this NPC
        dialog_lines = [f"{npc_name}: You already helped me. Thank you."]

    else:
        # First time finding this NPC — use appropriate dialog
        if requires and has_quest_flag(char, quest_id, requires):
            dialog_lines = npc.get('dialog_with_hobbles',
                                  npc.get('dialog', [f"{npc_name}: Thank you!"]))
        else:
            dialog_lines = npc.get('dialog', [f"{npc_name}: ..."])

        # Set the found flag
        if found_flag:
            set_quest_flag(char, quest_id, found_flag)

    # Display dialog
    for line in dialog_lines:
        if line == "":
            await session.send_line()
        else:
            await session.send_line(color(f"  {line}", WHITE))
            await session.get_char("")  # press any key to advance

    await session.send_line()
    await session.get_char(color("  (press any key to continue)", DIM))


# ── Quest rewards ─────────────────────────────────────────────────

def apply_quest_rewards(char, quest_id):
    """Apply quest completion rewards to a character."""
    quest = load_quest(quest_id)
    if not quest:
        return []

    rewards = quest.get('rewards', {})
    messages = []

    gold = rewards.get('gold', 0)
    if gold:
        char['gold'] += gold
        messages.append(color(f"  +{gold} gold!", YELLOW))

    blessing = rewards.get('blessing')
    if blessing:
        for key in ['atk_bonus', 'def_bonus', 'spd_bonus']:
            stat = key.replace('_bonus', '')
            if stat == 'atk':
                stat = 'base_atk'
            elif stat == 'def':
                stat = 'base_def'
            val = blessing.get(key, 0)
            if val:
                char[stat] = char.get(stat, 0) + val
                messages.append(color(f"  +{val} {stat}!", GREEN))

        hp_bonus = blessing.get('hp_bonus', 0)
        if hp_bonus:
            char['max_hp'] += hp_bonus
            char['hp'] += hp_bonus
            messages.append(color(f"  +{hp_bonus} max HP!", GREEN))

        mp_bonus = blessing.get('mp_bonus', 0)
        if mp_bonus:
            char['max_mp'] += mp_bonus
            char['mp'] += mp_bonus
            messages.append(color(f"  +{mp_bonus} max MP!", GREEN))

        name = blessing.get('name', 'Blessing')
        messages.insert(0, color(f"  Received: {name}", MAGENTA))

    save_character(char)
    return messages
