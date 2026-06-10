"""Game loop for processing player actions and updating game state."""

import json
from typing import TYPE_CHECKING
from protocol import ClientMessageType, parse_client_message, ErrorMessage
from serializer import serialize_for_player
from room import Room

if TYPE_CHECKING:
    from shengji_engine import Action, GameState


class ActionParseError(Exception):
    """Raised when a client message cannot be converted to an engine Action."""
    pass


def client_message_to_action(message: ClientMessageType, player_id: int) -> "Action":
    """Convert a client message to a shengji-engine Action.

    This is the bridge between the protocol layer and the engine layer.

    Args:
        message: Parsed client message from protocol.py
        player_id: The player sending the action

    Returns:
        Action object for shengji-engine

    Raises:
        ActionParseError: If the message cannot be converted to an Action
    """
    from shengji_engine import Action, ActionType, Card, Suit, Rank

    action_type = None
    cards = []
    target = None

    if message.type == "play_cards":
        action_type = ActionType.PLAY_CARDS
        cards = [
            Card(
                suit=Suit[card.suit.upper()] if card.suit.upper() in Suit.__members__ else Suit.HEARTS,
                rank=Rank[card.rank.upper()] if card.rank.upper() in Rank.__members__ else Rank.TWO,
                deck_id=card.deck_id,
            )
            for card in message.cards
        ]

    elif message.type == "declare_trump":
        action_type = ActionType.DECLARE_TRUMP
        cards = [
            Card(
                suit=Suit[card.suit.upper()] if card.suit.upper() in Suit.__members__ else Suit.HEARTS,
                rank=Rank[card.rank.upper()] if card.rank.upper() in Rank.__members__ else Rank.TWO,
                deck_id=card.deck_id,
            )
            for card in message.level_cards
        ]

    elif message.type == "call_helper":
        action_type = ActionType.CALL_HELPER
        cards = [
            Card(
                suit=Suit[message.card.suit.upper()] if message.card.suit.upper() in Suit.__members__ else Suit.HEARTS,
                rank=Rank[message.card.rank.upper()] if message.card.rank.upper() in Rank.__members__ else Rank.TWO,
                deck_id=message.card.deck_id,
            )
        ]

    elif message.type == "take_kitty":
        action_type = ActionType.TAKE_KITTY
        cards = [
            Card(
                suit=Suit[card.suit.upper()] if card.suit.upper() in Suit.__members__ else Suit.HEARTS,
                rank=Rank[card.rank.upper()] if card.rank.upper() in Rank.__members__ else Rank.TWO,
                deck_id=card.deck_id,
            )
            for card in message.buried_cards
        ]

    elif message.type == "pass":
        action_type = ActionType.PASS

    else:
        raise ActionParseError(f"Unknown message type: {message.type}")

    if action_type is None:
        raise ActionParseError(f"Could not determine action type from message")

    return Action(action_type=action_type, cards=tuple(cards), target=target)


async def handle_action(
    room: Room,
    player_id: int,
    message_data: dict,
) -> None:
    """Process a player action, update game state, and broadcast.

    This function:
    1. Parses the client message
    2. Validates the player is the current player (or can pass)
    3. Converts the message to an engine Action
    4. Calls game.step(action)
    5. Broadcasts updated state to all players
    6. Handles errors by sending error message to the sender only

    Args:
        room: The Room instance
        player_id: The player sending the action
        message_data: Raw dict from JSON message
    """
    # Step 1: Parse message
    try:
        message = parse_client_message(message_data)
    except Exception as e:
        error = ErrorMessage(type="error", message=f"Invalid message: {str(e)}")
        await room.broadcast(error.model_dump(), exclude_player=None)
        return

    # Step 2: Validate turn ownership
    # Only certain message types require being the current player
    action_types = {"play_cards", "declare_trump", "call_helper", "take_kitty", "pass"}
    if message.type in action_types and room.state.current_player != player_id:
        error = ErrorMessage(type="error", message="Not your turn")
        if player_id in room.connections:
            try:
                await room.connections[player_id].send_json(error.model_dump())
            except:
                pass
        return

    # Step 3: Convert to engine Action
    try:
        action = client_message_to_action(message, player_id)
    except ActionParseError as e:
        error = ErrorMessage(type="error", message=f"Invalid action: {str(e)}")
        if player_id in room.connections:
            try:
                await room.connections[player_id].send_json(error.model_dump())
            except:
                pass
        return

    # Step 4: Call engine
    try:
        new_state, info = room.game.step(room.state, action)
        room.state = new_state
    except ValueError as e:
        # Illegal move
        error = ErrorMessage(type="error", message=f"Illegal move: {str(e)}")
        if player_id in room.connections:
            try:
                await room.connections[player_id].send_json(error.model_dump())
            except:
                pass
        return
    except Exception as e:
        # Unexpected error
        error = ErrorMessage(type="error", message=f"Game error: {str(e)}")
        if player_id in room.connections:
            try:
                await room.connections[player_id].send_json(error.model_dump())
            except:
                pass
        return

    # Step 5: Broadcast updated state to all players (with privacy filtering)
    for player_id in range(6):
        if player_id in room.connections:
            serialized = serialize_for_player(room.state, player_id)
            try:
                await room.connections[player_id].send_json({
                    "type": "state_update",
                    **serialized,
                })
            except:
                pass

    # Step 6: Check for game over
    if room.state.phase == "SCORING":
        # Game is over, record results
        # (This would be done by the room cleanup process)
        pass


async def handle_join(room: Room, player_id: int) -> None:
    """Handle a player joining the room.

    Args:
        room: The Room instance
        player_id: The player joining
    """
    # Broadcast state to the joining player
    if player_id in room.connections:
        serialized = serialize_for_player(room.state, player_id)
        try:
            await room.connections[player_id].send_json({
                "type": "state_update",
                **serialized,
            })
        except:
            pass

    # Notify other players
    connection_count = room.get_connected_count()
    if connection_count == 6:
        # All players connected, start the game
        # (Reset game state if needed and broadcast)
        pass
