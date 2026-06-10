"""FastAPI application: REST room management + the game WebSocket.

The server is a thin transport over the `shengji` engine (CLAUDE.md): it owns
rooms, relays actions into the engine via game_loop, and broadcasts state. It
enforces no rules of its own.
"""

import json
import uuid

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException

from room import Room
from game_loop import handle_action, handle_join, is_action_message

app = FastAPI(title="shengji-server")

# In-memory room storage — acceptable for local play (CLAUDE.md).
rooms: dict[str, Room] = {}


def _new_room_id() -> str:
    return uuid.uuid4().hex[:8]


# ============ REST ============


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.post("/rooms")
async def create_room():
    """Create a new game room and return its id."""
    room_id = _new_room_id()
    rooms[room_id] = Room(room_id)
    return {"room_id": room_id}


@app.get("/rooms/{room_id}")
async def get_room(room_id: str):
    """Return a room's status, or 404 if it doesn't exist."""
    room = rooms.get(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found")
    return room.status()


# ============ WEBSOCKET ============


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: int):
    """One player's connection to a room.

    Accepts the socket, registers the player, sends current state, then relays
    action messages to the game loop until the player disconnects.
    """
    room = rooms.get(room_id)
    if room is None:
        await websocket.close(code=4004, reason="Room not found")
        return
    if not (0 <= player_id <= 5):
        await websocket.close(code=4003, reason="Invalid player_id (0-5)")
        return
    if room.has_player(player_id):
        await websocket.close(code=4002, reason="Player already connected")
        return

    await websocket.accept()
    room.add_connection(player_id, websocket)

    # Confirm join, then send the player their current view.
    await websocket.send_json({
        "type": "joined",
        "player_id": player_id,
        "room_id": room_id,
        "connected_players": room.connected_count(),
    })
    await handle_join(room, player_id)
    await room.broadcast(
        {
            "type": "player_connected",
            "player_id": player_id,
            "connected_count": room.connected_count(),
        },
        exclude=player_id,
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue
            if not isinstance(message, dict) or "type" not in message:
                await websocket.send_json({"type": "error", "message": "Malformed message"})
                continue

            if is_action_message(message):
                await handle_action(room, player_id, message)
            # Unknown / non-action message types are ignored silently (CLAUDE.md).

    except WebSocketDisconnect:
        room.remove_connection(player_id)
        await room.broadcast({
            "type": "player_disconnected",
            "player_id": player_id,
            "connected_count": room.connected_count(),
        })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
