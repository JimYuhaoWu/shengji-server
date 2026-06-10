"""End-to-end tests over the real FastAPI app + WebSocket transport."""

import pytest
from fastapi.testclient import TestClient

from main import app, rooms


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_rooms():
    rooms.clear()
    yield
    rooms.clear()


def drain_until(ws, msg_type, limit=10):
    """Receive messages until one of `msg_type` arrives (or limit reached)."""
    for _ in range(limit):
        msg = ws.receive_json()
        if msg["type"] == msg_type:
            return msg
    raise AssertionError(f"Did not receive {msg_type!r}")


class TestRest:
    def test_health(self, client):
        assert client.get("/health").json() == {"status": "ok"}

    def test_create_room(self, client):
        rid = client.post("/rooms").json()["room_id"]
        assert rid in rooms

    def test_room_status(self, client):
        rid = client.post("/rooms").json()["room_id"]
        body = client.get(f"/rooms/{rid}").json()
        assert body["room_id"] == rid
        assert body["game_phase"] == "DEALING"

    def test_missing_room_404(self, client):
        assert client.get("/rooms/nope").status_code == 404


class TestWebSocketHandshake:
    def test_join_then_state(self, client):
        rid = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{rid}/0") as ws:
            joined = ws.receive_json()
            assert joined["type"] == "joined"
            assert joined["player_id"] == 0
            state = ws.receive_json()
            assert state["type"] == "state_update"
            assert state["your_player_id"] == 0

    def test_invalid_player_id_rejected(self, client):
        rid = client.post("/rooms").json()["room_id"]
        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/{rid}/9"):
                pass

    def test_unknown_room_rejected(self, client):
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/ghost/0"):
                pass

    def test_duplicate_player_rejected(self, client):
        rid = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{rid}/0") as ws0:
            ws0.receive_json()
            with pytest.raises(Exception):
                with client.websocket_connect(f"/ws/{rid}/0"):
                    pass


class TestMessaging:
    def test_invalid_json(self, client):
        rid = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{rid}/0") as ws:
            drain_until(ws, "state_update")
            ws.send_text("{not json")
            assert ws.receive_json() == {"type": "error", "message": "Invalid JSON"}

    def test_unknown_type_ignored(self, client):
        rid = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{rid}/0") as ws:
            drain_until(ws, "state_update")
            # Unknown, non-action message: silently ignored, so a following
            # valid error-producing message is what we observe next.
            ws.send_json({"type": "totally_unknown"})
            ws.send_text("garbage")
            assert ws.receive_json()["type"] == "error"

    def test_not_your_turn_error(self, client):
        rid = client.post("/rooms").json()["room_id"]
        # Player 0 is current at start; connect player 1 and have them act.
        with client.websocket_connect(f"/ws/{rid}/0") as ws0:
            drain_until(ws0, "state_update")
            with client.websocket_connect(f"/ws/{rid}/1") as ws1:
                drain_until(ws1, "state_update")
                ws1.send_json({"type": "action", "index": 0})
                msg = drain_until(ws1, "error")
                assert msg["message"] == "Not your turn"


class TestTwoPlayerActionFlow:
    def test_action_broadcasts_state_to_all(self, client):
        rid = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{rid}/0") as ws0:
            drain_until(ws0, "state_update")
            with client.websocket_connect(f"/ws/{rid}/1") as ws1:
                drain_until(ws1, "state_update")
                # Player 0 (current at game start) passes during dealing.
                ws0.send_json({"type": "pass_trump"})
                # Both connected players receive a fresh state_update.
                assert drain_until(ws0, "state_update")["type"] == "state_update"
                assert drain_until(ws1, "state_update")["type"] == "state_update"


class TestMultipleRooms:
    def test_rooms_are_independent(self, client):
        r1 = client.post("/rooms").json()["room_id"]
        r2 = client.post("/rooms").json()["room_id"]
        with client.websocket_connect(f"/ws/{r1}/0") as a:
            a.receive_json()
            with client.websocket_connect(f"/ws/{r2}/0") as b:
                b.receive_json()
                assert client.get(f"/rooms/{r1}").json()["connected_players"] == 1
                assert client.get(f"/rooms/{r2}").json()["connected_players"] == 1
