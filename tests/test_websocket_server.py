"""Tests for WebSocket server API."""
from __future__ import annotations

import json
import socket
import time
import pytest

from vibe_studio.api.websocket_server import VibeWebSocketServer, make_ws_frame


def test_make_ws_frame():
    payload = "hello world"
    frame = make_ws_frame(payload)
    assert len(frame) > len(payload)
    assert frame[0] == 0x81  # Text frame, FIN bit set


def test_websocket_server_broadcast():
    ws_server = VibeWebSocketServer(host="127.0.0.1", port=8912)
    ws_server.start()
    time.sleep(0.1)

    try:
        # Connect socket to server
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", 8912))

        # Send WebSocket handshake
        req = (
            "GET / HTTP/1.1\r\n"
            "Host: 127.0.0.1:8912\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode("utf-8"))
        resp = sock.recv(1024).decode("utf-8")
        assert "101 Switching Protocols" in resp

        time.sleep(0.1)

        # Broadcast event
        ws_server.broadcast("test_event", {"foo": "bar"})

        sock.settimeout(2.0)
        data = sock.recv(1024)
        assert len(data) > 0
        sock.close()
    finally:
        ws_server.stop()
