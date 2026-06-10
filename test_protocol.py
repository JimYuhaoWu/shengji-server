"""Tests for protocol message definitions."""

import pytest
from pydantic import ValidationError

from protocol import (
    CardMessage,
    ActionMessage,
    JoinMessage,
    PlayCardsMessage,
    DeclareTrumpMessage,
    CallHelperMessage,
    PassMessage,
    TakeKittyMessage,
    StateUpdateMessage,
    ErrorMessage,
    GameOverMessage,
    parse_client_message,
)


class TestCardMessage:
    def test_valid_card(self):
        card = CardMessage(suit="♥", rank="7", deck_id=0)
        assert card.suit == "♥"
        assert card.rank == "7"
        assert card.deck_id == 0

    def test_card_missing_field(self):
        with pytest.raises(ValidationError):
            CardMessage(suit="♥", rank="7")  # Missing deck_id

    def test_card_invalid_type(self):
        with pytest.raises(ValidationError):
            CardMessage(suit="♥", rank="7", deck_id="invalid")


class TestActionMessage:
    def test_valid_action(self):
        action = ActionMessage(
            action_type="PLAY_CARDS",
            cards=[CardMessage(suit="♥", rank="7", deck_id=0)],
        )
        assert action.action_type == "PLAY_CARDS"
        assert len(action.cards) == 1
        assert action.target is None

    def test_action_with_target(self):
        action = ActionMessage(
            action_type="CALL_HELPER",
            cards=[CardMessage(suit="♦", rank="K", deck_id=1)],
            target=2,
        )
        assert action.target == 2

    def test_action_empty_cards(self):
        action = ActionMessage(action_type="PASS")
        assert action.cards == []


class TestClientMessages:
    def test_join_message(self):
        msg = JoinMessage(type="join", player_id=3)
        assert msg.type == "join"
        assert msg.player_id == 3

    def test_play_cards_message(self):
        msg = PlayCardsMessage(
            type="play_cards",
            cards=[
                CardMessage(suit="♥", rank="7", deck_id=0),
                CardMessage(suit="♥", rank="8", deck_id=0),
            ],
        )
        assert msg.type == "play_cards"
        assert len(msg.cards) == 2

    def test_declare_trump_message(self):
        msg = DeclareTrumpMessage(
            type="declare_trump",
            level_cards=[CardMessage(suit="♥", rank="7", deck_id=0)],
        )
        assert msg.type == "declare_trump"
        assert len(msg.level_cards) == 1

    def test_call_helper_message(self):
        msg = CallHelperMessage(
            type="call_helper",
            card=CardMessage(suit="♦", rank="K", deck_id=0),
        )
        assert msg.type == "call_helper"
        assert msg.card.rank == "K"

    def test_pass_message(self):
        msg = PassMessage(type="pass")
        assert msg.type == "pass"

    def test_take_kitty_message(self):
        msg = TakeKittyMessage(
            type="take_kitty",
            buried_cards=[CardMessage(suit="♣", rank="2", deck_id=0)],
        )
        assert msg.type == "take_kitty"
        assert len(msg.buried_cards) == 1


class TestServerMessages:
    def test_state_update_message(self):
        msg = StateUpdateMessage(
            type="state_update",
            phase="TRICK_PLAYING",
            current_player=2,
            dealer_id=0,
            your_hand=[CardMessage(suit="♥", rank="7", deck_id=0)],
            hands_size=[5, 6, 4, 7, 5, 6],
            legal_actions=[
                ActionMessage(
                    action_type="PLAY_CARDS",
                    cards=[CardMessage(suit="♥", rank="7", deck_id=0)],
                )
            ],
            trump_suit="♥",
            trump_level="7",
            current_trick=[(0, [CardMessage(suit="♠", rank="A", deck_id=0)])],
            tricks_won=[[], [], [], [], [], []],
            scores=[0, 0, 0, 0, 0, 0],
            revealed_helpers=[],
        )
        assert msg.type == "state_update"
        assert msg.phase == "TRICK_PLAYING"
        assert msg.current_player == 2

    def test_error_message(self):
        msg = ErrorMessage(type="error", message="Not your turn")
        assert msg.type == "error"
        assert msg.message == "Not your turn"

    def test_game_over_message(self):
        msg = GameOverMessage(
            type="game_over",
            winner_side="farmer",
            scores={"farmer": 180, "dealer": 20},
            level_changes={0: 2, 1: 0, 2: 2, 3: -1, 4: 2, 5: -1},
        )
        assert msg.type == "game_over"
        assert msg.winner_side == "farmer"


class TestParseClientMessage:
    def test_parse_join_message(self):
        data = {"type": "join", "player_id": 0}
        msg = parse_client_message(data)
        assert isinstance(msg, JoinMessage)
        assert msg.player_id == 0

    def test_parse_play_cards_message(self):
        data = {
            "type": "play_cards",
            "cards": [{"suit": "♥", "rank": "7", "deck_id": 0}],
        }
        msg = parse_client_message(data)
        assert isinstance(msg, PlayCardsMessage)
        assert len(msg.cards) == 1

    def test_parse_declare_trump_message(self):
        data = {
            "type": "declare_trump",
            "level_cards": [{"suit": "♥", "rank": "7", "deck_id": 0}],
        }
        msg = parse_client_message(data)
        assert isinstance(msg, DeclareTrumpMessage)

    def test_parse_call_helper_message(self):
        data = {
            "type": "call_helper",
            "card": {"suit": "♦", "rank": "K", "deck_id": 0},
        }
        msg = parse_client_message(data)
        assert isinstance(msg, CallHelperMessage)

    def test_parse_pass_message(self):
        data = {"type": "pass"}
        msg = parse_client_message(data)
        assert isinstance(msg, PassMessage)

    def test_parse_take_kitty_message(self):
        data = {
            "type": "take_kitty",
            "buried_cards": [{"suit": "♣", "rank": "2", "deck_id": 0}],
        }
        msg = parse_client_message(data)
        assert isinstance(msg, TakeKittyMessage)

    def test_parse_unknown_message_type(self):
        data = {"type": "unknown"}
        with pytest.raises(ValueError, match="Unknown message type"):
            parse_client_message(data)

    def test_parse_invalid_message_missing_field(self):
        data = {"type": "join"}  # Missing player_id
        with pytest.raises(ValidationError):
            parse_client_message(data)

    def test_parse_message_no_type(self):
        data = {"player_id": 0}
        with pytest.raises(ValueError, match="Unknown message type"):
            parse_client_message(data)
