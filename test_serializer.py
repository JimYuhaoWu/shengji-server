"""Tests for serializer.py — privacy filtering against real GameState."""

import pytest

from shengji import GamePhase

from conftest import advance_to_phase
from serializer import serialize_for_player, MAX_LEGAL_ACTIONS


class TestBasicShape:
    def test_has_core_fields(self, fresh_state):
        _, state = fresh_state
        view = serialize_for_player(state, 0)
        for key in (
            "phase", "current_player", "dealer_id", "your_hand", "hands_size",
            "trump_level", "scores", "player_levels",
        ):
            assert key in view

    def test_phase_is_name_string(self, fresh_state):
        _, state = fresh_state
        assert serialize_for_player(state, 0)["phase"] == "DEALING"

    def test_invalid_player_id(self, fresh_state):
        _, state = fresh_state
        with pytest.raises(ValueError):
            serialize_for_player(state, 6)
        with pytest.raises(ValueError):
            serialize_for_player(state, -1)


class TestHandPrivacy:
    def test_player_sees_only_own_hand(self, fresh_state):
        game, state = fresh_state
        # Deal a few rounds so hands are non-empty.
        state = advance_to_phase(game, state, GamePhase.TRUMP_DECLARATION)
        view0 = serialize_for_player(state, 0)
        view1 = serialize_for_player(state, 1)
        # your_hand matches that player's actual hand length.
        assert len(view0["your_hand"]) == len(state.hands[0])
        assert len(view1["your_hand"]) == len(state.hands[1])

    def test_hand_sizes_visible_to_all(self, fresh_state):
        game, state = fresh_state
        state = advance_to_phase(game, state, GamePhase.TRUMP_DECLARATION)
        expected = [len(h) for h in state.hands]
        for pid in range(6):
            assert serialize_for_player(state, pid)["hands_size"] == expected

    def test_no_raw_hands_field_leaked(self, fresh_state):
        _, state = fresh_state
        assert "hands" not in serialize_for_player(state, 0)


class TestLegalActionsPrivacy:
    def test_only_current_player_gets_actions(self, fresh_state):
        _, state = fresh_state
        current = state.current_player
        other = (current + 1) % 6
        assert serialize_for_player(state, current)["legal_actions"] is not None
        assert serialize_for_player(state, other)["legal_actions"] is None

    def test_kitty_actions_truncated(self, fresh_state):
        game, state = fresh_state
        state = advance_to_phase(game, state, GamePhase.KITTY)
        # KITTY has ~906k actions; must be omitted, not serialized.
        assert len(state.legal_actions) > MAX_LEGAL_ACTIONS
        view = serialize_for_player(state, state.current_player)
        assert view["legal_actions"] is None
        assert view["legal_actions_truncated"] is True


class TestKittyPrivacy:
    def test_kitty_visible_only_to_dealer(self, fresh_state):
        game, state = fresh_state
        state = advance_to_phase(game, state, GamePhase.KITTY)
        dealer = state.dealer_id
        # The dealer's hand absorbed the kitty in this engine; the standalone
        # kitty field is dealer-only when present.
        for pid in range(6):
            view = serialize_for_player(state, pid)
            if pid != dealer:
                assert view["kitty"] is None


class TestPublicInfo:
    def test_called_card_public_after_call(self, fresh_state):
        game, state = fresh_state
        state = advance_to_phase(game, state, GamePhase.TRICK_PLAYING)
        # By TRICK_PLAYING the helper card has been called; it's public to all.
        for pid in range(6):
            view = serialize_for_player(state, pid)
            assert view["called_rank"] is not None
            assert view["called_suit"] is not None

    def test_trump_suit_serialized_as_value(self, fresh_state):
        game, state = fresh_state
        state = advance_to_phase(game, state, GamePhase.TRICK_PLAYING)
        view = serialize_for_player(state, 0)
        # trump_suit is a single-char suit value or None.
        assert view["trump_suit"] in {"H", "D", "C", "S", None}
