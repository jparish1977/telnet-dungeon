"""Combat systems — PvE encounters, PvP duels, death handling."""

import random

from dungeon.config import (
    CLEAR, DIM, RED, GREEN, YELLOW, CYAN, WHITE, MAGENTA, RESET,
    color, OVERWORLD_FLOOR,
)
from dungeon.items import WEAPONS, ARMOR, SPELLS, SOUTH
from dungeon.persistence import save_character, delete_save
from dungeon.floor import get_floor_spawn


def _bar(cur, max_val, width, bar_color):
    """Render an HP/MP bar."""
    if max_val == 0:
        return f"{DIM}N/A{RESET}"
    filled = int((cur / max_val) * width) if max_val > 0 else 0
    filled = max(0, min(width, filled))
    bar = '#' * filled + '-' * (width - filled)
    return f"{bar_color}{bar}{RESET} {cur}/{max_val}"


async def run_combat(session, monster_template, allies=None):
    """Run a turn-based PvE combat encounter.

    session: the attacking GameSession
    allies: list of other GameSessions on the same tile
    Returns: 'victory', 'dead', or 'fled'
    """
    monster = dict(monster_template)
    if allies:
        monster['hp'] = int(monster['hp'] * (1 + 0.5 * len(allies)))
    monster['max_hp'] = monster['hp']
    session.combat_shield_bonus = 0
    char = session.char

    await session.send(CLEAR)
    await session.send_line(color("=======================================", RED))
    await session.send_line(color(f"  A {monster['name']} appears!", RED))
    await session.send_line(color("=======================================", RED))
    await session.send_line()

    # Monster ASCII art
    arts = {
        "Giant Rat":    ["  (\\_/)", "  (o.o)", "  (> <)"],
        "Kobold":       ["  /\\_/\\", " ( o.o)", "  > ^ <"],
        "Skeleton":     ["   _||_", "  /o  o\\", "  |_/\\_|", "   /||\\"],
        "Giant Spider": [" /\\(oo)/\\", "//\\\\||//\\\\"],
        "Zombie":       ["  [x_x]", "  /|  |\\", "  / \\/ \\"],
        "Demon Lord":   [" _/\\_/\\_", "( O  O )", " \\    /", "  \\||/", "  /||\\ ", " / || \\"],
    }
    if 'art' in monster and monster['art']:
        art = monster['art']
    else:
        art = arts.get(monster['name'], ["  [?_?]", "  /| |\\"])
    for line in art:
        await session.send_line(color(f"        {line}", RED))
    await session.send_line()

    fled = False
    while monster['hp'] > 0 and char['hp'] > 0 and not fled:
        hp_bar = _bar(char['hp'], char['max_hp'], 15, GREEN)
        mp_bar = _bar(char['mp'], char['max_mp'], 10, CYAN)
        m_bar = _bar(monster['hp'], monster['max_hp'], 15, RED)

        await session.send_line(f"  {color(char['name'], WHITE)} HP:{hp_bar} MP:{mp_bar}")
        await session.send_line(f"  {color(monster['name'], RED)}  HP:{m_bar}")
        await session.send_line()

        await session.send_line(
            f"  {color('[A]', YELLOW)}ttack  {color('[S]', YELLOW)}pell  "
            f"{color('[P]', YELLOW)}otion  {color('[F]', YELLOW)}lee"
        )
        action = (await session.get_char("  Action: ")).upper()

        player_dmg = 0
        player_acted = True

        if action == 'A':
            atk = session.get_atk()
            roll = random.randint(1, 20)
            if roll == 20:
                player_dmg = atk * 2
                session.log(color("CRITICAL HIT!", YELLOW))
            elif roll + char['spd'] > 8:
                player_dmg = max(1, atk - monster['def'] // 2 + random.randint(-2, 2))
            else:
                session.log("Your attack misses!")

            if player_dmg > 0:
                monster['hp'] -= player_dmg
                session.log(f"You hit {monster['name']} for {color(str(player_dmg), GREEN)} damage!")

        elif action == 'S':
            spells = char.get('spells', [])
            if not spells:
                session.log(color("You don't know any spells!", RED))
                player_acted = False
            else:
                await session.send_line()
                for i, sp in enumerate(spells, 1):
                    info = SPELLS[sp]
                    await session.send_line(
                        f"    {color(f'[{i}]', YELLOW)} {sp} - {info['desc']} (MP: {info['cost']})"
                    )
                await session.send_line(f"    {color('[0]', YELLOW)} Cancel")
                sp_choice = await session.get_char("    Spell: ")
                try:
                    si = int(sp_choice)
                    if si == 0:
                        player_acted = False
                    elif 1 <= si <= len(spells):
                        spell_name = spells[si - 1]
                        spell = SPELLS[spell_name]
                        if char['mp'] >= spell['cost']:
                            char['mp'] -= spell['cost']
                            if spell_name == 'HEAL':
                                heal = random.randint(15, 25)
                                char['hp'] = min(char['max_hp'], char['hp'] + heal)
                                session.log(color(f"You heal for {heal} HP!", GREEN))
                            elif spell_name == 'FIREBALL':
                                dmg = random.randint(12, 20)
                                monster['hp'] -= dmg
                                session.log(color(f"Fireball hits for {dmg} damage!", YELLOW))
                            elif spell_name == 'SHIELD':
                                session.combat_shield_bonus = 5
                                session.log(color("A magical shield surrounds you! +5 DEF", CYAN))
                            elif spell_name == 'LIGHTNING':
                                dmg = random.randint(20, 35)
                                monster['hp'] -= dmg
                                session.log(color(f"Lightning strikes for {dmg} damage!", YELLOW))
                            elif spell_name == 'CURE':
                                char['poisoned'] = False
                                session.log(color("Poison cured!", GREEN))
                        else:
                            session.log(color("Not enough MP!", RED))
                            player_acted = False
                    else:
                        player_acted = False
                except ValueError:
                    player_acted = False

        elif action == 'P':
            if char['potions'] > 0:
                char['potions'] -= 1
                heal = random.randint(10, 20)
                char['hp'] = min(char['max_hp'], char['hp'] + heal)
                session.log(color(f"You drink a potion! +{heal} HP ({char['potions']} left)", GREEN))
            else:
                session.log(color("No potions left!", RED))
                player_acted = False

        elif action == 'F':
            flee_chance = 40 + char['spd'] * 3
            if char['class'] == 'THIEF':
                flee_chance += 20
            if random.randint(1, 100) <= flee_chance:
                session.log("You flee from combat!")
                fled = True
                continue
            else:
                session.log(color("Can't escape!", RED))

        else:
            player_acted = False

        # Ally attacks (co-op)
        if monster['hp'] > 0 and player_acted and allies:
            for ally in allies:
                if ally.char and ally.char['hp'] > 0:
                    a_atk = ally.char['base_atk'] + WEAPONS[ally.char['weapon']]['atk']
                    a_roll = random.randint(1, 20)
                    if a_roll == 20:
                        a_dmg = a_atk * 2
                        session.log(color(f"{ally.char['name']} CRITS!", YELLOW))
                    elif a_roll + ally.char['spd'] > 8:
                        a_dmg = max(1, a_atk - monster['def'] // 2 + random.randint(-2, 2))
                    else:
                        a_dmg = 0
                    if a_dmg > 0:
                        monster['hp'] -= a_dmg
                        session.log(f"{color(ally.char['name'], GREEN)} hits for {color(str(a_dmg), GREEN)}!")
                    if monster['hp'] <= 0:
                        break

        # Monster turn
        if monster['hp'] > 0 and player_acted:
            m_roll = random.randint(1, 20)
            if m_roll == 20:
                m_dmg = monster['atk'] * 2
                session.log(color(f"{monster['name']} lands a CRITICAL HIT!", RED))
            elif m_roll + 5 > 8:
                m_dmg = max(1, monster['atk'] - session.get_def() // 2 + random.randint(-2, 2))
            else:
                m_dmg = 0
                session.log(f"{monster['name']}'s attack misses!")

            if m_dmg > 0:
                char['hp'] -= m_dmg
                session.log(f"{monster['name']} hits you for {color(str(m_dmg), RED)} damage!")

            if monster['name'] in ('Giant Spider', 'Ghoul') and random.randint(1, 4) == 1:
                char['poisoned'] = True
                session.log(color("You've been poisoned!", MAGENTA))

        # Show combat log
        await session.send(CLEAR)
        await session.send_line(color("=== COMBAT ===", RED))
        await session.send_line()
        for art_line in art:
            await session.send_line(color(f"        {art_line}", RED))
        await session.send_line()
        for msg in session.message_log:
            await session.send_line(f"  {msg}")
        await session.send_line()

    session.combat_shield_bonus = 0

    if char['hp'] <= 0:
        return 'dead'
    elif fled:
        return 'fled'
    else:
        xp_gain = monster['xp']
        gold_gain = monster['gold']
        if char.get('hardcore', False):
            xp_gain = int(xp_gain * 1.5)
            gold_gain = int(gold_gain * 1.5)
        char['xp'] += xp_gain
        char['gold'] += gold_gain
        char['kills'] += 1
        hc_tag = color(" [HC]", RED) if char.get('hardcore', False) else ""
        session.log(color(f"Victory! +{xp_gain} XP, +{gold_gain} gold", GREEN) + hc_tag)
        await session.check_level_up()
        if allies:
            for ally in allies:
                if ally.char and ally.char['hp'] > 0:
                    ally.char['xp'] += monster['xp']
                    ally.char['gold'] += monster['gold']
                    ally.char['kills'] += 1
                    ally.log(color(f"Party victory! +{monster['xp']} XP, +{monster['gold']} gold", GREEN))
                    save_character(ally.char)
        return 'victory'


async def run_pvp(session, target, world):
    """PvP duel — attacker controls actions, defender auto-fights."""
    my_name = session.char['name']
    t_name = target.char['name']

    world.broadcast(f"{my_name} attacks {t_name}!", RED)
    target.log(color(f"{my_name} is attacking you!", RED))
    target.notify_event.set()

    session.combat_shield_bonus = 0
    fled = False

    while session.char['hp'] > 0 and target.char['hp'] > 0 and not fled:
        await session.send(CLEAR)
        await session.send_line(color("=== PVP DUEL ===", RED))
        await session.send_line()
        my_hp = _bar(session.char['hp'], session.char['max_hp'], 12, GREEN)
        t_hp = _bar(target.char['hp'], target.char['max_hp'], 12, RED)
        await session.send_line(f"  {color(my_name, GREEN)} HP:{my_hp}")
        await session.send_line(f"  {color(t_name, RED)}  HP:{t_hp}")
        await session.send_line()

        for msg in session.message_log[-4:]:
            await session.send_line(f"  {msg}")
        session.message_log.clear()
        await session.send_line()

        await session.send_line(
            f"  {color('[A]', YELLOW)}ttack  {color('[P]', YELLOW)}otion  {color('[F]', YELLOW)}lee"
        )
        action = (await session.get_char("  Action: ")).upper()

        player_acted = True

        if action == 'F':
            flee_chance = 30 + session.char['spd'] * 3
            if random.randint(1, 100) <= flee_chance:
                session.log("You fled the duel!")
                target.log(f"{my_name} fled from the duel!")
                target.notify_event.set()
                world.broadcast(f"{my_name} fled from {t_name}!", YELLOW)
                fled = True
                continue
            else:
                session.log(color("Can't escape!", RED))

        elif action == 'P':
            if session.char['potions'] > 0:
                session.char['potions'] -= 1
                heal = random.randint(10, 20)
                session.char['hp'] = min(session.char['max_hp'], session.char['hp'] + heal)
                session.log(color(f"Drank a potion! +{heal} HP", GREEN))
            else:
                session.log(color("No potions!", RED))
                player_acted = False

        elif action == 'A':
            my_atk = session.get_atk()
            t_def = target.char['base_def'] + ARMOR[target.char['armor']]['def']
            roll = random.randint(1, 20)
            if roll == 20:
                dmg = my_atk * 2
                session.log(color("CRITICAL HIT!", YELLOW))
            elif roll + session.char['spd'] > 8:
                dmg = max(1, my_atk - t_def // 2 + random.randint(-2, 2))
            else:
                dmg = 0
                session.log("Your attack misses!")
            if dmg > 0:
                target.char['hp'] -= dmg
                session.log(f"You hit {t_name} for {color(str(dmg), GREEN)} damage!")
                target.log(f"{my_name} hits you for {color(str(dmg), RED)} damage!")
                target.notify_event.set()
        else:
            player_acted = False

        # Defender auto-attacks
        if target.char['hp'] > 0 and player_acted:
            t_atk = target.char['base_atk'] + WEAPONS[target.char['weapon']]['atk']
            my_def = session.get_def()
            roll = random.randint(1, 20)
            if roll == 20:
                dmg = t_atk * 2
                session.log(color(f"{t_name} lands a CRITICAL HIT!", RED))
            elif roll + target.char['spd'] > 8:
                dmg = max(1, t_atk - my_def // 2 + random.randint(-2, 2))
            else:
                dmg = 0
                session.log(f"{t_name}'s counter-attack misses!")
            if dmg > 0:
                session.char['hp'] -= dmg
                session.log(f"{t_name} hits you for {color(str(dmg), RED)} damage!")
                target.log(f"You counter-attack {my_name} for {color(str(dmg), GREEN)} damage!")
                target.notify_event.set()

    if fled:
        return

    if session.char['hp'] <= 0:
        winner, loser = target, session
    else:
        winner, loser = session, target

    spoils = loser.char['gold'] // 4
    winner.char['gold'] += spoils
    loser.char['gold'] -= spoils
    winner.char['kills'] += 1

    winner.log(color(f"Defeated {loser.char['name']}! +{spoils} gold!", GREEN))
    loser.log(color(f"Defeated by {winner.char['name']}! Lost {spoils} gold!", RED))
    winner.notify_event.set()
    loser.notify_event.set()
    world.broadcast(f"{winner.char['name']} defeated {loser.char['name']} in PvP!", RED)

    save_character(winner.char)
    save_character(loser.char)


async def handle_game_over(session):
    """Handle player death — permadeath for hardcore, respawn for normal."""
    char = session.char
    is_hardcore = char.get('hardcore', False)

    await session.send(CLEAR)
    await session.send_line()

    if is_hardcore:
        await session.send_line(color("  +-------------------------------+", RED))
        await session.send_line(color("  |     T H O U   H A S T        |", RED))
        await session.send_line(color("  |        P E R I S H E D        |", RED))
        await session.send_line(color("  |       [HARDCORE DEATH]        |", RED))
        await session.send_line(color("  +-------------------------------+", RED))
        await session.send_line()
        await session.send_line(f"  {char['name']} the {char['class']}")
        await session.send_line(f"  Level {char['level']} - {char['kills']} kills")
        await session.send_line(f"  Reached floor {char['floor'] + 1}")
        await session.send_line()
        delete_save(char['name'])
        await session.send_line(color("  Your save has been erased forever.", RED))
        await session.send_line(color("  This is the path you chose.", DIM))
        await session.send_line()
        await session.get_char(color("  Press any key...", DIM))
    else:
        await session.send_line(color("  +-------------------------------+", RED))
        await session.send_line(color("  |     Y O U   D I E D          |", RED))
        await session.send_line(color("  +-------------------------------+", RED))
        await session.send_line()
        await session.send_line(f"  {char['name']} the {char['class']}")
        await session.send_line(f"  Slain on floor {char['floor'] + 1}")
        await session.send_line()
        death_msgs = [
            "  The dungeon claims another soul... temporarily.",
            "  You see a light... it's the entrance. You're back.",
            "  A mysterious force drags you to safety.",
            "  The rats will feast tonight, but not on you.",
            "  Death is just a minor inconvenience around here.",
        ]
        await session.send_line(color(random.choice(death_msgs), YELLOW))
        await session.send_line()

        gold_lost = char['gold'] // 5
        char['gold'] -= gold_lost
        char['hp'] = char['max_hp'] // 2
        # Respawn at stairs-up on same floor
        sx, sy = get_floor_spawn(char['floor'])
        char['x'] = sx
        char['y'] = sy
        char['facing'] = SOUTH
        char['poisoned'] = False
        save_character(char)

        floor_name = "the overworld" if char['floor'] == OVERWORLD_FLOOR else f"floor {char['floor'] + 1}"
        await session.send_line(color(f"  Lost {gold_lost} gold. Respawning on {floor_name}...", DIM))
        await session.send_line()
        await session.get_char(color("  Press any key to try again...", DIM))


async def handle_pvp_death(session, killer_name):
    """PvP death — no permadeath, respawn with trash talk."""
    char = session.char
    taunts = [
        f"  {killer_name} mopped the floor with you.",
        f"  {killer_name} sent you back to the shadow realm.",
        f"  {killer_name} didn't even break a sweat.",
        "  Maybe try fighting a rat first next time.",
        f"  {killer_name} says: 'git gud'",
        "  Your ancestors are embarrassed.",
        f"  {killer_name} is now wearing your dignity as a hat.",
        "  Even the kobolds are laughing at you.",
        f"  {killer_name} killed you. Go eat their children.",
        "  That was painful to watch. And you LIVED it.",
    ]

    await session.send(CLEAR)
    await session.send_line()
    await session.send_line(color("  +-------------------------------+", RED))
    await session.send_line(color("  |     S L A I N   I N   P V P   |", RED))
    await session.send_line(color("  +-------------------------------+", RED))
    await session.send_line()
    await session.send_line(color(f"  Killed by: {killer_name}", RED))
    await session.send_line()
    await session.send_line(color(random.choice(taunts), YELLOW))
    await session.send_line()
    await session.send_line(color("  You lost 25% of your gold.", DIM))
    await session.send_line()

    char['hp'] = char['max_hp'] // 2
    # Respawn at stairs-up on same floor
    sx, sy = get_floor_spawn(char['floor'])
    char['x'] = sx
    char['y'] = sy
    char['facing'] = SOUTH
    char['poisoned'] = False
    save_character(char)

    await session.send_line(color("  Respawning at stairs...", GREEN))
    await session.send_line()
    await session.get_char(color("  Press any key to get back in there...", DIM))


async def run_pvp_combat(session, target):
    """PvP duel — attacker controls, defender sees live updates."""
    my_name = session.char['name']
    t_name = target.char['name']

    def notify_both(msg):
        """Log a message to both combatants."""
        session.log(msg)
        target.log(msg)
        target.notify_event.set()

    notify_both(color(f"=== PVP: {my_name} vs {t_name} ===", RED))

    session.combat_shield_bonus = 0
    fled = False

    while session.char['hp'] > 0 and target.char['hp'] > 0 and not fled:
        # Status update to both
        my_hp = _bar(session.char['hp'], session.char['max_hp'], 12, GREEN)
        t_hp = _bar(target.char['hp'], target.char['max_hp'], 12, RED)
        hp_status = f"  {color(my_name, GREEN)} HP:{my_hp}  vs  {color(t_name, RED)} HP:{t_hp}"
        target.log(hp_status)
        target.notify_event.set()

        # Attacker's combat screen
        await session.send(CLEAR)
        await session.send_line(color("=== PVP DUEL ===", RED))
        await session.send_line()
        await session.send_line(hp_status)
        await session.send_line()

        for msg in session.message_log[-4:]:
            await session.send_line(f"  {msg}")
        session.message_log.clear()
        await session.send_line()

        await session.send_line(f"  {color('[A]', YELLOW)}ttack  {color('[P]', YELLOW)}otion  "
                               f"{color('[F]', YELLOW)}lee")
        action = (await session.get_char("  Action: ")).upper()

        player_acted = True

        if action == 'F':
            flee_chance = 30 + session.char['spd'] * 3
            if random.randint(1, 100) <= flee_chance:
                notify_both(color(f"{my_name} fled from the duel!", YELLOW))
                fled = True
                continue
            else:
                notify_both(color(f"{my_name} can't escape!", RED))

        elif action == 'P':
            if session.char['potions'] > 0:
                session.char['potions'] -= 1
                heal = random.randint(10, 20)
                session.char['hp'] = min(session.char['max_hp'], session.char['hp'] + heal)
                notify_both(color(f"{my_name} drinks a potion! +{heal} HP", GREEN))
            else:
                session.log(color("No potions!", RED))
                player_acted = False

        elif action == 'A':
            my_atk = session.get_atk()
            t_def = target.char['base_def'] + ARMOR[target.char['armor']]['def']
            roll = random.randint(1, 20)
            if roll == 20:
                dmg = my_atk * 2
                notify_both(color(f"{my_name} lands a CRITICAL HIT!", YELLOW))
            elif roll + session.char['spd'] > 8:
                dmg = max(1, my_atk - t_def // 2 + random.randint(-2, 2))
            else:
                dmg = 0
                notify_both(color(f"{my_name}'s attack misses!", DIM))
            if dmg > 0:
                target.char['hp'] -= dmg
                notify_both(f"{color(my_name, GREEN)} hits {color(t_name, RED)} for {color(str(dmg), YELLOW)} damage!")
        else:
            player_acted = False

        # Defender auto-attacks back
        if target.char['hp'] > 0 and player_acted:
            t_atk = target.char['base_atk'] + WEAPONS[target.char['weapon']]['atk']
            my_def = session.get_def()
            roll = random.randint(1, 20)
            if roll == 20:
                dmg = t_atk * 2
                notify_both(color(f"{t_name} lands a CRITICAL HIT!", RED))
            elif roll + target.char['spd'] > 8:
                dmg = max(1, t_atk - my_def // 2 + random.randint(-2, 2))
            else:
                dmg = 0
                notify_both(color(f"{t_name}'s counter-attack misses!", DIM))
            if dmg > 0:
                session.char['hp'] -= dmg
                notify_both(f"{color(t_name, RED)} hits {color(my_name, GREEN)} for {color(str(dmg), YELLOW)} damage!")

    if fled:
        return

    # Determine winner/loser
    if session.char['hp'] <= 0:
        winner, loser = target, session
    else:
        winner, loser = session, target

    spoils = loser.char['gold'] // 4
    winner.char['gold'] += spoils
    loser.char['gold'] -= spoils
    winner.char['kills'] += 1

    winner.log(color(f"Defeated {loser.char['name']}! +{spoils} gold!", GREEN))
    loser.log(color(f"Defeated by {winner.char['name']}! Lost {spoils} gold!", RED))
    winner.notify_event.set()
    loser.notify_event.set()

    save_character(winner.char)
    save_character(loser.char)
