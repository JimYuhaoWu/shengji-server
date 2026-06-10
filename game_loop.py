"""Process player actions through the engine and broadcast the results.

Flow for every inbound action message (CLAUDE.md "validate through engine"):
  parse -> confirm it's the sender's turn -> resolve to an engine Action ->
  validate it is legal -> game.step() -> broadcast new state (-> game_over).

Errors go only to the offending sender; successful state updates go to everyone.
"""

from collections import Counter

from shengji import GamePhase

from protocol import ACTION_MESSAGE_TYPES, message_to_action
from room import Room


async def _error(room: Room, player_id: int, message: str) -> None:
    await room.send_to(player_id, {"type": "error", "message": message})


def _bury_is_valid(room: Room, cards) -> bool:
    """Check a TAKE_KITTY bury is exactly 6 cards drawn from the dealer's hand."""
    if len(cards) != 6:
        return False
    hand = Counter((c.suit, c.rank) for c in room.state.hands[room.state.dealer_id])
    want = Counter((c.suit, c.rank) for c in cards)
    return all(hand[k] >= v for k, v in want.items())


def _resolve_action(room: Room, player_id: int, message: dict):
    """Turn a client message into a validated engine Action.

    Returns the Action, or raises ValueError with a client-facing reason.
    """
    state = room.state

    # Convenience path: select a pre-computed legal action by index.
    if message.get("type") == "action":
        index = message.get("index")
        if not isinstance(index, int) or not (0 <= index < len(state.legal_actions)):
            raise ValueError("Invalid action index")
        return state.legal_actions[index]

    # Semantic path: reconstruct, then validate legality.
    action = message_to_action(message, player_id)

    # KITTY's legal-action list is enormous; validate the bury directly.
    if state.phase == GamePhase.KITTY:
        if not _bury_is_valid(room, action.cards):
            raise ValueError("Bury must be 6 cards from your hand")
        return action

    if action not in state.legal_actions:
        raise ValueError("Illegal move")
    return action


async def handle_action(room: Room, player_id: int, message: dict) -> None:
    """Validate and apply one action message from a player."""
    # Only the current player may act.
    if room.state.current_player != player_id:
        await _error(room, player_id, "Not your turn")
        return

    try:
        action = _resolve_action(room, player_id, message)
    except ValueError as e:
        await _error(room, player_id, str(e))
        return

    try:
        room.state, info = room.game.step(room.state, action)
    except Exception as e:  # engine should not raise, but never crash the room
        await _error(room, player_id, f"Engine error: {e}")
        return

    await room.broadcast_state()

    if room.state.phase == GamePhase.SCORING:
        await room.broadcast({
            "type": "game_over",
            "farmer_score": info.get("farmer_score"),
            "next_dealer": info.get("next_dealer"),
            "player_levels": list(room.state.player_levels),
        })


async def handle_join(room: Room, player_id: int) -> None:
    """Send the joining player their current view of the game."""
    from serializer import serialize_for_player

    payload = serialize_for_player(room.state, player_id)
    await room.send_to(player_id, {"type": "state_update", **payload})


def is_action_message(message: dict) -> bool:
    """Whether a parsed message is a player action (vs. join/other)."""
    return message.get("type") in ACTION_MESSAGE_TYPES
