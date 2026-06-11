"""FastAPI application: REST room management + the game WebSocket.

The server is a thin transport over the `shengji` engine (CLAUDE.md): it owns
rooms, relays actions into the engine via game_loop, and broadcasts state. It
enforces no rules of its own.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException

from room import Room
from game_loop import handle_action, handle_join, handle_next_game, is_action_message

# In-memory room storage — acceptable for local play (CLAUDE.md).
rooms: dict[str, Room] = {}

# Stale room cleanup configuration
SWEEPER_INTERVAL = 600  # 10 minutes
STALE_ROOM_MAX_AGE = 3600  # 1 hour

sweeper_task: asyncio.Task | None = None


async def sweeper_loop():
    """Periodically clean up stale rooms (no activity for max_age_seconds)."""
    while True:
        try:
            await asyncio.sleep(SWEEPER_INTERVAL)
            # Find and remove stale rooms.
            stale_ids = [
                rid for rid, room in rooms.items()
                if room.is_stale(max_age_seconds=STALE_ROOM_MAX_AGE)
            ]
            for rid in stale_ids:
                del rooms[rid]
        except Exception:
            # Continue sweeping even if an iteration fails.
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle for the FastAPI app."""
    # Startup: start the sweeper loop.
    global sweeper_task
    sweeper_task = asyncio.create_task(sweeper_loop())
    yield
    # Shutdown: cancel the sweeper.
    if sweeper_task:
        sweeper_task.cancel()
        try:
            await sweeper_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="shengji-server", lifespan=lifespan)


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

    Supports reconnect/resume: if the player was disconnected within the grace
    period (RECONNECT_GRACE_PERIOD), they rejoin their existing seat; otherwise
    it's a fresh join.
    """
    room = rooms.get(room_id)
    if room is None:
        await websocket.close(code=4004, reason="Room not found")
        return
    if not (0 <= player_id <= 5):
        await websocket.close(code=4003, reason="Invalid player_id (0-5)")
        return

    # Check if this is a reconnect or a fresh join.
    is_reconnect = room.is_reconnecting(player_id)
    if room.has_player(player_id):
        # Seat is occupied: last-write-wins. Evict the old socket (likely a stale
        # tab or zombie connection) so the new one can take over immediately.
        old_ws = room.evict_connection(player_id)
        if old_ws is not None:
            try:
                await old_ws.close(code=4001, reason="Seat taken over")
            except Exception:
                pass
        is_reconnect = False

    await websocket.accept()

    if is_reconnect:
        room.restore_connection(player_id, websocket)
    else:
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
            elif message.get("type") == "next_game":
                await handle_next_game(room, player_id)
            # Unknown / non-action message types are ignored silently (CLAUDE.md).

    except WebSocketDisconnect:
        # Only treat this as a real disconnect if our socket is still the seat's
        # active one — an evicted socket must not clobber its replacement.
        if room.remove_connection(player_id, websocket):
            await room.broadcast({
                "type": "player_disconnected",
                "player_id": player_id,
                "connected_count": room.connected_count(),
            })


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
