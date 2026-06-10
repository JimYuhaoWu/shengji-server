"""Tests for room.py Room class."""

import asyncio
import pytest
import time
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, timedelta
from room import Room


@pytest.fixture
def mock_game():
    """Create a mock Game instance."""
    game = Mock()
    game.reset = Mock(return_value=Mock(phase="DEALING"))
    return game


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


@pytest.fixture
def room(mock_game):
    """Create a Room instance for testing."""
    return Room("test_room", mock_game)


class TestRoomInit:
    def test_room_initialization(self, room):
        """Test room is properly initialized."""
        assert room.room_id == "test_room"
        assert room.state is not None
        assert room.get_connected_count() == 0
        assert room.created_at is not None
        assert room.last_activity is not None

    def test_room_calls_game_reset(self, mock_game):
        """Test that room calls game.reset on initialization."""
        room = Room("test", mock_game)
        mock_game.reset.assert_called_once_with(dealer_id=0)


class TestAddConnection:
    def test_add_connection(self, room, mock_websocket):
        """Test adding a player connection."""
        room.add_connection(0, mock_websocket)
        assert room.has_player(0)
        assert room.get_connected_count() == 1

    def test_add_multiple_connections(self, room, mock_websocket):
        """Test adding multiple player connections."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        room.add_connection(0, ws1)
        room.add_connection(1, ws2)
        room.add_connection(5, ws3)

        assert room.get_connected_count() == 3
        assert room.has_player(0)
        assert room.has_player(1)
        assert room.has_player(5)

    def test_add_duplicate_connection(self, room, mock_websocket):
        """Test that adding duplicate player raises error."""
        room.add_connection(0, mock_websocket)
        with pytest.raises(ValueError, match="already connected"):
            room.add_connection(0, mock_websocket)

    def test_add_invalid_player_id_negative(self, room, mock_websocket):
        """Test that negative player_id raises error."""
        with pytest.raises(ValueError, match="Invalid player_id"):
            room.add_connection(-1, mock_websocket)

    def test_add_invalid_player_id_too_high(self, room, mock_websocket):
        """Test that player_id > 5 raises error."""
        with pytest.raises(ValueError, match="Invalid player_id"):
            room.add_connection(6, mock_websocket)

    def test_add_connection_updates_last_activity(self, room, mock_websocket):
        """Test that adding connection updates last_activity."""
        old_activity = room.last_activity
        time.sleep(0.01)  # Ensure time passes
        room.add_connection(0, mock_websocket)
        assert room.last_activity >= old_activity


class TestRemoveConnection:
    def test_remove_connection(self, room, mock_websocket):
        """Test removing a player connection."""
        room.add_connection(0, mock_websocket)
        assert room.has_player(0)

        room.remove_connection(0)
        assert not room.has_player(0)
        assert room.get_connected_count() == 0

    def test_remove_nonexistent_connection(self, room):
        """Test removing nonexistent player doesn't error."""
        room.remove_connection(0)  # Should not raise
        assert room.get_connected_count() == 0

    def test_remove_connection_updates_last_activity(self, room, mock_websocket):
        """Test that removing connection updates last_activity."""
        room.add_connection(0, mock_websocket)
        old_activity = room.last_activity
        time.sleep(0.01)  # Ensure time passes
        room.remove_connection(0)
        assert room.last_activity >= old_activity


class TestGetConnectedPlayers:
    def test_get_connected_players_empty(self, room):
        """Test get_connected_players when no one is connected."""
        assert room.get_connected_players() == []

    def test_get_connected_players_sorted(self, room, mock_websocket):
        """Test get_connected_players returns sorted list."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()

        room.add_connection(5, ws1)
        room.add_connection(1, ws2)
        room.add_connection(3, ws3)

        assert room.get_connected_players() == [1, 3, 5]


class TestGetConnectedCount:
    def test_get_connected_count(self, room, mock_websocket):
        """Test counting connected players."""
        assert room.get_connected_count() == 0

        for i in range(3):
            ws = AsyncMock()
            room.add_connection(i, ws)

        assert room.get_connected_count() == 3


class TestIsFull:
    def test_is_full_false(self, room, mock_websocket):
        """Test is_full returns False when not all players connected."""
        for i in range(5):
            ws = AsyncMock()
            room.add_connection(i, ws)
        assert room.is_full() is False

    def test_is_full_true(self, room):
        """Test is_full returns True when all 6 players connected."""
        for i in range(6):
            ws = AsyncMock()
            room.add_connection(i, ws)
        assert room.is_full() is True


class TestGetPhase:
    def test_get_phase(self, room):
        """Test getting game phase."""
        # Mock state has phase="DEALING"
        phase = room.get_phase()
        assert phase == "DEALING"


class TestHasPlayer:
    def test_has_player_true(self, room, mock_websocket):
        """Test has_player returns True for connected player."""
        room.add_connection(2, mock_websocket)
        assert room.has_player(2) is True

    def test_has_player_false(self, room):
        """Test has_player returns False for disconnected player."""
        assert room.has_player(2) is False


@pytest.mark.asyncio
class TestBroadcast:
    async def test_broadcast_to_all(self, room):
        """Test broadcasting message to all connected players."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        room.add_connection(0, ws1)
        room.add_connection(1, ws2)

        await room.broadcast({"type": "test", "data": "hello"})

        ws1.send_json.assert_called_once()
        ws2.send_json.assert_called_once()

    async def test_broadcast_exclude_player(self, room):
        """Test broadcasting with excluded player."""
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        room.add_connection(0, ws1)
        room.add_connection(1, ws2)

        await room.broadcast({"type": "test"}, exclude_player=0)

        ws1.send_json.assert_not_called()
        ws2.send_json.assert_called_once()

    async def test_broadcast_empty_room(self, room):
        """Test broadcasting to empty room doesn't error."""
        await room.broadcast({"type": "test"})  # Should not raise

    async def test_broadcast_updates_last_activity(self, room):
        """Test that broadcast updates last_activity."""
        ws = AsyncMock()
        room.add_connection(0, ws)
        old_activity = room.last_activity
        await asyncio.sleep(0.01)  # Ensure time passes

        await room.broadcast({"type": "test"})

        assert room.last_activity >= old_activity


@pytest.mark.asyncio
class TestBroadcastState:
    async def test_broadcast_state(self, room):
        """Test broadcasting game state."""
        ws = AsyncMock()
        room.add_connection(0, ws)

        state_data = {
            "phase": "TRICK_PLAYING",
            "current_player": 1,
        }

        await room.broadcast_state(state_data)

        ws.send_json.assert_called_once()
        call_args = ws.send_json.call_args[0][0]
        assert call_args["type"] == "state_update"
        assert call_args["phase"] == "TRICK_PLAYING"


class TestIsStale:
    def test_is_stale_false_new_room(self, room):
        """Test that new room is not stale."""
        assert room.is_stale() is False

    def test_is_stale_true_old_room(self, room):
        """Test that old room is stale."""
        # Set last_activity to 2 hours ago
        room.last_activity = datetime.now() - timedelta(hours=2)
        assert room.is_stale(max_age_seconds=3600) is True

    def test_is_stale_custom_timeout(self, room):
        """Test is_stale with custom timeout."""
        # Set last_activity to 305 seconds ago (> 300 second threshold)
        room.last_activity = datetime.now() - timedelta(seconds=305)
        assert room.is_stale(max_age_seconds=300) is True
        assert room.is_stale(max_age_seconds=600) is False


class TestGetStats:
    def test_get_stats(self, room):
        """Test getting room statistics."""
        stats = room.get_stats()
        assert stats["room_id"] == "test_room"
        assert stats["connected_players"] == 0
        assert stats["is_full"] is False
        assert stats["phase"] == "DEALING"
        assert "created_at" in stats
        assert "last_activity" in stats
        assert "player_ids" in stats

    def test_get_stats_with_players(self, room):
        """Test stats with connected players."""
        for i in range(3):
            ws = AsyncMock()
            room.add_connection(i, ws)

        stats = room.get_stats()
        assert stats["connected_players"] == 3
        assert stats["is_full"] is False
        assert stats["player_ids"] == [0, 1, 2]
