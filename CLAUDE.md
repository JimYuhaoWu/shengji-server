# CLAUDE.md — shengji-server

## What You Are Building

A thin FastAPI WebSocket server for six-player 拖拉机 (Sheng Ji). The server manages game rooms, orchestrates connections, and broadcasts state from `shengji-engine` to browser clients and AI agents. **All game logic belongs in the engine**—the server is a bridge, not a rule enforcer.

## Cardinal Rules

1. **No game logic in this server.** Delegate all rule enforcement, card validity, trick resolution, scoring to `shengji-engine`. The server calls `game.step(action)` and trusts it to raise on violations.
2. **Hand secrecy is non-negotiable.** `serializer.py` must filter opponent hands before any broadcast. Never send full game state to all clients.
3. **Identical WebSocket protocol for humans and AI.** Server treats them the same: JSON messages over `/ws/{room_id}/{player_id}`, no special paths for bots.
4. **Treat disconnects gracefully.** Pause game if player disconnects; resume when they reconnect within timeout. Remove stale rooms.
5. **Validate through the engine, not the server.** Illegal move → call `game.step(action)` and let it raise `ValueError`; catch and broadcast error to the client.

## Coding Standards

### 1. Simplicity First
- **Minimum code that solves the problem.** No speculative abstractions or features beyond what's asked.
- **No error handling for impossible scenarios.** Trust internal code and framework guarantees; validate only at system boundaries (user input, external APIs).
- **Three similar lines = time to extract.** One-off code stays inline.
- **Ask: "Is this overcomplicated?"** If yes, rewrite it.

### 2. Surgical Changes
- **Touch only what you must.** Don't improve adjacent code unless requested.
- **Match existing style.** Even if you'd do it differently.
- **Remove only YOUR orphans.** If your changes make an import/variable/function unused, delete it. Don't clean up pre-existing dead code.
- **Every changed line traces to the user's request.** No drive-by refactoring.

### 3. Think Before Coding
- **State assumptions explicitly.** Uncertain about interpretation? Ask before implementing.
- **Surface tradeoffs.** Don't pick silently between equally valid approaches.
- **Don't hide confusion.** If something is unclear, stop and name what's confusing.
- **Simplify when possible.** If 50 lines can do what 200 does, rewrite it.

### 4. Goal-Driven Execution
- **Define success criteria first.** Transform tasks into verifiable checks:
  - "Add WebSocket endpoint" → test connection, message receipt, broadcast
  - "Fix disconnect bug" → write test for reconnect, make it pass
  - "Implement room expiry" → test stale room cleanup, pass it
- **State brief plans for multi-step work.** Format: `1. [Step] → verify: [check]`
- **Loop until verified.** Success = tests pass + behavior matches spec.

## System Architecture

Three main modules:
- **main.py**: FastAPI app, WebSocket (`/ws/{room_id}/{player_id}`) and REST endpoints (`POST /rooms`, `GET /rooms/{room_id}`)
- **room.py**: Room lifecycle, connection management, message dispatch, game loop
- **protocol.py**: WebSocket message types and parsing
- **serializer.py**: State serialization with hand secrecy and legal action filtering

## Critical Implementation Patterns

### WebSocket Flow
```
Accept connection → send current game state → listen for action messages in loop → on action:
  → validate turn ownership → parse action → call game.step(action) → broadcast updated state or error
```

### Message Handling
1. Parse JSON message as protocol type (join, play_cards, declare_trump, etc.)
2. Validate sender is current player (if action-based) or observer (if read-only)
3. Convert to `shengji-engine` action object
4. Call `game.step(state, action)` and let it raise on illegality
5. If valid: update state, broadcast new state (with privacy) to all; if invalid: send error to sender only

### State Serialization
Return complete game state but:
- Set `your_hand` only for the viewing player's own cards
- Set `legal_actions` only for the current player
- Never include opponent hands in any broadcast

Example:
```python
def serialize_for_player(game_state: GameState, viewing_player_id: int):
    return {
        "phase": game_state.phase,
        "current_player": game_state.current_player,
        "your_hand": list(game_state.hands[viewing_player_id]),  # Only for this player
        "hands_size": [len(h) for h in game_state.hands],         # Never full hands
        "legal_actions": game_state.legal_actions if game_state.current_player == viewing_player_id else [],
        # ... rest of state
    }
```

### Broadcasting
Use `asyncio.gather()` to send state simultaneously to all connections:
```python
await asyncio.gather(*[conn.send(json.dumps(state)) for conn in room.connections])
```
Not sequential awaits—they serialize and delay updates.

### Error Handling
- **Illegal move**: catch `ValueError` from `game.step()`, send `{"type": "error", "message": "..."}` to client
- **Disconnects**: remove from active connections, pause game; on reconnect within timeout, restore session
- **Unknown message type**: log and ignore silently
- **Malformed JSON**: catch `json.JSONDecodeError`, send error response

## Key Data Structures

### Room
```python
class Room:
    room_id: str
    game: Game  # The engine instance
    connections: dict[int, WebSocket]  # player_id -> WebSocket
    state: GameState  # Current game state
    created_at: float
    last_activity: float
```

### Protocol Messages (Client → Server)
```python
# Join
{"type": "join", "player_id": int}

# Play cards
{"type": "play_cards", "cards": [{"suit": "♥", "rank": "7", "deck_id": 0}, ...]}

# Declare trump
{"type": "declare_trump", "level_cards": [{"suit": "♥", "rank": "7"}, ...]}

# Call helper
{"type": "call_helper", "card": {"suit": "♦", "rank": "K"}}
```

### Protocol Messages (Server → Client)
```python
# Game state update
{
    "type": "state_update",
    "phase": "TRICK_PLAYING",
    "current_player": 2,
    "your_hand": [...],
    "hands_size": [5, 6, 4, 7, 5, 6],
    "legal_actions": [...],
    "current_trick": [...],
    "scores": [20, 0, 15, 0, 0, 10],
    ...
}

# Error
{"type": "error", "message": "Not your turn"}

# Game over
{"type": "game_over", "winner_side": "farmer", "scores": {...}}
```

## Operational Details

- **In-memory room storage**: Acceptable for local play; stale rooms expire after 1 hour of inactivity
- **Dealer ID tracking**: Persists across rounds; remember to cycle to next dealer
- **Observer support**: Allow players to join as read-only if game already started (< 6 connected)
- **Async/await**: All I/O is async; use `await` for WebSocket sends, `asyncio.gather()` for broadcasts
- **No blocking operations**: Never call synchronous file I/O, database I/O, or `time.sleep()` in async context

## Testing Strategy

### Unit Tests
```python
# test_serializer.py
def test_hand_hidden_from_opponent(): ...
def test_legal_actions_only_for_current_player(): ...

# test_room.py
def test_room_creation(): ...
def test_player_join(): ...
def test_disconnect_handling(): ...
```

### Integration Tests
```python
# test_server.py — WebSocket client simulation
async def test_full_game_via_websocket():
    async with websockets.connect("ws://localhost:8000/ws/room1/0") as ws:
        # Join
        await ws.send(json.dumps({"type": "join", "player_id": 0}))
        state = json.loads(await ws.recv())
        assert state["phase"] == "TRUMP_DECLARATION"
        
        # Play action
        await ws.send(json.dumps({"type": "play_cards", "cards": [...]}))
        state = json.loads(await ws.recv())
        assert state["phase"] == "TRICK_PLAYING"
```

## Important Patterns (Not Mistakes, But Easy to Confuse)

- **Async/await discipline**: All network I/O is async. Never mix `asyncio` with blocking calls. Use `asyncio.create_task()` for background room cleanup.
- **Room lifecycle**: Create on `POST /rooms`, destroy after 1-hour inactivity or manual close. Don't leave rooms in memory forever.
- **Action parsing**: Convert JSON action message → `shengji_engine.Action` dataclass before passing to `game.step()`. The engine only speaks its own types.
- **State ownership**: Each room owns its `GameState` instance. Never share state between rooms. Never mutate state in place—always use engine's return value.
- **Broadcast symmetry**: When you broadcast state, every client sees the same structure (just with their own hand/actions filled in). Consistency prevents client-side bugs.

## Build Order

1. `protocol.py` (message types) + basic tests
2. `main.py` (FastAPI + endpoints) with health check
3. `room.py` (Room class, connection management)
4. `serializer.py` (state filtering + privacy)
5. `game loop` (accept actions, call engine, broadcast state)
6. Integration tests (full WebSocket flow)

Do not proceed to step N+1 until tests for step N all pass.
