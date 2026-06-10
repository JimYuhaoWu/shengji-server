"""Tests for room.py — connection management and broadcasting."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from room import Room


@pytest.fixture
def room():
    return Room("r1")


def test_init_starts_in_dealing(room):
    assert room.state.phase.name == "DEALING"
    assert room.connected_count() == 0


class TestConnections:
    def test_add_and_has(self, room):
        room.add_connection(0, AsyncMock())
        assert room.has_player(0)
        assert room.connected_count() == 1

    def test_add_invalid_id(self, room):
        with pytest.raises(ValueError):
            room.add_connection(6, AsyncMock())

    def test_add_duplicate(self, room):
        room.add_connection(0, AsyncMock())
        with pytest.raises(ValueError):
            room.add_connection(0, AsyncMock())

    def test_remove(self, room):
        room.add_connection(0, AsyncMock())
        room.remove_connection(0)
        assert not room.has_player(0)

    def test_remove_absent_is_noop(self, room):
        room.remove_connection(3)  # no raise

    def test_is_full(self, room):
        for i in range(6):
            room.add_connection(i, AsyncMock())
        assert room.is_full()


@pytest.mark.asyncio
class TestBroadcast:
    async def test_broadcast_reaches_all(self, room):
        a, b = AsyncMock(), AsyncMock()
        room.add_connection(0, a)
        room.add_connection(1, b)
        await room.broadcast({"type": "ping"})
        a.send_json.assert_awaited_once_with({"type": "ping"})
        b.send_json.assert_awaited_once_with({"type": "ping"})

    async def test_broadcast_exclude(self, room):
        a, b = AsyncMock(), AsyncMock()
        room.add_connection(0, a)
        room.add_connection(1, b)
        await room.broadcast({"type": "ping"}, exclude=0)
        a.send_json.assert_not_called()
        b.send_json.assert_awaited_once()

    async def test_send_to_swallows_errors(self, room):
        bad = AsyncMock()
        bad.send_json.side_effect = RuntimeError("closed")
        room.add_connection(0, bad)
        await room.send_to(0, {"x": 1})  # no raise

    async def test_broadcast_state_filters_per_player(self, room):
        a, b = AsyncMock(), AsyncMock()
        room.add_connection(0, a)
        room.add_connection(1, b)
        await room.broadcast_state()
        msg0 = a.send_json.call_args[0][0]
        msg1 = b.send_json.call_args[0][0]
        assert msg0["type"] == "state_update"
        assert msg0["your_player_id"] == 0
        assert msg1["your_player_id"] == 1


class TestHousekeeping:
    def test_is_stale(self, room):
        assert not room.is_stale()
        room.last_activity = datetime.now() - timedelta(seconds=3601)
        assert room.is_stale()

    def test_status(self, room):
        s = room.status()
        assert s["room_id"] == "r1"
        assert s["game_phase"] == "DEALING"
        assert s["connected_players"] == 0


class TestReconnect:
    def test_disconnect_marks_player_offline(self, room):
        room.add_connection(0, AsyncMock())
        room.remove_connection(0)
        assert not room.has_player(0)
        assert room.is_reconnecting(0)

    def test_reconnect_within_grace_period(self, room):
        room.add_connection(0, AsyncMock())
        room.remove_connection(0)
        # Immediately reconnect should be allowed.
        assert room.is_reconnecting(0)
        new_ws = AsyncMock()
        room.restore_connection(0, new_ws)
        assert room.has_player(0)
        assert room.connections[0] is new_ws
        assert not room.is_reconnecting(0)

    def test_reconnect_after_grace_period_expires(self, room):
        room.add_connection(0, AsyncMock())
        room.remove_connection(0)
        # Simulate grace period expiring.
        room.disconnected_at[0] = datetime.now() - timedelta(seconds=301)
        # is_reconnecting should return False and clean up.
        assert not room.is_reconnecting(0)
        assert 0 not in room.disconnected_at
