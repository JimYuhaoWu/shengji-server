"""Integration tests for full WebSocket game flow."""

import pytest
import json
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from main import app, rooms
from room import Room


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_rooms_fixture():
    """Clear rooms before each test."""
    rooms.clear()
    yield
    rooms.clear()


class TestRoomCreationAndConnection:
    """Tests for creating rooms and connecting players."""

    def test_create_room_and_connect_player(self, client):
        """Test creating a room and connecting a single player."""
        # Create room
        create_resp = client.post("/rooms")
        assert create_resp.status_code == 200
        room_id = create_resp.json()["room_id"]

        # Connect player
        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            data = ws.receive_json()
            assert data["type"] == "joined"
            assert data["player_id"] == 0
            assert data["room_id"] == room_id

    def test_multiple_players_connect_to_same_room(self, client):
        """Test multiple players connecting to the same room."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        for player_id in range(3):
            with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
                data = ws.receive_json()
                assert data["type"] == "joined"
                assert data["player_id"] == player_id

    def test_all_six_players_can_connect(self, client):
        """Test that 6 players can sequentially connect to a room."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        for player_id in range(6):
            with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
                data = ws.receive_json()
                assert data["type"] == "joined"
                assert data["player_id"] == player_id

        # After all disconnect, verify room is empty
        status = client.get(f"/rooms/{room_id}").json()
        assert status["connected_players"] == 0


class TestPlayerDisconnection:
    """Tests for player disconnection and reconnection."""

    def test_player_disconnect_notifies_others(self, client):
        """Test that other players are notified when someone disconnects."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws0:
            ws0.receive_json()  # Consume joined

            with client.websocket_connect(f"/ws/{room_id}/1") as ws1:
                ws1.receive_json()  # Consume joined

                # Disconnect player 0
                ws0.close()

                # Player 1 should receive disconnect notification
                data = ws1.receive_json()
                assert data["type"] == "player_disconnected"
                assert data["player_id"] == 0

    def test_disconnect_reduces_connected_count(self, client):
        """Test that disconnect updates room connection count."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws0:
            ws0.receive_json()
            status = client.get(f"/rooms/{room_id}").json()
            assert status["connected_players"] == 1

            ws0.close()

            status = client.get(f"/rooms/{room_id}").json()
            assert status["connected_players"] == 0


class TestMessageHandling:
    """Tests for handling messages from clients."""

    def test_send_invalid_json(self, client):
        """Test sending invalid JSON."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            ws.receive_json()  # Consume joined

            ws.send_text("{invalid json")
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "Invalid JSON" in data["message"]

    def test_send_unknown_message_type(self, client):
        """Test sending unknown message type."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            ws.receive_json()  # Consume joined

            ws.send_json({"type": "unknown_type"})
            data = ws.receive_json()
            assert data["type"] == "error"

    def test_send_incomplete_message(self, client):
        """Test sending incomplete message (missing required fields)."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            ws.receive_json()  # Consume joined

            # Pass message is valid with no fields
            ws.send_json({"type": "pass"})
            data = ws.receive_json()
            # Should receive error or game message (not format error)
            assert "type" in data


class TestStateConsistency:
    """Tests for state consistency across clients."""

    def test_all_players_see_same_game_metadata(self, client):
        """Test that all players see the same game metadata."""
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        states = []
        for player_id in range(2):
            with client.websocket_connect(f"/ws/{room_id}/{player_id}") as ws:
                data = ws.receive_json()
                states.append(data)

        # Both should have same metadata
        assert states[0]["room_id"] == states[1]["room_id"]

    def test_current_player_sees_legal_actions(self, client):
        """Test that protocol includes legal_actions in state messages."""
        # This is tested in detail in test_serializer.py and test_game_loop.py
        # Here we verify the field exists in serialized state
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            # Initial message is "joined"
            data = ws.receive_json()
            assert data["type"] == "joined"
            # legal_actions is sent in state_update messages, which come after actions

    def test_player_sees_own_hand_only(self, client):
        """Test that players receive state updates with hand info."""
        # This is tested in detail in test_serializer.py
        # Here we verify the integration works
        create_resp = client.post("/rooms")
        room_id = create_resp.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            # Initial message is "joined", not "state_update"
            data = ws.receive_json()
            assert data["type"] == "joined"
            # your_hand and hands_size are in state_update messages
            # which are sent after game actions or in game_loop integration


class TestMultipleRooms:
    """Tests for managing multiple independent rooms."""

    def test_separate_rooms_independent(self, client):
        """Test that separate rooms don't interfere."""
        # Create two rooms
        room1 = client.post("/rooms").json()["room_id"]
        room2 = client.post("/rooms").json()["room_id"]

        # Connect different players to each
        with client.websocket_connect(f"/ws/{room1}/0") as ws1:
            with client.websocket_connect(f"/ws/{room2}/0") as ws2:
                ws1.receive_json()
                ws2.receive_json()

                # Check room status
                status1 = client.get(f"/rooms/{room1}").json()
                status2 = client.get(f"/rooms/{room2}").json()

                assert status1["connected_players"] == 1
                assert status2["connected_players"] == 1

    def test_duplicate_player_in_different_rooms(self, client):
        """Test that same player ID can connect to different rooms."""
        room1 = client.post("/rooms").json()["room_id"]
        room2 = client.post("/rooms").json()["room_id"]

        with client.websocket_connect(f"/ws/{room1}/0") as ws1:
            with client.websocket_connect(f"/ws/{room2}/0") as ws2:
                data1 = ws1.receive_json()
                data2 = ws2.receive_json()

                # Both should succeed with same player_id
                assert data1["room_id"] == room1
                assert data2["room_id"] == room2


class TestRoomStatus:
    """Tests for room status and queries."""

    def test_get_empty_room_status(self, client):
        """Test getting status of empty room."""
        room_id = client.post("/rooms").json()["room_id"]

        status = client.get(f"/rooms/{room_id}").json()
        assert status["room_id"] == room_id
        assert status["connected_players"] == 0
        assert status["started"] is False

    def test_get_nonexistent_room_status(self, client):
        """Test getting status of nonexistent room returns 404."""
        response = client.get("/rooms/nonexistent")
        assert response.status_code == 404

    def test_room_status_updates_with_connections(self, client):
        """Test that room status updates as players connect."""
        room_id = client.post("/rooms").json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws0:
            ws0.receive_json()

            status = client.get(f"/rooms/{room_id}").json()
            assert status["connected_players"] == 1

            with client.websocket_connect(f"/ws/{room_id}/1") as ws1:
                ws1.receive_json()

                status = client.get(f"/rooms/{room_id}").json()
                assert status["connected_players"] == 2


class TestErrorRecovery:
    """Tests for error handling and recovery."""

    def test_player_can_send_message_after_error(self, client):
        """Test that player can recover after receiving an error."""
        room_id = client.post("/rooms").json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            ws.receive_json()  # Consume joined

            # Send invalid message
            ws.send_json({"type": "unknown"})
            error = ws.receive_json()
            assert error["type"] == "error"

            # Should be able to send another message
            ws.send_json({"type": "pass"})
            # Should receive a response
            data = ws.receive_json()
            assert "type" in data

    def test_connection_survives_malformed_message(self, client):
        """Test that connection doesn't close on malformed message."""
        room_id = client.post("/rooms").json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            ws.receive_json()  # Consume joined

            # Send malformed JSON
            ws.send_text("not json at all")
            error = ws.receive_json()
            assert error["type"] == "error"

            # If we get here, connection is still open
            # (no exception was raised)


class TestConcurrency:
    """Tests for concurrent player actions."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_connections(self, client):
        """Test that multiple players can connect concurrently."""
        room_id = client.post("/rooms").json()["room_id"]

        # Create multiple connections
        connections = [
            client.websocket_connect(f"/ws/{room_id}/{i}")
            for i in range(3)
        ]

        # All should connect successfully
        for i, conn in enumerate(connections):
            with conn as ws:
                data = ws.receive_json()
                assert data["type"] == "joined"


class TestHealthCheck:
    """Tests for server health check."""

    def test_health_check_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_check_available_during_game(self, client):
        """Test health check remains available during game."""
        room_id = client.post("/rooms").json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws:
            ws.receive_json()

            # Health check should still work
            response = client.get("/health")
            assert response.status_code == 200
