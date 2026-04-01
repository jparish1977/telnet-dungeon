"""Shop interaction — buy weapons, armor, and potions."""

from dungeon.config import CLEAR, RED, GREEN, YELLOW, WHITE, color
from dungeon.items import WEAPONS, ARMOR


async def run_shop(session):
    """Visit the shop at the entrance. Takes a GameSession."""
    char = session.char
    while True:
        await session.send(CLEAR)
        await session.send_line(color("=== YE OLDE SHOPPE ===", YELLOW))
        await session.send_line()
        await session.send_line(f"  Gold: {color(str(char['gold']), YELLOW)}")
        await session.send_line(f"  Current Weapon: {WEAPONS[char['weapon']]['name']}")
        await session.send_line(f"  Current Armor:  {ARMOR[char['armor']]['name']}")
        await session.send_line()
        await session.send_line(
            f"  {color('[W]', YELLOW)}eapons  {color('[A]', YELLOW)}rmor  "
            f"{color('[P]', YELLOW)}otions  {color('[L]', YELLOW)}eave"
        )

        choice = (await session.get_char("  Choice: ")).upper()

        if choice == 'W':
            await session.send_line()
            await session.send_line(color("  WEAPONS:", WHITE))
            for i, w in enumerate(WEAPONS):
                owned = " (equipped)" if i == char['weapon'] else ""
                price = f"{w['price']}g" if w['price'] > 0 else "---"
                await session.send_line(
                    f"    [{i+1}] {w['name']:20s} ATK+{w['atk']:2d}  {price}{owned}"
                )
            await session.send_line()
            inp = await session.get_char("    Buy (0=cancel): ")
            try:
                idx = int(inp) - 1
                if 0 <= idx < len(WEAPONS):
                    w = WEAPONS[idx]
                    if idx <= char['weapon']:
                        session.log("You already have equal or better!")
                    elif char['gold'] >= w['price']:
                        char['gold'] -= w['price']
                        char['weapon'] = idx
                        session.log(color(f"Bought {w['name']}!", GREEN))
                    else:
                        session.log(color("Not enough gold!", RED))
            except ValueError:
                pass

        elif choice == 'A':
            await session.send_line()
            await session.send_line(color("  ARMOR:", WHITE))
            for i, a in enumerate(ARMOR):
                owned = " (equipped)" if i == char['armor'] else ""
                price = f"{a['price']}g" if a['price'] > 0 else "---"
                await session.send_line(
                    f"    [{i+1}] {a['name']:20s} DEF+{a['def']:2d}  {price}{owned}"
                )
            await session.send_line()
            inp = await session.get_char("    Buy (0=cancel): ")
            try:
                idx = int(inp) - 1
                if 0 <= idx < len(ARMOR):
                    a = ARMOR[idx]
                    if idx <= char['armor']:
                        session.log("You already have equal or better!")
                    elif char['gold'] >= a['price']:
                        char['gold'] -= a['price']
                        char['armor'] = idx
                        session.log(color(f"Bought {a['name']}!", GREEN))
                    else:
                        session.log(color("Not enough gold!", RED))
            except ValueError:
                pass

        elif choice == 'P':
            price = 25
            await session.send_line(
                f"\n  Potions: {price}g each. You have {char['potions']}."
            )
            inp = await session.get_input("  How many? ")
            try:
                qty = int(inp)
                cost = qty * price
                if cost <= char['gold'] and qty > 0:
                    char['gold'] -= cost
                    char['potions'] += qty
                    session.log(color(f"Bought {qty} potions!", GREEN))
                elif qty > 0:
                    session.log(color("Not enough gold!", RED))
            except ValueError:
                pass

        elif choice == 'L':
            break

        # Show messages
        for msg in session.message_log:
            await session.send_line(f"  {msg}")
        session.message_log.clear()
