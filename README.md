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
   - Client actions: action (by index), pass_trump, bid_trump, take_kitty, call_helper, play_cards
   - Server messages: joined, state updates, player connected/disconnected, errors, game over
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

`player_id` (0–5) is taken from the URL path. Card dicts use single-character suit
and rank values: `{"suit": "H", "rank": "7", "deck_id": 0}` (suits `H/D/C/S/J`,
ten = `"T"`, jokers = `"Js"`/`"Jl"`).

**Client messages:**
```json
{"type": "action", "index": 0}
{"type": "pass_trump"}
{"type": "bid_trump", "count": 1, "suit": "H"}
{"type": "take_kitty", "cards": [ /* exactly 6 card dicts */ ]}
{"type": "call_helper", "suit": "D", "rank": "K"}
{"type": "play_cards", "cards": [{"suit": "H", "rank": "7", "deck_id": 0}]}
{"type": "next_game"}
```
The current player may either pick a precomputed legal action by `index` (the server
sends `legal_actions` to that player) or send the equivalent semantic message. The
KITTY phase has ~906k bury options, so `legal_actions` is omitted there
(`legal_actions_truncated: true`) and you must use `take_kitty`.

**Server messages:**
```json
{"type": "joined", "player_id": 0, "room_id": "abc123", "connected_players": 1}
{"type": "state_update", "phase": "TRICK_PLAYING", "current_player": 2, "your_hand": [], "hands_size": [25,25,25,25,25,25], "legal_actions": []}
{"type": "player_connected", "player_id": 1, "connected_count": 2}
{"type": "player_disconnected", "player_id": 1, "connected_count": 1}
{"type": "error", "message": "Not your turn"}
{"type": "game_over", "farmer_score": 80, "next_dealer": 1, "player_levels": ["R1:2", "..."]}
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

See [CLAUDE.md](./CLAUDE.md) for full coding standards and the verified engine API. Highlights:

1. **No game logic in server** — call `game.step(state, action)` on the `shengji` engine
2. **Hand secrecy mandatory** — serialize state with opponent hands hidden
3. **Identical protocol for humans and AI** — server treats all clients the same
4. **Validate legality before stepping** — confirm `action in legal_actions`, reply `"Illegal move"` otherwise
5. **Async/await discipline** — all I/O is async; broadcasts use `asyncio.gather()`

## Development

### Setup

```bash
# Install the engine (sibling repo) editable, then the server deps:
pip install -e ../shengji-engine
pip install -r requirements.txt   # requirements.txt also references the engine via -e
```

### Run

```bash
python -m uvicorn main:app --reload
```

Server runs on `http://localhost:8000`. WebSocket at `ws://localhost:8000/ws/{room_id}/{player_id}`.

### Test

```bash
python -m pytest -q     # 67 tests (run against the real engine, ~6s)
```

## Project Structure

```
.
├── main.py             # FastAPI app, WebSocket & REST endpoints
├── room.py             # Room: owns Game/GameState, connections, broadcasting
├── protocol.py         # Card/Action <-> JSON translation
├── serializer.py       # Per-player privacy-filtered state
├── game_loop.py        # Action validation, engine step, broadcast
├── conftest.py         # Shared pytest fixtures (real engine)
├── test_protocol.py    # Translation round-trips
├── test_serializer.py  # Privacy filtering
├── test_room.py        # Connection lifecycle + broadcasting
├── test_game_loop.py   # Turn enforcement, legality, full game to SCORING
├── test_integration.py # End-to-end over FastAPI TestClient
├── CLAUDE.md           # Coding standards, verified engine API, build status
├── README.md           # This file
└── requirements.txt    # Dependencies
```

## Status

All core features are complete and the suite passes (67 tests) against the **real**
`shengji` engine:

- [x] Reconstruction: real engine, correct API
- [x] Stale-room sweeper: background cleanup every 10 minutes
- [x] Reconnect/resume: 5-minute grace period for reconnecting players
- [x] Next-hand support: `game.next_game()` wired to `{"type": "next_game"}` message

See CLAUDE.md for details on remaining future enhancements (auto-start, observer mode).

## Related

- **shengji-engine** — Pure Python game engine (sibling repo)
- **shengji-web** — Browser UI (future)
- **shengji-ai** — AI agents (future)
