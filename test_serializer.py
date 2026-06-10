"""Tests for serializer.py state filtering and privacy."""

import pytest
from unittest.mock import Mock
from protocol import CardMessage, ActionMessage
from serializer import (
    card_to_message,
    action_to_message,
    serialize_for_player,
    serialize_for_all_players,
)


@pytest.fixture
def mock_card():
    """Create a mock Card."""
    card = Mock()
    card.suit = "♥"
    card.rank = "7"
    card.deck_id = 0
    return card


@pytest.fixture
def mock_action(mock_card):
    """Create a mock Action."""
    action = Mock()
    action.action_type = "PLAY_CARDS"
    action.cards = [mock_card]
    action.target = None
    return action


@pytest.fixture
def mock_state():
    """Create a mock GameState."""
    state = Mock()
    state.phase = "TRICK_PLAYING"
    state.current_player = 1
    state.dealer_id = 0
    state.trump_suit = "♥"
    state.trump_level = "7"

    # Create mock hands: 6 players with different card counts
    mock_cards = [Mock(suit="♥", rank="K", deck_id=0) for _ in range(5)]
    state.hands = (
        tuple(mock_cards[:4]),  # Player 0: 4 cards
        tuple(mock_cards[:5]),  # Player 1: 5 cards
        tuple(),                 # Player 2: 0 cards
        tuple(mock_cards[:3]),  # Player 3: 3 cards
        tuple(mock_cards[:4]),  # Player 4: 4 cards
        tuple(mock_cards[:2]),  # Player 5: 2 cards
    )

    # Trick info
    state.current_trick = [(0, tuple([mock_cards[0]]))]
    state.tricks_won = [tuple(), tuple(), tuple(), tuple(), tuple(), tuple()]

    # Scoring
    state.scores = (0, 10, 0, 0, 0, 0)
    state.player_levels = ("R1:2", "R1:2", "R1:2", "R1:2", "R1:2", "R1:2")
    state.revealed_helpers = (1,)

    # Kitty and helper
    state.kitty = tuple(mock_cards[:3])
    state.helper_card = mock_cards[0]

    # Legal actions (mocked)
    mock_action = Mock()
    mock_action.action_type = "PLAY_CARDS"
    mock_action.cards = [mock_cards[0]]
    mock_action.target = None
    state.legal_actions = (mock_action,)

    return state


class TestCardToMessage:
    def test_card_to_message(self, mock_card):
        """Test converting a card to CardMessage."""
        msg = card_to_message(mock_card)
        assert isinstance(msg, CardMessage)
        assert msg.suit == "♥"
        assert msg.rank == "7"
        assert msg.deck_id == 0


class TestActionToMessage:
    def test_action_to_message(self, mock_action, mock_card):
        """Test converting an action to ActionMessage."""
        msg = action_to_message(mock_action)
        assert isinstance(msg, ActionMessage)
        assert msg.action_type == "PLAY_CARDS"
        assert len(msg.cards) == 1
        assert msg.target is None

    def test_action_to_message_with_target(self, mock_card):
        """Test action message with target."""
        action = Mock()
        action.action_type = "CALL_HELPER"
        action.cards = [mock_card]
        action.target = 2

        msg = action_to_message(action)
        assert msg.target == 2


class TestSerializeForPlayer:
    def test_serialize_viewing_player_sees_own_hand(self, mock_state):
        """Test that viewing player sees their own hand."""
        serialized = serialize_for_player(mock_state, viewing_player_id=1)
        assert len(serialized["your_hand"]) == 5  # Player 1 has 5 cards

    def test_serialize_viewing_player_does_not_see_others_hands(self, mock_state):
        """Test that viewing player doesn't see other players' hands."""
        serialized = serialize_for_player(mock_state, viewing_player_id=1)

        # Should have hands_size info
        assert serialized["hands_size"] == [4, 5, 0, 3, 4, 2]

        # But not other hands
        assert "hands" not in serialized

    def test_serialize_hand_sizes_visible_to_all(self, mock_state):
        """Test that all players see hand sizes."""
        for player_id in range(6):
            serialized = serialize_for_player(mock_state, viewing_player_id=player_id)
            assert serialized["hands_size"] == [4, 5, 0, 3, 4, 2]

    def test_serialize_current_player_sees_legal_actions(self, mock_state):
        """Test that only current player sees legal actions."""
        # Current player is 1
        serialized = serialize_for_player(mock_state, viewing_player_id=1)
        assert len(serialized["legal_actions"]) == 1

    def test_serialize_other_players_dont_see_legal_actions(self, mock_state):
        """Test that other players don't see legal actions."""
        # Current player is 1
        serialized = serialize_for_player(mock_state, viewing_player_id=0)
        assert len(serialized["legal_actions"]) == 0

    def test_serialize_kitty_visible_only_to_dealer(self, mock_state):
        """Test that kitty is visible only to dealer."""
        # Dealer is player 0
        serialized = serialize_for_player(mock_state, viewing_player_id=0)
        assert serialized["kitty"] is not None

        # Other players don't see it
        serialized = serialize_for_player(mock_state, viewing_player_id=1)
        assert serialized["kitty"] is None

    def test_serialize_includes_game_metadata(self, mock_state):
        """Test that serialized state includes game metadata."""
        serialized = serialize_for_player(mock_state, viewing_player_id=0)

        assert serialized["phase"] == "TRICK_PLAYING"
        assert serialized["current_player"] == 1
        assert serialized["dealer_id"] == 0
        assert serialized["trump_suit"] == "♥"
        assert serialized["trump_level"] == "7"

    def test_serialize_includes_scores_and_helpers(self, mock_state):
        """Test that serialized state includes scores and revealed helpers."""
        serialized = serialize_for_player(mock_state, viewing_player_id=0)

        assert serialized["scores"] == [0, 10, 0, 0, 0, 0]
        assert serialized["revealed_helpers"] == [1]

    def test_serialize_invalid_player_id_negative(self, mock_state):
        """Test that negative player_id raises error."""
        with pytest.raises(ValueError, match="Invalid viewing_player_id"):
            serialize_for_player(mock_state, viewing_player_id=-1)

    def test_serialize_invalid_player_id_too_high(self, mock_state):
        """Test that player_id > 5 raises error."""
        with pytest.raises(ValueError, match="Invalid viewing_player_id"):
            serialize_for_player(mock_state, viewing_player_id=6)

    def test_serialize_current_trick(self, mock_state):
        """Test that current trick is included."""
        serialized = serialize_for_player(mock_state, viewing_player_id=0)

        # Current trick format: [[player_id, [cards]]]
        assert len(serialized["current_trick"]) == 1
        assert serialized["current_trick"][0][0] == 0

    def test_serialize_tricks_won(self, mock_state):
        """Test that tricks won are included."""
        serialized = serialize_for_player(mock_state, viewing_player_id=0)

        # Should have 6 entries (one per player)
        assert len(serialized["tricks_won"]) == 6

    def test_serialize_helper_card(self, mock_state):
        """Test that helper card is included."""
        serialized = serialize_for_player(mock_state, viewing_player_id=0)

        assert serialized["helper_card"] is not None
        assert isinstance(serialized["helper_card"], dict)
        assert serialized["helper_card"]["suit"] == "♥"

    def test_serialize_with_no_kitty(self, mock_state):
        """Test serialization when there's no kitty."""
        mock_state.kitty = None
        serialized = serialize_for_player(mock_state, viewing_player_id=0)
        assert serialized["kitty"] is None

    def test_serialize_with_no_legal_actions(self, mock_state):
        """Test serialization when there are no legal actions."""
        mock_state.legal_actions = None
        serialized = serialize_for_player(mock_state, viewing_player_id=1)
        assert serialized["legal_actions"] == []

    def test_serialize_with_empty_hands(self, mock_state):
        """Test serialization when hands are empty."""
        mock_state.hands = (tuple(), tuple(), tuple(), tuple(), tuple(), tuple())
        serialized = serialize_for_player(mock_state, viewing_player_id=0)
        assert len(serialized["your_hand"]) == 0


class TestSerializeForAllPlayers:
    def test_serialize_for_all_players(self, mock_state):
        """Test serializing state for all players."""
        all_serialized = serialize_for_all_players(mock_state)

        # Should have 6 entries, one per player
        assert len(all_serialized) == 6
        assert all(player_id in all_serialized for player_id in range(6))

    def test_serialize_for_all_players_hand_visibility(self, mock_state):
        """Test that each player only sees their own hand."""
        all_serialized = serialize_for_all_players(mock_state)

        # Player 0 should see 4 cards
        assert len(all_serialized[0]["your_hand"]) == 4

        # Player 1 should see 5 cards
        assert len(all_serialized[1]["your_hand"]) == 5

        # Player 2 should see 0 cards
        assert len(all_serialized[2]["your_hand"]) == 0

    def test_serialize_for_all_players_legal_actions(self, mock_state):
        """Test that only current player sees legal actions."""
        all_serialized = serialize_for_all_players(mock_state)

        # Current player is 1
        assert len(all_serialized[1]["legal_actions"]) == 1

        # Other players see no actions
        for player_id in range(6):
            if player_id != 1:
                assert len(all_serialized[player_id]["legal_actions"]) == 0

    def test_serialize_for_all_players_kitty_visibility(self, mock_state):
        """Test that only dealer sees kitty."""
        all_serialized = serialize_for_all_players(mock_state)

        # Dealer is player 0
        assert all_serialized[0]["kitty"] is not None

        # Other players don't see it
        for player_id in range(1, 6):
            assert all_serialized[player_id]["kitty"] is None

    def test_serialize_for_all_players_symmetric(self, mock_state):
        """Test that all players see the same game state info."""
        all_serialized = serialize_for_all_players(mock_state)

        # All should see the same phase, current_player, etc.
        for player_id in range(6):
            assert all_serialized[player_id]["phase"] == "TRICK_PLAYING"
            assert all_serialized[player_id]["current_player"] == 1
            assert all_serialized[player_id]["dealer_id"] == 0
            assert all_serialized[player_id]["hands_size"] == [4, 5, 0, 3, 4, 2]
