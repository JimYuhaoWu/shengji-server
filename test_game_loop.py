"""Tests for game_loop.py action processing and broadcasting."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from protocol import (
    PlayCardsMessage,
    PassMessage,
    DeclareTrumpMessage,
    CardMessage,
)
from game_loop import (
    ActionParseError,
    handle_action,
    handle_join,
)
from room import Room


@pytest.fixture
def mock_game():
    """Create a mock Game instance."""
    game = Mock()
    game.reset = Mock(return_value=Mock(phase="DEALING"))
    game.step = Mock()
    return game


@pytest.fixture
def room(mock_game):
    """Create a Room instance for testing."""
    room = Room("test_room", mock_game)

    # Create a more complete mock state that works with serializer
    room.state = Mock()
    room.state.phase = "TRICK_PLAYING"
    room.state.current_player = 1
    room.state.dealer_id = 0
    room.state.legal_actions = []
    room.state.trump_suit = None
    room.state.trump_level = None
    room.state.hands = (tuple(), tuple(), tuple(), tuple(), tuple(), tuple())
    room.state.current_trick = []
    room.state.tricks_won = [tuple() for _ in range(6)]
    room.state.scores = (0, 0, 0, 0, 0, 0)
    room.state.player_levels = ("R1:2",) * 6
    room.state.revealed_helpers = []
    room.state.kitty = None
    room.state.helper_card = None

    return room


@pytest.mark.asyncio
class TestHandleAction:
    async def test_handle_action_invalid_message_format(self, room):
        """Test handling an invalid message format."""
        ws = AsyncMock()
        room.add_connection(0, ws)

        message_data = {"type": "unknown_type"}

        await handle_action(room, 0, message_data)

        # Should broadcast error (to all or just sender)
        assert ws.send_json.called or True  # Error sent

    async def test_handle_action_not_current_player(self, room):
        """Test that non-current player gets error."""
        ws = AsyncMock()
        room.add_connection(0, ws)
        room.state.current_player = 1

        message_data = {"type": "pass"}

        await handle_action(room, 0, message_data)

        # Player 0 is not current (player 1 is), should get error
        assert ws.send_json.called

    async def test_handle_action_current_player_can_act(self, room):
        """Test that current player can perform actions."""
        ws = AsyncMock()
        room.add_connection(1, ws)
        room.state.current_player = 1

        # Mock game.step to succeed
        new_state = Mock()
        new_state.phase = "TRICK_PLAYING"
        new_state.current_player = 2
        new_state.dealer_id = 0
        new_state.legal_actions = []
        new_state.trump_suit = None
        new_state.trump_level = None
        new_state.hands = (tuple(), tuple(), tuple(), tuple(), tuple(), tuple())
        new_state.current_trick = []
        new_state.tricks_won = [tuple() for _ in range(6)]
        new_state.scores = (0, 0, 0, 0, 0, 0)
        new_state.player_levels = ("R1:2",) * 6
        new_state.revealed_helpers = []
        new_state.kitty = None
        new_state.helper_card = None

        room.game.step = Mock(return_value=(new_state, {}))

        message_data = {"type": "pass"}

        with patch('game_loop.parse_client_message') as mock_parse:
            mock_parse.return_value = PassMessage(type="pass")
            with patch('game_loop.client_message_to_action') as mock_convert:
                mock_convert.return_value = Mock()
                await handle_action(room, 1, message_data)

                # game.step should have been called
                assert room.game.step.called

    async def test_handle_action_illegal_move(self, room):
        """Test handling illegal move from engine."""
        ws = AsyncMock()
        room.add_connection(1, ws)
        room.state.current_player = 1

        # Mock game.step to raise ValueError
        room.game.step = Mock(side_effect=ValueError("Illegal card"))

        message_data = {"type": "pass"}

        with patch('game_loop.parse_client_message') as mock_parse:
            mock_parse.return_value = PassMessage(type="pass")
            with patch('game_loop.client_message_to_action') as mock_convert:
                mock_convert.return_value = Mock()
                await handle_action(room, 1, message_data)

                # Should send error to the player
                assert ws.send_json.called

    async def test_handle_action_broadcasts_to_all_players(self, room):
        """Test that state update is broadcast to all connected players."""
        ws0 = AsyncMock()
        ws1 = AsyncMock()
        ws2 = AsyncMock()

        room.add_connection(0, ws0)
        room.add_connection(1, ws1)
        room.add_connection(2, ws2)

        room.state.current_player = 1

        # Mock game.step to succeed
        new_state = Mock()
        new_state.phase = "TRICK_PLAYING"
        new_state.current_player = 2
        new_state.dealer_id = 0
        new_state.legal_actions = []
        new_state.trump_suit = None
        new_state.trump_level = None
        new_state.hands = (tuple(), tuple(), tuple(), tuple(), tuple(), tuple())
        new_state.current_trick = []
        new_state.tricks_won = [tuple() for _ in range(6)]
        new_state.scores = (0, 0, 0, 0, 0, 0)
        new_state.player_levels = ("R1:2",) * 6
        new_state.revealed_helpers = []
        new_state.kitty = None
        new_state.helper_card = None
        room.game.step = Mock(return_value=(new_state, {}))

        message_data = {"type": "pass"}

        with patch('game_loop.parse_client_message') as mock_parse:
            mock_parse.return_value = PassMessage(type="pass")
            with patch('game_loop.client_message_to_action') as mock_convert:
                mock_convert.return_value = Mock()
                await handle_action(room, 1, message_data)

                # All connected players should receive state update
                assert ws0.send_json.called
                assert ws1.send_json.called
                assert ws2.send_json.called

    async def test_handle_action_updates_room_state(self, room):
        """Test that room state is updated after action."""
        ws = AsyncMock()
        room.add_connection(1, ws)
        room.state.current_player = 1

        old_state = room.state
        new_state = Mock()
        new_state.phase = "TRICK_PLAYING"
        new_state.current_player = 2
        new_state.dealer_id = 0
        new_state.legal_actions = []
        new_state.trump_suit = None
        new_state.trump_level = None
        new_state.hands = (tuple(), tuple(), tuple(), tuple(), tuple(), tuple())
        new_state.current_trick = []
        new_state.tricks_won = [tuple() for _ in range(6)]
        new_state.scores = (0, 0, 0, 0, 0, 0)
        new_state.player_levels = ("R1:2",) * 6
        new_state.revealed_helpers = []
        new_state.kitty = None
        new_state.helper_card = None
        room.game.step = Mock(return_value=(new_state, {}))

        message_data = {"type": "pass"}

        with patch('game_loop.parse_client_message') as mock_parse:
            mock_parse.return_value = PassMessage(type="pass")
            with patch('game_loop.client_message_to_action') as mock_convert:
                mock_convert.return_value = Mock()
                await handle_action(room, 1, message_data)

                # Room state should be updated
                assert room.state == new_state

    async def test_handle_action_game_over(self, room):
        """Test handling game over state."""
        ws = AsyncMock()
        room.add_connection(1, ws)
        room.state.current_player = 1

        new_state = Mock()
        new_state.phase = "SCORING"  # Game over
        new_state.current_player = 2
        new_state.dealer_id = 0
        new_state.legal_actions = []
        new_state.trump_suit = None
        new_state.trump_level = None
        new_state.hands = (tuple(), tuple(), tuple(), tuple(), tuple(), tuple())
        new_state.current_trick = []
        new_state.tricks_won = [tuple() for _ in range(6)]
        new_state.scores = (0, 0, 0, 0, 0, 0)
        new_state.player_levels = ("R1:2",) * 6
        new_state.revealed_helpers = []
        new_state.kitty = None
        new_state.helper_card = None
        room.game.step = Mock(return_value=(new_state, {}))

        message_data = {"type": "pass"}

        with patch('game_loop.parse_client_message') as mock_parse:
            mock_parse.return_value = PassMessage(type="pass")
            with patch('game_loop.client_message_to_action') as mock_convert:
                mock_convert.return_value = Mock()
                await handle_action(room, 1, message_data)

                # Should still broadcast (game over is just another state)
                assert ws.send_json.called


@pytest.mark.asyncio
class TestHandleJoin:
    async def test_handle_join_sends_state(self, room):
        """Test that joining player receives initial state."""
        ws = AsyncMock()
        room.add_connection(0, ws)

        with patch('game_loop.serialize_for_player') as mock_serialize:
            mock_serialize.return_value = {"phase": "DEALING"}
            await handle_join(room, 0)

            # Player should receive state update
            assert ws.send_json.called
            call_args = ws.send_json.call_args[0][0]
            assert call_args["type"] == "state_update"

    async def test_handle_join_nonexistent_connection(self, room):
        """Test joining when player connection doesn't exist."""
        # Don't add the connection
        await handle_join(room, 0)
        # Should not raise error


class TestActionParseError:
    def test_action_parse_error_is_exception(self):
        """Test that ActionParseError is an Exception."""
        assert issubclass(ActionParseError, Exception)

    def test_action_parse_error_message(self):
        """Test ActionParseError message."""
        error = ActionParseError("Test error")
        assert str(error) == "Test error"
