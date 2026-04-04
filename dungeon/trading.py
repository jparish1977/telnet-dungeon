"""Player-to-player trading system."""

import asyncio
from dungeon.config import CLEAR, RED, GREEN, YELLOW, CYAN, WHITE, MAGENTA, DIM, color
from dungeon.persistence import save_character


async def run_direct_trade(session, target_session, world):
    """Direct 1-on-1 trade between two players on same tile."""
    char = session.char
    target_char = target_session.char

    # Get player's offer amount
    await session.send_line()
    await session.send_line(
        color(f"Propose a trade with {target_char['name']}?", CYAN)
    )
    await session.send_line(f"You have: {color(str(char['gold']), YELLOW)}g")

    amount_str = await session.get_input("Offer how much gold? (0=cancel): ")
    try:
        amount = int(amount_str)
        if amount == 0:
            await session.send_line(color("Trade cancelled.", DIM))
            return
        if amount < 0 or amount > char['gold']:
            await session.send_line(color("Invalid amount!", RED))
            return
    except ValueError:
        await session.send_line(color("Invalid amount!", RED))
        return

    # Send trade request to other player
    await session.send_line(
        color(f"Sent trade proposal: {amount}g to {target_char['name']}", YELLOW)
    )

    target_session._trade_pending = True
    target_session.log(
        color(f"{char['name']} proposes trading {amount}g to you! Press [Y] to accept or [N] to decline.", MAGENTA)
    )
    target_session.notify_event.set()

    # Wait for response (up to 20 seconds)
    accepted = False
    for _ in range(40):
        await asyncio.sleep(0.5)
        if hasattr(target_session, '_trade_response'):
            accepted = target_session._trade_response
            del target_session._trade_response
            if hasattr(target_session, '_trade_pending'):
                del target_session._trade_pending
            break
    else:
        # Timeout
        await session.send_line(color(f"{target_char['name']} didn't respond. Trade expired.", DIM))
        if hasattr(target_session, '_trade_pending'):
            del target_session._trade_pending
        return

    if not accepted:
        await session.send_line(color(f"{target_char['name']} declined the trade.", RED))
        return

    # Execute trade
    char['gold'] -= amount
    target_char['gold'] += amount
    target_char['gold'] = min(target_char['gold'], 9999999)

    save_character(char)
    save_character(target_char)

    await session.send_line(
        color(f"✓ Trade complete! You sent {amount}g to {target_char['name']}", GREEN)
    )
    target_session.log(
        color(f"✓ {char['name']} sent you {amount}g!", GREEN)
    )

    world.broadcast(
        f"{char['name']} traded {amount}g with {target_char['name']}",
        MAGENTA
    )
