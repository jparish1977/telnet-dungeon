#!/usr/bin/env python3
"""
Telnet Dungeon Crawler - BBS-style multiplayer dungeon game
Run: python dungeon_server.py [port]
Connect: telnet localhost 2323
"""

import asyncio
import sys
import random

from dungeon.config import CYAN, GREEN, PORT, YELLOW, color
from dungeon.items import ARMOR, SPELLS, WEAPONS
from dungeon.protocol.telnet import TelnetAdapter



from dungeon.world import World
from dungeon.shop import run_shop
from dungeon.combat import run_combat, handle_game_over, handle_pvp_death, _bar
from dungeon.menus import (
    title_screen as _title_screen,
    create_character as _create_character,
    load_character_menu as _load_character_menu,
)
from dungeon.gm.tools import (
    gm_pick_player as _gm_pick_player,
    gm_menu as _gm_menu,
)
from dungeon.session import (
    draw_game_screen as _draw_game_screen,
    run_main_loop as _run_main_loop,
    character_screen as _character_screen,
)

WORLD = World()



# ── Game Session ───────────────────────────────────────────────────
class GameSession:
    def __init__(self, reader=None, writer=None, adapter=None):
        self.io = adapter if adapter else TelnetAdapter(reader, writer)
        self.char = None
        self.running = True
        self.message_log = []
        self.combat_shield_bonus = 0
        self.is_gm = False

    # ── I/O delegation ────────────────────────────────────────────
    # These delegate to self.io so existing code (self.send, self.get_char, etc.)
    # continues to work without changing every call site at once.

    async def send(self, text):
        await self.io.send(text)

    async def send_line(self, text=""):
        await self.io.send_line(text)

    async def move_to(self, row, col):
        await self.io.move_to(row, col)

    async def clear_row(self, row):
        await self.io.clear_row(row)

    async def get_input(self, prompt="> ", preserve_spaces=False, prefill=""):
        result = await self.io.get_input(prompt, preserve_spaces, prefill)
        if not self.io.running:
            self.running = False
        return result

    async def get_char(self, prompt="", redraw_on_resize=False):
        result = await self.io.get_char(prompt, redraw_on_resize)
        if not self.io.running:
            self.running = False
        return result

    # ── Terminal state (delegated to adapter) ─────────────────────

    @property
    def term_width(self):
        return self.io.term_width

    @property
    def term_height(self):
        return self.io.term_height

    @property
    def resized(self):
        return self.io.resized

    @resized.setter
    def resized(self, value):
        self.io.resized = value

    @property
    def notify_event(self):
        return self.io.notify_event

    @property
    def writer(self):
        return self.io.writer

    # ── Layout helpers ────────────────────────────────────────────

    def get_view_size(self):
        """Calculate 3D viewport size. Aspect-ratio limited, extra space goes to log."""
        map_radius = self.get_map_radius()
        map_cols = (map_radius * 2 + 1) + 4
        avail_w = self.term_width - map_cols - 4
        vw = max(20, avail_w)
        max_vh = max(8, vw // 3)
        avail_h = self.term_height - 8
        vh = min(max_vh, avail_h)
        return vw, vh

    def get_log_rows(self):
        """How many rows available for the message/chat log below the viewport."""
        vw, vh = self.get_view_size()
        used = 2 + vh + 2 + 2 + 1 + 1
        return max(2, self.term_height - used)

    def get_map_radius(self):
        return max(3, min(7, (self.term_height - 10) // 3))


    def log(self, msg):
        self.message_log.append(msg)
        if len(self.message_log) > 5:
            self.message_log.pop(0)

    async def title_screen(self):
        return await _title_screen(self, WORLD)

    async def create_character(self):
        await _create_character(self, WORLD)

    async def load_character_menu(self):
        return await _load_character_menu(self, WORLD)

    def get_atk(self):
        return self.char['base_atk'] + WEAPONS[self.char['weapon']]['atk']

    def get_def(self):
        return self.char['base_def'] + ARMOR[self.char['armor']]['def'] + self.combat_shield_bonus

    async def check_level_up(self):
        while self.char['xp'] >= self.char['xp_next']:
            self.char['level'] += 1
            self.char['xp'] -= self.char['xp_next']
            self.char['xp_next'] = int(self.char['xp_next'] * 1.5)

            hp_gain = random.randint(3, 8)
            mp_gain = random.randint(1, 4) if self.char['max_mp'] > 0 else 0
            atk_gain = random.randint(0, 2)
            def_gain = random.randint(0, 1)

            self.char['max_hp'] += hp_gain
            self.char['hp'] = self.char['max_hp']
            self.char['max_mp'] += mp_gain
            self.char['mp'] = self.char['max_mp']
            self.char['base_atk'] += atk_gain
            self.char['base_def'] += def_gain

            self.log(color(f"*** LEVEL UP! Now level {self.char['level']}! ***", YELLOW))
            self.log(f"  HP+{hp_gain} MP+{mp_gain} ATK+{atk_gain} DEF+{def_gain}")

            # Learn spells
            for spell_name, spell in SPELLS.items():
                if self.char['level'] >= spell['min_level'] and self.char['max_mp'] > 0:
                    if 'spells' not in self.char:
                        self.char['spells'] = []
                    if spell_name not in self.char['spells']:
                        self.char['spells'].append(spell_name)
                        self.log(color(f"  Learned {spell_name}!", CYAN))

    async def combat(self, monster_template, allies=None):
        return await run_combat(self, monster_template, allies)

    def _bar(self, cur, max_val, width, bar_color):
        return _bar(cur, max_val, width, bar_color)

    async def shop(self):
        await run_shop(self)

    async def game_over(self):
        await handle_game_over(self)

    async def pvp_death(self, killer_name):
        await handle_pvp_death(self, killer_name)

    async def draw_game_screen(self):
        await _draw_game_screen(self, WORLD)

    async def main_loop(self):
        await _run_main_loop(self, WORLD)

    async def gm_pick_player(self, prompt="Pick player: "):
        return await _gm_pick_player(self, WORLD, prompt)

    async def gm_menu(self):
        await _gm_menu(self, WORLD)

    async def character_screen(self):
        await _character_screen(self)

    async def run(self):
        """Main entry point for a game session."""
        await self.io.negotiate()

        while self.running:
            choice = await self.title_screen()

            if choice == 'Q':
                await self.send_line(color("\nFarewell, adventurer!\n", CYAN))
                break

            elif choice == '/':
                # GM tools without a character
                await self.gm_menu()

            elif choice == 'N':
                await self.create_character()
                WORLD.add_player(self)
                WORLD.broadcast(f"{self.char['name']} has entered the dungeon!", GREEN, exclude=self)
                await self.main_loop()
                WORLD.remove_player(self)

            elif choice == 'L':
                if await self.load_character_menu():
                    WORLD.add_player(self)
                    WORLD.broadcast(f"{self.char['name']} has returned to the dungeon!", GREEN, exclude=self)
                    await self.main_loop()
                    WORLD.remove_player(self)

        await self.io.close()


# ── Server ─────────────────────────────────────────────────────────
async def handle_client(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"[+] Connection from {addr} ({WORLD.player_count()} online)")
    session = GameSession(reader, writer)
    try:
        await session.run()
    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        print(f"[-] Error with {addr}: {e}")
    finally:
        WORLD.remove_player(session)
        print(f"[-] Disconnected: {addr} ({WORLD.player_count()} online)")
        try:
            writer.close()
        except Exception:
            pass


async def handle_ws_client(reader, writer):
    """Handle a WebSocket client connection."""
    from dungeon.protocol.websocket import WebSocketAdapter
    addr = writer.get_extra_info('peername')
    print(f"[+] WebSocket from {addr} ({WORLD.player_count()} online)")
    adapter = WebSocketAdapter(reader, writer)
    session = GameSession(adapter=adapter)
    try:
        await session.run()
    except (ConnectionResetError, BrokenPipeError):
        pass
    except Exception as e:
        print(f"[-] WS error with {addr}: {e}")
    finally:
        WORLD.remove_player(session)
        print(f"[-] WS disconnected: {addr} ({WORLD.player_count()} online)")
        try:
            writer.close()
        except Exception:
            pass


WS_PORT = PORT + 1  # WebSocket on telnet port + 1


async def main():
    server = await asyncio.start_server(handle_client, '0.0.0.0', PORT)
    ws_server = await asyncio.start_server(handle_ws_client, '0.0.0.0', WS_PORT)
    print(f"""
+---------------------------------------------------+
|        DUNGEON CRAWLER OF DOOM - BBS Server        |
+---------------------------------------------------+
|  Telnet:    localhost:{PORT:<36d}|
|  WebSocket: localhost:{WS_PORT:<36d}|
+---------------------------------------------------+
""")
    async with server, ws_server:
        await asyncio.gather(
            server.serve_forever(),
            ws_server.serve_forever(),
        )


async def local_play():
    """Run a single-player session locally — no telnet needed."""
    from dungeon.protocol.stdio import StdioAdapter
    adapter = StdioAdapter()
    session = GameSession(adapter=adapter)
    try:
        await session.run()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        WORLD.remove_player(session)


if __name__ == '__main__':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    try:
        if '--local' in sys.argv:
            asyncio.run(local_play())
        else:
            asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shut down.")
