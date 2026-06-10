"""Room: owns one Game instance, its current GameState, and player connections.

One Game per Room (CLAUDE.md principle #5). The room never enforces rules — it
holds the engine, tracks who's connected, and broadcasts. Action handling lives
in game_loop.py.
"""

import asyncio
from datetime import datetime

from fastapi import WebSocket

from shengji import Game, GameState
from serializer import serialize_for_player


class Room:
    """A single game room."""

    def __init__(self, room_id: str, dealer_id: int = 0):
        self.room_id = room_id
        self.game = Game(num_players=6)
        self.state: GameState = self.game.reset(dealer_id=dealer_id)
        self.connections: dict[int, WebSocket] = {}  # player_id -> WebSocket
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

    # ---- connection management ----

    def add_connection(self, player_id: int, websocket: WebSocket) -> None:
        """Register a player's WebSocket.

        Raises:
            ValueError: if player_id is out of range or already connected.
        """
        if not (0 <= player_id <= 5):
            raise ValueError(f"Invalid player_id: {player_id}")
        if player_id in self.connections:
            raise ValueError(f"Player {player_id} already connected")
        self.connections[player_id] = websocket
        self.last_activity = datetime.now()

    def remove_connection(self, player_id: int) -> None:
        """Drop a player's connection (no-op if absent)."""
        self.connections.pop(player_id, None)
        self.last_activity = datetime.now()

    def has_player(self, player_id: int) -> bool:
        return player_id in self.connections

    def connected_count(self) -> int:
        return len(self.connections)

    def is_full(self) -> bool:
        return len(self.connections) == 6

    # ---- broadcasting ----

    async def send_to(self, player_id: int, message: dict) -> None:
        """Send one message to one player, swallowing send failures."""
        ws = self.connections.get(player_id)
        if ws is None:
            return
        try:
            await ws.send_json(message)
        except Exception:
            pass

    async def broadcast(self, message: dict, exclude: int | None = None) -> None:
        """Send the same message to all connected players concurrently."""
        tasks = [
            self.send_to(pid, message)
            for pid in self.connections
            if pid != exclude
        ]
        if tasks:
            await asyncio.gather(*tasks)
        self.last_activity = datetime.now()

    async def broadcast_state(self) -> None:
        """Send each connected player their privacy-filtered view of the state."""
        tasks = []
        for pid in self.connections:
            payload = serialize_for_player(self.state, pid)
            tasks.append(self.send_to(pid, {"type": "state_update", **payload}))
        if tasks:
            await asyncio.gather(*tasks)
        self.last_activity = datetime.now()

    # ---- housekeeping ----

    def is_stale(self, max_age_seconds: int = 3600) -> bool:
        """True if inactive longer than max_age_seconds (default 1 hour)."""
        return (datetime.now() - self.last_activity).total_seconds() > max_age_seconds

    def status(self) -> dict:
        """Lightweight status for the REST endpoint."""
        return {
            "room_id": self.room_id,
            "connected_players": self.connected_count(),
            "game_phase": self.state.phase.name,
            "current_player": self.state.current_player,
            "started": True,
        }
