# shengji-server

A WebSocket game server for six-player 拖拉机 (Sheng Ji), a Chinese trick-taking card game.

## Overview

**shengji-server** is a thin FastAPI + WebSocket layer that:
- Manages game rooms (creation, joining, automatic start at 6 players)
- Runs the underlying game engine (`shengji-engine`)
- Broadcasts game state to all connected clients (human or AI)
- Handles player reconnections and graceful disconnects

The server **does not enforce game rules**—all logic lives in `shengji-engine`, which the server imports as a library. This separation ensures game integrity and makes the engine reusable for AI training, CLI tools, or other frontends.

## Architecture

### Three-Layer Design

1. **Networking Layer** (`main.py`, `room.py`)
   - FastAPI application
   - WebSocket endpoint: `/ws/{room_id}/{player_id}`
   - REST endpoints: `POST /rooms`, `GET /rooms/{room_id}`
   - Connection/disconnection handling

2. **Message Protocol** (`protocol.py`)
   - Client messages: join, play_cards, declare_trump, call_helper
   - Server messages: state updates, errors, game over
   - JSON-based for browser client compatibility

3. **Privacy & Serialization** (`serializer.py`)
   - Hide opponent hands from each client
   - Filter legal actions to current player only
   - Ensure symmetric state for debugging/logging

### Game Loop

```
Accept connection
  ↓
Send current state
  ↓
(Loop) Listen for action
    ↓
    Validate turn ownership
    ↓
    Call game.step(action) → catches ValueError for illegal moves
    ↓
    Broadcast new state (with privacy filters) to all
    ↓
    If game over, record result
```

## Dependencies

- `fastapi` — HTTP + WebSocket framework
- `uvicorn` — ASGI server
- `websockets` — WebSocket protocol
- `python-dotenv` — environment configuration
- `shengji-engine` — game rule engine (sibling repo)

## API Reference

### WebSocket: `/ws/{room_id}/{player_id}`

**Client messages:**
```json
{"type": "join", "player_id": 0}
{"type": "play_cards", "cards": [{"suit": "♥", "rank": "7", "deck_id": 0}]}
{"type": "declare_trump", "level_cards": [...]}
{"type": "call_helper", "card": {"suit": "♦", "rank": "K"}}
```

**Server messages:**
```json
{"type": "state_update", "phase": "TRICK_PLAYING", "current_player": 2, "your_hand": [...], "legal_actions": [...]}
{"type": "error", "message": "Not your turn"}
{"type": "game_over", "winner_side": "farmer", "scores": {...}}
```

### REST: `POST /rooms`

Create a new game room.

**Response:**
```json
{"room_id": "abc123"}
```

### REST: `GET /rooms/{room_id}`

Query room status (useful for matchmaking).

**Response:**
```json
{
  "room_id": "abc123",
  "connected_players": 4,
  "game_phase": "TRUMP_DECLARATION",
  "started": true
}
```

## Key Principles

See [CLAUDE.md](./CLAUDE.md) for full coding standards. Highlights:

1. **No game logic in server** — call `shengji_engine.Game.step(action)` and trust it
2. **Hand secrecy mandatory** — serialize state with opponent hands hidden
3. **Identical protocol for humans and AI** — server treats all clients the same
4. **Validate through the engine** — illegal move → engine raises, server catches and reports
5. **Async/await discipline** — all I/O is async; no blocking operations

## Development

### Setup

```bash
pip install -r requirements.txt
```

### Run

```bash
python -m uvicorn main:app --reload
```

Server runs on `http://localhost:8000`. WebSocket at `ws://localhost:8000/ws/{room_id}/{player_id}`.

### Test

```bash
pytest
```

## Project Structure

```
.
├── main.py           # FastAPI app, WebSocket & REST endpoints
├── room.py           # Room lifecycle, connection management
├── protocol.py       # Message type definitions
├── serializer.py     # State filtering (privacy)
├── CLAUDE.md         # Coding standards & patterns
├── README.md         # This file
├── requirements.txt  # Dependencies
└── tests/
    ├── test_server.py       # WebSocket integration tests
    ├── test_room.py         # Room management tests
    └── test_serializer.py   # Privacy tests
```

## Related

- **shengji-engine** — Pure Python game engine (sibling repo)
- **shengji-web** — Browser UI (future)
- **shengji-ai** — AI agents (future)
