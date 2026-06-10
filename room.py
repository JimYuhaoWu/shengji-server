"""Room management for game state and player connections."""

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING
from fastapi import WebSocket

if TYPE_CHECKING:
    # Type hints only - shengji-engine should be installed separately
    from shengji_engine import Game, GameState


class Room:
    """Manages a single game room with player connections and game state."""

    def __init__(self, room_id: str, game: "Game"):
        """Initialize a room with a game instance.

        Args:
            room_id: Unique identifier for the room
            game: Game instance from shengji-engine
        """
        self.room_id = room_id
        self.game = game
        self.connections: dict[int, WebSocket] = {}  # player_id -> WebSocket
        self.state = game.reset(dealer_id=0)  # Initial game state
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

    def add_connection(self, player_id: int, websocket: WebSocket) -> None:
        """Add a player connection to the room.

        Args:
            player_id: The player ID (0-5)
            websocket: The WebSocket connection

        Raises:
            ValueError: If player already connected or player_id invalid
        """
        if not (0 <= player_id <= 5):
            raise ValueError(f"Invalid player_id: {player_id}")

        if player_id in self.connections:
            raise ValueError(f"Player {player_id} already connected")

        self.connections[player_id] = websocket
        self.last_activity = datetime.now()

    def remove_connection(self, player_id: int) -> None:
        """Remove a player connection from the room.

        Args:
            player_id: The player ID to disconnect
        """
        self.connections.pop(player_id, None)
        self.last_activity = datetime.now()

    def get_connected_players(self) -> list[int]:
        """Get list of connected player IDs.

        Returns:
            List of player IDs currently connected
        """
        return sorted(self.connections.keys())

    def get_connected_count(self) -> int:
        """Get number of connected players.

        Returns:
            Number of players currently connected
        """
        return len(self.connections)

    def is_full(self) -> bool:
        """Check if room has all 6 players connected.

        Returns:
            True if 6 players are connected, False otherwise
        """
        return len(self.connections) == 6

    def get_phase(self) -> str | None:
        """Get current game phase.

        Returns:
            The current game phase (e.g., "DEALING", "TRICK_PLAYING") or None if not started
        """
        if self.state is None:
            return None
        return str(self.state.phase)

    def has_player(self, player_id: int) -> bool:
        """Check if a player is connected.

        Args:
            player_id: The player ID to check

        Returns:
            True if player is connected, False otherwise
        """
        return player_id in self.connections

    async def broadcast(self, message: dict, exclude_player: int | None = None) -> None:
        """Broadcast a message to all connected players.

        Args:
            message: The message to broadcast (will be JSON encoded)
            exclude_player: Optional player ID to exclude from broadcast
        """
        import json

        tasks = []
        for player_id, ws in self.connections.items():
            if exclude_player is not None and player_id == exclude_player:
                continue

            async def send_message(ws: WebSocket, msg: dict) -> None:
                try:
                    await ws.send_json(msg)
                except:
                    pass  # Connection may have been closed

            tasks.append(send_message(ws, message))

        if tasks:
            await asyncio.gather(*tasks)

        self.last_activity = datetime.now()

    async def broadcast_state(self, serialized_state: dict) -> None:
        """Broadcast game state to all connected players.

        Note: Caller (serializer.py) is responsible for filtering state per player.

        Args:
            serialized_state: Pre-serialized game state (player-specific filtering should be done by caller)
        """
        await self.broadcast({"type": "state_update", **serialized_state})

    def is_stale(self, max_age_seconds: int = 3600) -> bool:
        """Check if room is stale (inactive for too long).

        Args:
            max_age_seconds: Maximum age in seconds (default 1 hour)

        Returns:
            True if room has been inactive longer than max_age_seconds
        """
        age = (datetime.now() - self.last_activity).total_seconds()
        return age > max_age_seconds

    def get_stats(self) -> dict:
        """Get room statistics for debugging.

        Returns:
            Dictionary with room stats
        """
        return {
            "room_id": self.room_id,
            "connected_players": self.get_connected_count(),
            "is_full": self.is_full(),
            "phase": self.get_phase(),
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "player_ids": self.get_connected_players(),
        }
