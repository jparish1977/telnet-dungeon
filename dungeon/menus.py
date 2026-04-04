"""Title screen, character creation, and character loading menus."""

import random

from dungeon.config import (
    CLEAR, DIM, RED, GREEN, YELLOW, CYAN, WHITE, MAGENTA,
    color, GM_PASSWORD, OVERWORLD_FLOOR,
)
from dungeon.items import CLASSES, SOUTH
from dungeon.persistence import save_character, load_character, list_saves
from dungeon.floor import get_overworld_spawn


async def title_screen(session, world):
    """Show the title screen and return the player's choice: N, L, G, or Q."""
    await session.send(CLEAR)
    w = session.term_width

    if w >= 72:
        await session.send_line(color("=" * min(w - 2, 68), CYAN))
        await session.send_line()
        await session.send_line(color("  ____  _   _ _   _  ____ _____ ___  _   _", RED))
        await session.send_line(color(" |  _ \\| | | | \\ | |/ ___| ____/ _ \\| \\ | |", RED))
        await session.send_line(color(" | | | | | | |  \\| | |  _|  _|| | | |  \\| |", YELLOW))
        await session.send_line(color(" | |_| | |_| | |\\  | |_| | |__| |_| | |\\  |", YELLOW))
        await session.send_line(color(" |____/ \\___/|_| \\_|\\____|_____\\___/|_| \\_|", GREEN))
        await session.send_line()
    else:
        await session.send_line(color("=" * min(w - 2, 40), CYAN))
        await session.send_line()
        await session.send_line(color("     D U N G E O N", RED))
        await session.send_line()

    await session.send_line(color("   +===================================+", MAGENTA))
    await session.send_line(color("   | C R A W L E R   o f   D O O M    |", MAGENTA))
    await session.send_line(color("   +===================================+", MAGENTA))
    await session.send_line()
    await session.send_line(color("=" * min(w - 2, 68), CYAN))
    await session.send_line()
    await session.send_line(color("  A Wizardry-Style Dungeon Crawler", DIM))
    online = world.player_count()
    if online > 0:
        s = "s" if online != 1 else ""
        await session.send_line(f"  {color(f'{online} adventurer{s} online', GREEN)}")
    await session.send_line(
        f"  {color(f'Terminal: {session.term_width}x{session.term_height}', DIM)}"
    )
    await session.send_line()
    await session.send_line(f"  {color('[N]', YELLOW)} New Character")
    await session.send_line(f"  {color('[L]', YELLOW)} Load Character")
    await session.send_line(f"  {color('[G]', DIM)} GM Login")
    await session.send_line(f"  {color('[Q]', YELLOW)} Quit")
    await session.send_line()

    while True:
        choice = (await session.get_char("Your choice: ")).upper()
        if choice in ('N', 'L', 'Q'):
            await session.send_line()
            return choice
        if choice == 'G':
            if session.is_gm:
                # Already authenticated — go straight to GM menu
                return '/'
            await session.send_line()
            pw = await session.get_input("GM Password: ")
            if pw == GM_PASSWORD:
                session.is_gm = True
                await session.send_line(
                    color("GM access granted!", GREEN)
                )
                await session.get_char("Press any key...")
                return '/'
            else:
                await session.send_line(color("Wrong password.", RED))
                await session.get_char("Press any key...")
                return 'G'


async def create_character(session, world):
    """Character creation flow. Sets session.char when done."""
    await session.send(CLEAR)
    await session.send_line(color("=== CHARACTER CREATION ===", CYAN))
    await session.send_line()

    name = ""
    while not name or len(name) > 16:
        name = await session.get_input("Enter thy name (max 16 chars): ")
        if not name:
            await session.send_line("A hero must have a name!")
        elif world.is_banned(name):
            await session.send_line(color("That name is banned!", RED))
            name = ""

    await session.send_line()
    await session.send_line(color("Choose thy class:", YELLOW))
    await session.send_line()
    for i, (cls, stats) in enumerate(CLASSES.items(), 1):
        await session.send_line(
            f"  {color(f'[{i}]', YELLOW)} {color(cls, WHITE)} - {stats['desc']}"
        )
        await session.send_line(
            f"      HP:{stats['hp']} MP:{stats['mp']} ATK:{stats['atk']} "
            f"DEF:{stats['def']} SPD:{stats['spd']}"
        )
    await session.send_line()

    cls_choice = 0
    class_names = list(CLASSES.keys())
    while cls_choice < 1 or cls_choice > 4:
        inp = await session.get_char("Class (1-4): ")
        try:
            cls_choice = int(inp)
        except ValueError:
            pass

    chosen_class = class_names[cls_choice - 1]
    stats = CLASSES[chosen_class]

    await session.send_line()
    await session.send_line(color("Choose thy fate:", YELLOW))
    await session.send_line(
        f"  {color('[1]', YELLOW)} {color('NORMAL', GREEN)} "
        "- Respawn on death, keep your save"
    )
    await session.send_line(
        f"  {color('[2]', YELLOW)} {color('HARDCORE', RED)} "
        "- Permadeath! Save erased on death. +50% XP & gold"
    )
    await session.send_line()
    hardcore = False
    while True:
        mode = await session.get_char("Mode (1-2): ")
        if mode == '2':
            hardcore = True
            await session.send_line(color("\r\n  You have chosen the path of no return!", RED))
            break
        elif mode == '1':
            await session.send_line(
                color("\r\n  A wise choice. Death is but a setback.", GREEN)
            )
            break

    await session.send_line()
    await session.send_line(color("Rolling bonus stats...", DIM))
    bonus = random.randint(1, 6) + random.randint(1, 6) + random.randint(1, 6)
    await session.send_line(f"  Bonus points: {color(str(bonus), GREEN)}")

    session.char = {
        "name": name,
        "class": chosen_class,
        "level": 1,
        "xp": 0,
        "xp_next": 100,
        "hp": stats["hp"] + bonus,
        "max_hp": stats["hp"] + bonus,
        "mp": stats["mp"] + (bonus // 2 if stats["mp"] > 0 else 0),
        "max_mp": stats["mp"] + (bonus // 2 if stats["mp"] > 0 else 0),
        "base_atk": stats["atk"],
        "base_def": stats["def"],
        "spd": stats["spd"] + random.randint(0, 2),
        "gold": 50,
        "weapon": 0,
        "armor": 0,
        "potions": 3,
        "floor": OVERWORLD_FLOOR,
        "x": get_overworld_spawn()[0],
        "y": get_overworld_spawn()[1],
        "facing": SOUTH,
        "explored": {},
        "treasures_found": [],
        "poisoned": False,
        "kills": 0,
        "hardcore": hardcore,
    }

    save_character(session.char)

    await session.send_line()
    await session.send_line(color(f"{name} the {chosen_class} enters the dungeon!", GREEN))
    await session.send_line(color("Press any key to begin...", DIM))
    await session.get_char()


async def load_character_menu(session, world):
    """Show saved characters and load one. Returns True if loaded, False if cancelled."""
    saves = list_saves()
    if not saves:
        await session.send_line(color("No saved characters found!", RED))
        await session.send_line()
        return False

    await session.send(CLEAR)
    await session.send_line(color("=== LOAD CHARACTER ===", CYAN))
    await session.send_line()
    for i, name in enumerate(saves, 1):
        char = load_character(name)
        if char:
            mode_tag = color(" [HC]", RED) if char.get('hardcore', False) else ""
            await session.send_line(
                f"  {color(f'[{i}]', YELLOW)} {char['name']} - Lv.{char['level']} "
                f"{char['class']} (Floor {char['floor']+1}){mode_tag}"
            )
    await session.send_line()

    while True:
        inp = await session.get_char(f"Choose (1-{len(saves)}, 0=back): ")
        if inp == '0':
            return False
        try:
            idx = int(inp) - 1
            if 0 <= idx < len(saves):
                session.char = load_character(saves[idx])
                if session.char:
                    if world.is_banned(session.char['name']):
                        await session.send_line(
                            color(f"\r\n{session.char['name']} is BANNED!", RED)
                        )
                        session.char = None
                        await session.get_char("Press any key...")
                        return False
                    if session.char['name'] in world.sessions:
                        await session.send_line(
                            color(f"\r\n{session.char['name']} is already logged in!", RED)
                        )
                        session.char = None
                        await session.get_char("Press any key...")
                        return False
                if session.char['hp'] <= 0:
                    session.char['hp'] = session.char['max_hp'] // 2
                    session.char['floor'] = OVERWORLD_FLOOR
                    session.char['x'] = get_overworld_spawn()[0]
                    session.char['y'] = get_overworld_spawn()[1]
                    session.char['poisoned'] = False
                    save_character(session.char)
                    await session.send_line(
                        color(f"\r\n{session.char['name']} was found unconscious at the entrance...", YELLOW)
                    )
                else:
                    await session.send_line(
                        color(f"\r\nWelcome back, {session.char['name']}!", GREEN)
                    )
                await session.get_char("Press any key...")
                return True
        except ValueError:
            pass
