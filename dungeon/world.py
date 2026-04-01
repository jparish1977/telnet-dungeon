"""Shared world state — player registry, broadcasting, bans."""

from dungeon.config import WHITE, YELLOW, RED, MAGENTA, color
from dungeon.persistence import load_bans, save_bans


class World:
    """Shared state for all connected players."""

    def __init__(self):
        self.sessions = {}       # name -> GameSession
        self.global_log = []     # recent global messages
        self.max_log = 50
        self.banned = load_bans()

    def add_player(self, session):
        if session.char:
            self.sessions[session.char['name']] = session

    def remove_player(self, session):
        if session.char and session.char['name'] in self.sessions:
            self.broadcast(
                f"{session.char['name']} has left the dungeon.",
                MAGENTA, exclude=session,
            )
            del self.sessions[session.char['name']]

    def get_players_on_floor(self, floor, exclude_name=None):
        """Get list of (name, x, y, facing) for all players on a floor."""
        players = []
        for name, s in self.sessions.items():
            if s.char and s.char['floor'] == floor and name != exclude_name:
                players.append((name, s.char['x'], s.char['y'], s.char['facing']))
        return players

    def get_players_at(self, floor, x, y, exclude_name=None):
        """Get sessions of players at a specific tile."""
        result = []
        for name, s in self.sessions.items():
            if (s.char and s.char['floor'] == floor
                    and s.char['x'] == x and s.char['y'] == y
                    and name != exclude_name):
                result.append(s)
        return result

    def broadcast(self, msg, msg_color=WHITE, exclude=None):
        """Send a message to all connected players."""
        formatted = color(msg, msg_color)
        self.global_log.append(formatted)
        if len(self.global_log) > self.max_log:
            self.global_log.pop(0)
        for name, s in self.sessions.items():
            if s != exclude:
                s.message_log.append(formatted)
                s.notify_event.set()

    def chat(self, sender, msg):
        """Broadcast a chat message from a player."""
        formatted = f"{color(sender, YELLOW)}: {msg}"
        self.global_log.append(formatted)
        if len(self.global_log) > self.max_log:
            self.global_log.pop(0)
        for name, s in self.sessions.items():
            s.message_log.append(formatted)
            s.notify_event.set()

    def player_count(self):
        return len(self.sessions)

    def is_banned(self, name):
        return name.lower() in self.banned

    def ban_player(self, name):
        lname = name.lower()
        if lname not in self.banned:
            self.banned.append(lname)
            save_bans(self.banned)

    def unban_player(self, name):
        lname = name.lower()
        if lname in self.banned:
            self.banned.remove(lname)
            save_bans(self.banned)

    async def kick_player(self, name, reason="Kicked by GM"):
        if name in self.sessions:
            s = self.sessions[name]
            try:
                await s.send_line(color(f"\r\n*** {reason} ***", RED))
                s.running = False
                await s.io.close()
            except Exception:
                pass
            self.broadcast(f"{name} was kicked: {reason}", RED)
            if name in self.sessions:
                del self.sessions[name]
            return True
        return False
