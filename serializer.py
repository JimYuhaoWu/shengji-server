"""Serialize game state with privacy controls for WebSocket clients."""

from typing import TYPE_CHECKING

from protocol import CardMessage, ActionMessage

if TYPE_CHECKING:
    from shengji_engine import GameState, Card, Action


def card_to_message(card: "Card") -> CardMessage:
    """Convert engine Card to protocol CardMessage.

    Args:
        card: Card from shengji-engine

    Returns:
        CardMessage for JSON serialization
    """
    return CardMessage(
        suit=str(card.suit),
        rank=str(card.rank),
        deck_id=card.deck_id,
    )


def action_to_message(action: "Action") -> ActionMessage:
    """Convert engine Action to protocol ActionMessage.

    Args:
        action: Action from shengji-engine

    Returns:
        ActionMessage for JSON serialization
    """
    return ActionMessage(
        action_type=str(action.action_type),
        cards=[card_to_message(c) for c in action.cards],
        target=action.target,
    )


def serialize_for_player(
    state: "GameState",
    viewing_player_id: int,
) -> dict:
    """Serialize game state for a specific player, filtering private information.

    Privacy rules:
    - Only the viewing player sees their own hand
    - Only the current player sees legal actions
    - No one sees other players' hands
    - Hand sizes are visible to all (for game state tracking)

    Args:
        state: GameState from shengji-engine
        viewing_player_id: The player ID viewing this state (0-5)

    Returns:
        Dictionary ready for JSON serialization to client
    """
    if not (0 <= viewing_player_id <= 5):
        raise ValueError(f"Invalid viewing_player_id: {viewing_player_id}")

    # Build player-specific hand (only for viewing player)
    your_hand = []
    if state.hands is not None:
        your_hand = [
            card_to_message(c)
            for c in state.hands[viewing_player_id]
        ]

    # Build hands_size for all players (visible to all)
    hands_size = []
    if state.hands is not None:
        hands_size = [len(h) for h in state.hands]

    # Legal actions only for current player
    legal_actions = []
    if state.current_player == viewing_player_id and state.legal_actions is not None:
        legal_actions = [
            action_to_message(a)
            for a in state.legal_actions
        ]

    # Current trick (cards played this round)
    current_trick = []
    if state.current_trick is not None:
        for player_id, cards in state.current_trick:
            current_trick.append([
                player_id,
                [card_to_message(c) for c in cards],
            ])

    # Tricks won by each player (visible to all)
    tricks_won = []
    if state.tricks_won is not None:
        tricks_won = [
            [card_to_message(c) for c in trick_cards]
            for trick_cards in state.tricks_won
        ]

    # Kitty visible only to dealer
    kitty = None
    if state.kitty is not None and state.dealer_id == viewing_player_id:
        kitty = [card_to_message(c) for c in state.kitty]

    # Helper card (the card dealer called for identifying helpers)
    helper_card = None
    if state.helper_card is not None:
        helper_card = card_to_message(state.helper_card)

    return {
        "phase": str(state.phase) if state.phase else None,
        "current_player": state.current_player,
        "dealer_id": state.dealer_id,
        "your_hand": [c.model_dump() for c in your_hand],
        "hands_size": hands_size,
        "legal_actions": [a.model_dump() for a in legal_actions],
        "trump_suit": str(state.trump_suit) if state.trump_suit else None,
        "trump_level": state.trump_level,
        "current_trick": [
            [player_id, [c.model_dump() for c in cards]]
            for player_id, cards in current_trick
        ],
        "tricks_won": [
            [c.model_dump() for c in trick]
            for trick in tricks_won
        ],
        "scores": list(state.scores) if state.scores else [],
        "player_levels": list(state.player_levels) if state.player_levels else [],
        "revealed_helpers": list(state.revealed_helpers) if state.revealed_helpers else [],
        "kitty": [c.model_dump() for c in kitty] if kitty else None,
        "helper_card": helper_card.model_dump() if helper_card else None,
    }


def serialize_for_all_players(
    state: "GameState",
) -> dict[int, dict]:
    """Serialize game state for all 6 players.

    Each player gets the state filtered for their perspective.

    Args:
        state: GameState from shengji-engine

    Returns:
        Dictionary mapping player_id -> serialized_state
    """
    return {
        player_id: serialize_for_player(state, player_id)
        for player_id in range(6)
    }
