# CLAUDE.md — shengji-server

## What You Are Building

A thin FastAPI WebSocket server for six-player 拖拉机 (Sheng Ji). The server manages game rooms, orchestrates connections, and broadcasts state from `shengji-engine` to browser clients and AI agents. **All game logic belongs in the engine**—the server is a bridge, not a rule enforcer.

## Cardinal Rules

1. **No game logic in this server.** Delegate all rule enforcement, card validity, trick resolution, scoring to the `shengji` engine. The server calls `game.step(state, action)` and never re-derives rules.
2. **Hand secrecy is non-negotiable.** `serializer.py` must filter opponent hands before any broadcast. Never send full game state to all clients.
3. **Identical WebSocket protocol for humans and AI.** Server treats them the same: JSON messages over `/ws/{room_id}/{player_id}`, no special paths for bots.
4. **Treat disconnects gracefully.** A disconnect frees the seat and notifies the room (reconnect/resume is listed under Remaining Work).
5. **Validate legality before stepping.** The real engine is forgiving — bad input often returns the state unchanged rather than raising — so the server confirms `action in state.legal_actions` (or, for KITTY, a valid 6-card bury) and replies `"Illegal move"` itself.

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

## Engine Integration (VERIFIED against the real `shengji` package)

> The engine lives in the sibling repo and is imported as the package **`shengji`**
> (NOT `shengji_engine`). Install editable: `pip install -e ../shengji-engine`.
> Everything below was read off the real source — trust it over older drafts.

### Imports
```python
from shengji import Game, GameState, Action, ActionType, GamePhase, Suit, Rank, TrumpBid
from shengji.card import Card
```

### Game API (pure / immutable)
```python
game = Game(num_players=6)
state = game.reset(dealer_id=0)            # -> GameState in DEALING
state, info = game.step(state, action)     # action may be None to auto-deal in DEALING
# info: {"phase", "current_player"}; at SCORING also {"farmer_score","next_dealer","game_over"}
```
`state.legal_actions` is precomputed for `state.current_player` in EVERY phase.

### Enums / values (wire encodings)
- `Suit`: HEARTS=`"H"`, DIAMONDS=`"D"`, CLUBS=`"C"`, SPADES=`"S"`, JOKER=`"J"`.
- `Rank`: `"2".."9"`, TEN=`"T"`, JACK=`"J"`, QUEEN=`"Q"`, KING=`"K"`, ACE=`"A"`,
  SMALL_JOKER=`"Js"`, LARGE_JOKER=`"Jl"`.
- `GamePhase`: DEALING → TRUMP_DECLARATION → KITTY → CALL_HELPER → TRICK_PLAYING → SCORING.
  Compare with `==`; serialize with `.name`.
- `ActionType`: `BID_TRUMP`, `PASS_TRUMP`, `PLAY_CARDS`, `TAKE_KITTY`, `CALL_HELPER`.
  (There is **no** `DECLARE_TRUMP` and **no** generic `PASS`.)

### `Card`
`Card(suit: Suit, rank: Rank, deck_id: int)`. Equality/hash ignore `deck_id`
(so a "pair" is two cards equal by suit+rank). `str(card) == suit.value + rank.value`.

### `Action`
```python
Action(action_type, cards=(), trump_bid=None, target_suit=None, target_card=None)
```
- `BID_TRUMP` → set `trump_bid = TrumpBid(count, suit, bidder_id)`.
- `TAKE_KITTY` / `PLAY_CARDS` → set `cards`.
- `CALL_HELPER` → `cards=(Card(suit, rank, 0),)`.
Dataclass `__eq__` compares all fields; safe to test `action in state.legal_actions`.

### `GameState` fields that matter for serialization
`phase, current_player, dealer_id, hands (tuple per player), kitty, cards_dealt,
trump_suit, trump_level (str), trump_locked, current_trump_bid, current_trick
([(player_id, cards), ...]), tricks_won ([(winner_id, cards), ...] — PER TRICK, not
per player), scores, player_levels, called_rank, called_suit, helper_players,
buried_cards`.
There is **no** `helper_card`, no `revealed_helpers`, no per-player `tricks_won`.

### The KITTY gotcha
`KITTY` legal actions = C(32,6) ≈ **906,192** bury options. NEVER serialize them.
`serializer.py` omits `legal_actions` when the count exceeds `MAX_LEGAL_ACTIONS`
(sets `legal_actions_truncated: true`); the client drives KITTY with a semantic
`take_kitty` message instead.

## Protocol (as implemented)

### Client → Server
```jsonc
{"type": "action", "index": 0}                 // pick a precomputed legal action by index
{"type": "pass_trump"}
{"type": "bid_trump", "count": 1, "suit": "H"}
{"type": "take_kitty", "cards": [<6 card dicts>]}
{"type": "call_helper", "suit": "D", "rank": "K"}
{"type": "play_cards", "cards": [<card dicts>]}
{"type": "next_game"}                           // start next hand after SCORING phase
```
Card dict: `{"suit": "H", "rank": "7", "deck_id": 0}`. `player_id` comes from the URL
path, not the message body. Unknown / non-action message types are ignored silently.

### Server → Client
```jsonc
{"type": "joined", "player_id", "room_id", "connected_players"}
{"type": "state_update", ...serialized per-player view...}
{"type": "player_connected" | "player_disconnected", "player_id", "connected_count"}
{"type": "error", "message": "Not your turn" | "Illegal move" | ...}
{"type": "game_over", "farmer_score", "next_dealer", "player_levels"}
```

### Action handling pipeline (`game_loop.handle_action`)
1. Reject if `player_id != state.current_player` → `"Not your turn"`.
2. Resolve the action: index path picks `legal_actions[i]`; semantic path rebuilds an
   `Action` and validates legality (`action in legal_actions`, except KITTY which is
   validated as a 6-card subset of the dealer's hand) → `"Illegal move"` on failure.
3. `room.state, info = game.step(room.state, action)`.
4. `await room.broadcast_state()` (each player gets their filtered view).
5. If `phase == SCORING`, broadcast `game_over`.

## Module Map (current)

| File | Responsibility |
|------|----------------|
| `main.py` | FastAPI app, REST (`/health`, `/rooms`, `/rooms/{id}`), WS endpoint + receive loop |
| `room.py` | `Room`: owns `Game`+`GameState`, connections, `broadcast`/`broadcast_state` |
| `protocol.py` | Card/Action ⇄ JSON translation; `message_to_action`; no game logic |
| `serializer.py` | Per-player privacy-filtered `state_update` payload |
| `game_loop.py` | `handle_action`, `handle_join`, legality validation |
| `conftest.py` | Test fixtures: real `Game`, `advance_to_phase` helper |

## Operational Details

- **In-memory room storage**: acceptable for local play. `Room.is_stale()` flags rooms
  idle > 1h (a sweeper is not yet wired up — see Remaining Work).
- **Async/await**: all WS sends are async; broadcasts use `asyncio.gather()`.
- **One Game per Room**: never global; `room.state` is reassigned from the engine's
  return value, never mutated in place.

## Testing Strategy

Tests run against the **real engine** (no mocking of game logic). Engine objects are
created via the `conftest.py` fixtures; only WebSockets are mocked (`AsyncMock`) or
driven through FastAPI's `TestClient`.
- `test_protocol.py` — card/action round-trips and reconstruction.
- `test_serializer.py` — privacy: own-hand-only, current-player-only actions, KITTY
  truncation, dealer-only kitty.
- `test_room.py` — connection lifecycle + broadcasting.
- `test_game_loop.py` — turn enforcement, legality, and a **full game** played to
  SCORING through `handle_action`.
- `test_integration.py` — end-to-end over `TestClient`: handshake, messaging, errors.

Run: `python -m pytest -q` (62 tests, ~5s).

## Build Status

- [x] **Step 1** `protocol.py` — engine-accurate translation
- [x] **Step 2** `main.py` — REST + WS wired to real `Room`
- [x] **Step 3** `room.py` — owns real `Game`/`GameState`
- [x] **Step 4** `serializer.py` — privacy + KITTY truncation
- [x] **Step 5** `game_loop.py` — validate-through-engine + broadcast + game_over
- [x] **Step 6** integration tests — full WebSocket flow, full game to SCORING
- [x] **Reconstruction** — replaced the original mock/`shengji_engine` code (written
  against a fictional API) with code verified against the real `shengji` package.

### Remaining Work (completed)
- [x] **Stale-room sweeper** — Background `asyncio` task runs every 10 minutes,
  cleans up rooms idle > 1 hour (wired into FastAPI lifespan).
- [x] **Reconnect/resume** — Graceful disconnect: players have 5 minutes to
  reconnect to their seat via `Room.is_reconnecting()` and `.restore_connection()`.
- [x] **Next hand / continuous play** — `handle_next_game()` resets via
  `game.next_game()` after SCORING; triggered by `{"type": "next_game"}` message.
- **Future work:**
  - Auto-start game when 6 players connected (game naturally progresses in DEALING)
  - Observer/spectator mode (read-only join after game starts)

## Session Log — 2026-06-11 (live-playtest bug fixes)

1. **Seat takeover (last-write-wins) replaces the duplicate-connection reject.**
   A new connection to an occupied seat used to be refused with code `4002`
   ("Player already connected"). Combined with client-side duplicate sockets
   (StrictMode, a stale `onclose`, a parallel reconnect loop), this produced a
   reject→close→retry storm and the user could never hold a seat. Now the
   WebSocket endpoint (`main.py`) **evicts** the old socket via
   `room.evict_connection(player_id)`, closes it with code `4001`
   ("Seat taken over"), and accepts the newcomer. `room.remove_connection` is
   now **socket-aware** (`remove_connection(player_id, websocket)`): the
   `WebSocketDisconnect` handler only frees the seat / broadcasts
   `player_disconnected` when the disconnecting socket is still the seat's active
   one, so an evicted/stale socket can't clobber its replacement. Test:
   `test_integration.py::...::test_duplicate_player_takes_over_seat` (67 passing).

### Known issues / planned work (NOT yet done)

- **`legal_actions_truncated` is overloaded as a "this is KITTY" signal.**
  `serializer.py` sets it whenever `len(legal_actions) > MAX_LEGAL_ACTIONS` (500)
  in *any* phase, and the AI client treats truncation as "go bury the kitty."
  Today only KITTY (~906k actions) exceeds the cap, but the coupling is fragile:
  any future non-KITTY phase that truncates would be mis-read as a bury and
  deadlock the client (it already bit the AI once — see shengji-ai session log).
  Plan: make the bury signal phase-explicit (key on `phase == KITTY`), and stop
  generating/serializing KITTY's enumerated actions altogether (validate the
  bury directly, which `_bury_is_valid` already does).
