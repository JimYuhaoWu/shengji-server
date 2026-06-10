"""Tests for main.py FastAPI endpoints."""

import json
import pytest
from fastapi.testclient import TestClient
from main import app, rooms


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clear_rooms():
    """Clear rooms before each test."""
    rooms.clear()
    yield
    rooms.clear()


class TestHealthCheck:
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestCreateRoom:
    def test_create_room(self, client):
        """Test creating a new room."""
        response = client.post("/rooms")
        assert response.status_code == 200
        data = response.json()
        assert "room_id" in data
        assert len(data["room_id"]) > 0
        assert data["room_id"] in rooms

    def test_create_multiple_rooms(self, client):
        """Test creating multiple rooms with unique IDs."""
        response1 = client.post("/rooms")
        response2 = client.post("/rooms")
        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response1.json()["room_id"] != response2.json()["room_id"]


class TestGetRoomStatus:
    def test_get_room_status(self, client):
        """Test getting room status."""
        # Create a room first
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        # Get its status
        response = client.get(f"/rooms/{room_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["room_id"] == room_id
        assert data["connected_players"] == 0
        assert data["game_phase"] is None
        assert data["started"] is False

    def test_get_nonexistent_room(self, client):
        """Test getting status of nonexistent room."""
        response = client.get("/rooms/nonexistent")
        assert response.status_code == 404

    def test_room_status_with_connections(self, client):
        """Test room status reflects connected players."""
        # Create a room
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        # Add connections manually
        rooms[room_id]["connections"] = {0: None, 1: None}

        # Get status
        response = client.get(f"/rooms/{room_id}")
        assert response.status_code == 200
        assert response.json()["connected_players"] == 2


class TestWebSocketEndpoint:
    def test_websocket_invalid_room(self, client):
        """Test WebSocket connection to nonexistent room."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/nonexistent/0"):
                pass

    def test_websocket_invalid_player_id_negative(self, client):
        """Test WebSocket with invalid negative player_id."""
        # Create room first
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/{room_id}/-1"):
                pass

    def test_websocket_invalid_player_id_too_high(self, client):
        """Test WebSocket with invalid high player_id."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with pytest.raises(Exception):
            with client.websocket_connect(f"/ws/{room_id}/6"):
                pass

    def test_websocket_valid_connection(self, client):
        """Test valid WebSocket connection."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as websocket:
            # Should receive joined message
            data = websocket.receive_json()
            assert data["type"] == "joined"
            assert data["player_id"] == 0
            assert data["room_id"] == room_id

    def test_websocket_duplicate_player(self, client):
        """Test that same player cannot connect twice."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as websocket1:
            websocket1.receive_json()  # Consume joined message

            # Try to connect same player again
            with pytest.raises(Exception):
                with client.websocket_connect(f"/ws/{room_id}/0"):
                    pass

    def test_websocket_invalid_json(self, client):
        """Test sending invalid JSON to WebSocket."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as websocket:
            websocket.receive_json()  # Consume joined message

            # Send invalid JSON
            websocket.send_text("{invalid json")

            # Should receive error
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "Invalid JSON" in data["message"]

    def test_websocket_multiple_players(self, client):
        """Test multiple players connecting to same room."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as ws0:
            ws0.receive_json()  # Consume joined

            with client.websocket_connect(f"/ws/{room_id}/1") as ws1:
                ws1.receive_json()  # Consume joined

                # Check room has 2 connections
                status = client.get(f"/rooms/{room_id}").json()
                assert status["connected_players"] == 2

    def test_websocket_disconnect_notification(self, client):
        """Test that other players are notified of disconnect."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

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
                assert data["connected_count"] == 1

    def test_websocket_received_message(self, client):
        """Test that WebSocket can receive messages."""
        create_response = client.post("/rooms")
        room_id = create_response.json()["room_id"]

        with client.websocket_connect(f"/ws/{room_id}/0") as websocket:
            websocket.receive_json()  # Consume joined message

            # Send a message
            websocket.send_json({"type": "pass"})

            # Should receive error (game logic not implemented)
            data = websocket.receive_json()
            assert data["type"] == "error"
