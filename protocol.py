"""WebSocket protocol message definitions using Pydantic for validation."""

from typing import Literal
from pydantic import BaseModel, Field


class CardMessage(BaseModel):
    """Card representation in protocol messages."""
    suit: str
    rank: str
    deck_id: int


class ActionMessage(BaseModel):
    """Action representation for legal actions."""
    action_type: str
    cards: list[CardMessage] = Field(default_factory=list)
    target: int | None = None


# ============ CLIENT → SERVER ============


class ClientMessage(BaseModel):
    """Base class for all client messages."""
    type: str


class JoinMessage(ClientMessage):
    """Client joins a game room."""
    type: Literal["join"]
    player_id: int


class PlayCardsMessage(ClientMessage):
    """Client plays cards during trick."""
    type: Literal["play_cards"]
    cards: list[CardMessage]


class DeclareTrumpMessage(ClientMessage):
    """Client declares trump during bidding."""
    type: Literal["declare_trump"]
    level_cards: list[CardMessage]


class CallHelperMessage(ClientMessage):
    """Dealer calls a helper card."""
    type: Literal["call_helper"]
    card: CardMessage


class PassMessage(ClientMessage):
    """Client passes during trump declaration."""
    type: Literal["pass"]


class TakeKittyMessage(ClientMessage):
    """Dealer takes the kitty."""
    type: Literal["take_kitty"]
    buried_cards: list[CardMessage]


# Union type for all client messages
ClientMessageType = JoinMessage | PlayCardsMessage | DeclareTrumpMessage | CallHelperMessage | PassMessage | TakeKittyMessage


# ============ SERVER → CLIENT ============


class ServerMessage(BaseModel):
    """Base class for all server messages."""
    type: str


class StateUpdateMessage(ServerMessage):
    """Complete game state sent to client."""
    type: Literal["state_update"]
    phase: str
    current_player: int
    dealer_id: int
    your_hand: list[CardMessage]
    hands_size: list[int]
    legal_actions: list[ActionMessage]
    trump_suit: str | None
    trump_level: str | None
    current_trick: list[tuple[int, list[CardMessage]]]  # [(player_id, cards), ...]
    tricks_won: list[list[CardMessage]]  # Per player
    scores: list[int]  # Per player
    revealed_helpers: list[int]
    kitty: list[CardMessage] | None = None  # Only visible to dealer


class ErrorMessage(ServerMessage):
    """Error from server."""
    type: Literal["error"]
    message: str


class GameOverMessage(ServerMessage):
    """Game has ended."""
    type: Literal["game_over"]
    winner_side: str  # "farmer" or "dealer"
    scores: dict[str, int]  # Round scores
    level_changes: dict[int, int]  # player_id -> level_delta


class JoinedMessage(ServerMessage):
    """Confirmation that player joined."""
    type: Literal["joined"]
    player_id: int
    room_id: str


class PlayerConnectedMessage(ServerMessage):
    """Another player connected."""
    type: Literal["player_connected"]
    player_id: int
    connected_count: int


class PlayerDisconnectedMessage(ServerMessage):
    """Another player disconnected."""
    type: Literal["player_disconnected"]
    player_id: int
    connected_count: int


# Union type for all server messages
ServerMessageType = (
    StateUpdateMessage
    | ErrorMessage
    | GameOverMessage
    | JoinedMessage
    | PlayerConnectedMessage
    | PlayerDisconnectedMessage
)


def parse_client_message(data: dict) -> ClientMessageType:
    """Parse JSON data into the appropriate client message type.

    Raises ValueError if message type is unknown or validation fails.
    """
    msg_type = data.get("type")

    message_map = {
        "join": JoinMessage,
        "play_cards": PlayCardsMessage,
        "declare_trump": DeclareTrumpMessage,
        "call_helper": CallHelperMessage,
        "pass": PassMessage,
        "take_kitty": TakeKittyMessage,
    }

    if msg_type not in message_map:
        raise ValueError(f"Unknown message type: {msg_type}")

    return message_map[msg_type](**data)
