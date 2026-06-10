"""WebSocket protocol: (de)serialize cards/actions and parse client messages.

This module is the boundary between JSON-over-WebSocket and the `shengji`
engine's typed objects. It contains NO game logic — only translation.
"""

from shengji import Action, ActionType, Suit, Rank, TrumpBid
from shengji.card import Card

# Reverse lookups from the single-character wire values back to engine enums.
SUIT_BY_VALUE = {s.value: s for s in Suit}
RANK_BY_VALUE = {r.value: r for r in Rank}

# Client message types that carry a player action (require it to be your turn).
ACTION_MESSAGE_TYPES = {
    "action",        # pick a pre-computed legal action by index
    "bid_trump",
    "pass_trump",
    "take_kitty",
    "call_helper",
    "play_cards",
}


# ============ CARDS ============


def card_to_dict(card: Card) -> dict:
    """Serialize an engine Card to a JSON-friendly dict."""
    return {"suit": card.suit.value, "rank": card.rank.value, "deck_id": card.deck_id}


def card_from_dict(data: dict) -> Card:
    """Reconstruct an engine Card from a client dict.

    Raises:
        ValueError: if suit/rank are missing or unrecognized.
    """
    try:
        suit = SUIT_BY_VALUE[data["suit"]]
        rank = RANK_BY_VALUE[data["rank"]]
    except (KeyError, TypeError) as e:
        raise ValueError(f"Invalid card: {data!r}") from e
    return Card(suit, rank, int(data.get("deck_id", 0)))


def cards_from_list(items) -> tuple[Card, ...]:
    """Reconstruct a tuple of Cards from a list of dicts."""
    if not isinstance(items, list):
        raise ValueError("Expected a list of cards")
    return tuple(card_from_dict(c) for c in items)


# ============ ACTIONS (engine -> wire) ============


def trump_bid_to_dict(bid: TrumpBid | None) -> dict | None:
    """Serialize a TrumpBid to a dict (or None)."""
    if bid is None:
        return None
    return {"count": bid.count, "suit": bid.suit.value, "bidder_id": bid.bidder_id}


def action_to_dict(action: Action, index: int) -> dict:
    """Serialize an engine Action for transmission to the current player.

    The `index` is the position in the player's legal_actions list, so a client
    may echo it back via an {"type": "action", "index": i} message.
    """
    return {
        "index": index,
        "action_type": action.action_type.name,
        "cards": [card_to_dict(c) for c in action.cards],
        "trump_bid": trump_bid_to_dict(action.trump_bid),
        "target_suit": action.target_suit.value if action.target_suit else None,
        "target_card": card_to_dict(action.target_card) if action.target_card else None,
    }


# ============ ACTIONS (wire -> engine) ============


def message_to_action(message: dict, player_id: int) -> Action:
    """Reconstruct an engine Action from a semantic client message.

    Does NOT cover the "action"/index path (that selects a pre-computed action
    directly from state.legal_actions in the game loop).

    Args:
        message: parsed JSON dict with a "type" field
        player_id: the player sending the action (used as the bid's bidder_id)

    Returns:
        An engine Action ready to validate against legal_actions.

    Raises:
        ValueError: if the message is malformed or of an unknown action type.
    """
    msg_type = message.get("type")

    if msg_type == "pass_trump":
        return Action(action_type=ActionType.PASS_TRUMP)

    if msg_type == "bid_trump":
        try:
            count = int(message["count"])
            suit = SUIT_BY_VALUE[message["suit"]]
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError("bid_trump requires 'count' and 'suit'") from e
        return Action(
            action_type=ActionType.BID_TRUMP,
            trump_bid=TrumpBid(count=count, suit=suit, bidder_id=player_id),
        )

    if msg_type == "take_kitty":
        cards = cards_from_list(message.get("cards", []))
        return Action(action_type=ActionType.TAKE_KITTY, cards=cards)

    if msg_type == "call_helper":
        try:
            suit = SUIT_BY_VALUE[message["suit"]]
            rank = RANK_BY_VALUE[message["rank"]]
        except (KeyError, TypeError) as e:
            raise ValueError("call_helper requires 'suit' and 'rank'") from e
        return Action(action_type=ActionType.CALL_HELPER, cards=(Card(suit, rank, 0),))

    if msg_type == "play_cards":
        cards = cards_from_list(message.get("cards", []))
        return Action(action_type=ActionType.PLAY_CARDS, cards=cards)

    raise ValueError(f"Unknown action message type: {msg_type!r}")
