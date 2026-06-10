"""Serialize the engine's GameState for a specific player, enforcing privacy.

Privacy rules (see CLAUDE.md):
- A player sees only their own hand; everyone else sees just hand sizes.
- Only the current player receives the list of legal actions.
- The kitty is visible only to the dealer, and only while it exists.
- Buried cards stay hidden until SCORING.
- The called helper card is public (the dealer announces it); the identities of
  revealed helpers come straight from the engine's helper_players, which is only
  populated once a player has played the called card.
"""

from shengji import GameState
from protocol import card_to_dict, action_to_dict

# Cap on how many legal actions we serialize. The KITTY phase has C(32,6) ≈ 906k
# bury actions — far too many to send. When exceeded we omit the list and the
# client drives that phase with a semantic message (e.g. take_kitty) instead.
MAX_LEGAL_ACTIONS = 500


def _trump_bid_to_dict(bid) -> dict | None:
    if bid is None:
        return None
    return {"count": bid.count, "suit": bid.suit.value, "bidder_id": bid.bidder_id}


def serialize_for_player(state: GameState, viewing_player_id: int) -> dict:
    """Build the state_update payload for one player's perspective.

    Args:
        state: the engine GameState
        viewing_player_id: 0-5, the player this payload is for

    Returns:
        A JSON-serializable dict (without the "type" envelope field).
    """
    if not (0 <= viewing_player_id <= 5):
        raise ValueError(f"Invalid viewing_player_id: {viewing_player_id}")

    is_current = state.current_player == viewing_player_id
    is_dealer = state.dealer_id == viewing_player_id

    # Own hand only; sizes for everyone.
    your_hand = [card_to_dict(c) for c in state.hands[viewing_player_id]]
    hands_size = [len(h) for h in state.hands]

    # Legal actions: current player only, and only when the list is sendable.
    legal_actions = None
    legal_actions_truncated = False
    if is_current:
        if len(state.legal_actions) <= MAX_LEGAL_ACTIONS:
            legal_actions = [
                action_to_dict(a, i) for i, a in enumerate(state.legal_actions)
            ]
        else:
            legal_actions_truncated = True

    # Current trick: [[player_id, [cards]], ...]
    current_trick = [
        [pid, [card_to_dict(c) for c in cards]] for pid, cards in state.current_trick
    ]

    # Tricks won: [[winner_id, [cards]], ...] — public record of completed tricks.
    tricks_won = [
        [winner_id, [card_to_dict(c) for c in cards]]
        for winner_id, cards in state.tricks_won
    ]

    # Kitty: dealer-only, while it exists (KITTY phase before burying).
    kitty = None
    if is_dealer and state.kitty:
        kitty = [card_to_dict(c) for c in state.kitty]

    # Buried cards: revealed to all only at SCORING.
    buried_cards = None
    if state.phase.name == "SCORING" and state.buried_cards:
        buried_cards = [card_to_dict(c) for c in state.buried_cards]

    return {
        "phase": state.phase.name,
        "current_player": state.current_player,
        "dealer_id": state.dealer_id,
        "your_player_id": viewing_player_id,
        "your_hand": your_hand,
        "hands_size": hands_size,
        "legal_actions": legal_actions,
        "legal_actions_truncated": legal_actions_truncated,
        "trump_suit": state.trump_suit.value if state.trump_suit else None,
        "trump_level": state.trump_level,
        "trump_locked": state.trump_locked,
        "current_trump_bid": _trump_bid_to_dict(state.current_trump_bid),
        "cards_dealt": state.cards_dealt,
        "current_trick": current_trick,
        "tricks_won": tricks_won,
        "scores": list(state.scores),
        "player_levels": list(state.player_levels),
        "called_rank": state.called_rank,
        "called_suit": state.called_suit.value if state.called_suit else None,
        "helper_players": list(state.helper_players),
        "kitty": kitty,
        "buried_cards": buried_cards,
    }
