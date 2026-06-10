"""Tests for game_loop.py — action handling against the real engine."""

from unittest.mock import AsyncMock

import pytest

from shengji import GamePhase

from room import Room
from game_loop import handle_action, handle_join, is_action_message


def make_room_with_players():
    """A room with all six players connected via AsyncMock sockets."""
    room = Room("g1")
    socks = {}
    for pid in range(6):
        s = AsyncMock()
        room.add_connection(pid, s)
        socks[pid] = s
    return room, socks


def last_message(sock):
    return sock.send_json.call_args[0][0]


class TestIsActionMessage:
    def test_action_types(self):
        assert is_action_message({"type": "play_cards"})
        assert is_action_message({"type": "action"})
        assert not is_action_message({"type": "join"})
        assert not is_action_message({"type": "whatever"})


@pytest.mark.asyncio
class TestTurnEnforcement:
    async def test_not_your_turn(self):
        room, socks = make_room_with_players()
        wrong = (room.state.current_player + 1) % 6
        await handle_action(room, wrong, {"type": "action", "index": 0})
        assert last_message(socks[wrong]) == {"type": "error", "message": "Not your turn"}

    async def test_bad_index(self):
        room, socks = make_room_with_players()
        cur = room.state.current_player
        await handle_action(room, cur, {"type": "action", "index": 9999})
        assert last_message(socks[cur])["type"] == "error"


@pytest.mark.asyncio
class TestActionApplication:
    async def test_index_path_advances_and_broadcasts(self):
        room, socks = make_room_with_players()
        cur = room.state.current_player
        before = room.state
        await handle_action(room, cur, {"type": "action", "index": 0})
        # State advanced (new object) and everyone got a state_update.
        assert room.state is not before
        for pid in range(6):
            assert last_message(socks[pid])["type"] == "state_update"

    async def test_semantic_pass_trump(self):
        room, socks = make_room_with_players()
        cur = room.state.current_player
        # pass_trump is always legal during DEALING.
        await handle_action(room, cur, {"type": "pass_trump"})
        assert last_message(socks[cur])["type"] == "state_update"

    async def test_illegal_semantic_move_rejected(self):
        room, socks = make_room_with_players()
        cur = room.state.current_player
        # Playing cards is illegal during DEALING.
        await handle_action(
            room, cur,
            {"type": "play_cards", "cards": [{"suit": "H", "rank": "7", "deck_id": 0}]},
        )
        assert last_message(socks[cur]) == {"type": "error", "message": "Illegal move"}


@pytest.mark.asyncio
class TestJoin:
    async def test_handle_join_sends_state(self):
        room, socks = make_room_with_players()
        await handle_join(room, 2)
        msg = last_message(socks[2])
        assert msg["type"] == "state_update"
        assert msg["your_player_id"] == 2


@pytest.mark.asyncio
class TestFullPlaythrough:
    async def test_full_game_via_loop_reaches_game_over(self):
        room, socks = make_room_with_players()

        steps = 0
        while room.state.phase != GamePhase.SCORING and steps < 5000:
            cur = room.state.current_player
            await handle_action(room, cur, {"type": "action", "index": 0})
            steps += 1

        assert room.state.phase == GamePhase.SCORING

        # Every player should have received a game_over message last.
        for pid in range(6):
            assert last_message(socks[pid])["type"] == "game_over"
        go = last_message(socks[0])
        assert "farmer_score" in go
        assert "next_dealer" in go
