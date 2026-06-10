"""Tests for protocol.py — card/action translation against the real engine."""

import pytest

from shengji import Action, ActionType, Suit, Rank, TrumpBid
from shengji.card import Card

import protocol


class TestCardRoundTrip:
    def test_card_to_dict(self):
        card = Card(Suit.HEARTS, Rank.SEVEN, 1)
        assert protocol.card_to_dict(card) == {"suit": "H", "rank": "7", "deck_id": 1}

    def test_card_from_dict(self):
        card = protocol.card_from_dict({"suit": "S", "rank": "A", "deck_id": 2})
        assert card == Card(Suit.SPADES, Rank.ACE, 2)
        assert card.deck_id == 2

    def test_ten_uses_T(self):
        # Rank.TEN serializes as "T".
        d = protocol.card_to_dict(Card(Suit.CLUBS, Rank.TEN, 0))
        assert d["rank"] == "T"
        assert protocol.card_from_dict(d).rank == Rank.TEN

    def test_jokers(self):
        big = Card(Suit.JOKER, Rank.LARGE_JOKER, 0)
        assert protocol.card_from_dict(protocol.card_to_dict(big)) == big

    def test_deck_id_defaults_to_zero(self):
        assert protocol.card_from_dict({"suit": "H", "rank": "K"}).deck_id == 0

    def test_invalid_card_raises(self):
        with pytest.raises(ValueError):
            protocol.card_from_dict({"suit": "X", "rank": "7"})

    def test_cards_from_list_requires_list(self):
        with pytest.raises(ValueError):
            protocol.cards_from_list({"not": "a list"})


class TestActionToDict:
    def test_play_cards_action(self):
        action = Action(
            action_type=ActionType.PLAY_CARDS,
            cards=(Card(Suit.HEARTS, Rank.SEVEN, 0),),
        )
        d = protocol.action_to_dict(action, index=3)
        assert d["index"] == 3
        assert d["action_type"] == "PLAY_CARDS"
        assert d["cards"] == [{"suit": "H", "rank": "7", "deck_id": 0}]
        assert d["trump_bid"] is None

    def test_bid_action_serializes_trump_bid(self):
        action = Action(
            action_type=ActionType.BID_TRUMP,
            trump_bid=TrumpBid(count=2, suit=Suit.HEARTS, bidder_id=4),
        )
        d = protocol.action_to_dict(action, index=0)
        assert d["trump_bid"] == {"count": 2, "suit": "H", "bidder_id": 4}

    def test_call_helper_action(self):
        action = Action(
            action_type=ActionType.CALL_HELPER,
            cards=(Card(Suit.DIAMONDS, Rank.KING, 0),),
        )
        d = protocol.action_to_dict(action, index=1)
        assert d["action_type"] == "CALL_HELPER"
        assert d["cards"][0]["rank"] == "K"


class TestMessageToAction:
    def test_pass_trump(self):
        a = protocol.message_to_action({"type": "pass_trump"}, player_id=0)
        assert a == Action(action_type=ActionType.PASS_TRUMP)

    def test_bid_trump_fills_bidder_id(self):
        a = protocol.message_to_action(
            {"type": "bid_trump", "count": 1, "suit": "H"}, player_id=2
        )
        assert a.action_type == ActionType.BID_TRUMP
        assert a.trump_bid == TrumpBid(count=1, suit=Suit.HEARTS, bidder_id=2)

    def test_bid_trump_missing_fields(self):
        with pytest.raises(ValueError):
            protocol.message_to_action({"type": "bid_trump", "count": 1}, player_id=0)

    def test_play_cards(self):
        a = protocol.message_to_action(
            {"type": "play_cards", "cards": [{"suit": "H", "rank": "7", "deck_id": 0}]},
            player_id=0,
        )
        assert a.action_type == ActionType.PLAY_CARDS
        assert a.cards == (Card(Suit.HEARTS, Rank.SEVEN, 0),)

    def test_call_helper(self):
        a = protocol.message_to_action(
            {"type": "call_helper", "suit": "D", "rank": "K"}, player_id=0
        )
        assert a.action_type == ActionType.CALL_HELPER
        assert a.cards[0] == Card(Suit.DIAMONDS, Rank.KING, 0)

    def test_take_kitty(self):
        cards = [{"suit": "H", "rank": str(r), "deck_id": 0} for r in (2, 3, 4, 5, 6, 7)]
        a = protocol.message_to_action({"type": "take_kitty", "cards": cards}, player_id=0)
        assert a.action_type == ActionType.TAKE_KITTY
        assert len(a.cards) == 6

    def test_unknown_type(self):
        with pytest.raises(ValueError):
            protocol.message_to_action({"type": "nonsense"}, player_id=0)
