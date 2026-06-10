"""FastAPI application with WebSocket and REST endpoints."""

import json
import uuid
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

app = FastAPI(title="shengji-server")


# ============ DATA MODELS ============


class RoomStatus(BaseModel):
    """Room status response."""
    room_id: str
    connected_players: int
    game_phase: str | None
    started: bool
    created_at: str


class CreateRoomResponse(BaseModel):
    """Response from room creation."""
    room_id: str


# ============ IN-MEMORY STORAGE ============


rooms: dict[str, dict] = {}


def create_room_id() -> str:
    """Generate a unique room ID."""
    return str(uuid.uuid4())[:8]


# ============ REST ENDPOINTS ============


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/rooms")
async def create_room() -> CreateRoomResponse:
    """Create a new game room.

    Returns:
        CreateRoomResponse with the new room_id
    """
    room_id = create_room_id()
    rooms[room_id] = {
        "room_id": room_id,
        "connections": {},  # player_id -> WebSocket
        "created_at": datetime.now(),
        "game_state": None,
        "phase": None,
    }
    return CreateRoomResponse(room_id=room_id)


@app.get("/rooms/{room_id}")
async def get_room_status(room_id: str) -> RoomStatus:
    """Get status of a room.

    Args:
        room_id: The room ID

    Returns:
        RoomStatus with connected players and game phase

    Raises:
        HTTPException 404 if room not found
    """
    if room_id not in rooms:
        raise HTTPException(status_code=404, detail="Room not found")

    room = rooms[room_id]
    return RoomStatus(
        room_id=room_id,
        connected_players=len(room["connections"]),
        game_phase=room["phase"],
        started=room["phase"] is not None,
        created_at=room["created_at"].isoformat(),
    )


# ============ WEBSOCKET ENDPOINT ============


@app.websocket("/ws/{room_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str, player_id: int):
    """WebSocket endpoint for game players.

    Args:
        websocket: The WebSocket connection
        room_id: The room ID to join
        player_id: The player ID (0-5)
    """
    if room_id not in rooms:
        await websocket.close(code=4004, reason="Room not found")
        return

    if not (0 <= player_id <= 5):
        await websocket.close(code=4003, reason="Invalid player_id (must be 0-5)")
        return

    room = rooms[room_id]

    if player_id in room["connections"]:
        await websocket.close(code=4002, reason="Player already connected")
        return

    await websocket.accept()
    room["connections"][player_id] = websocket

    try:
        # Send initial state (placeholder)
        await websocket.send_json({
            "type": "joined",
            "player_id": player_id,
            "room_id": room_id,
            "connected_players": len(room["connections"]),
        })

        # Listen for messages
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            # TODO: Handle messages when room.py is implemented
            # For now, just echo back
            await websocket.send_json({
                "type": "error",
                "message": "Game logic not yet implemented",
            })

    except WebSocketDisconnect:
        room["connections"].pop(player_id, None)

        # Broadcast disconnection to other players
        for ws in room["connections"].values():
            try:
                await ws.send_json({
                    "type": "player_disconnected",
                    "player_id": player_id,
                    "connected_count": len(room["connections"]),
                })
            except:
                pass

        # Clean up stale rooms (no connections for 1 hour would happen elsewhere)

    except json.JSONDecodeError:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid JSON",
        })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
