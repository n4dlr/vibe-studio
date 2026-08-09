"""WebSocket Server API — Lightweight stdlib RFC 6455 WebSocket implementation for real-time streaming."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import socket
import struct
import threading
import time
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)


def make_ws_frame(payload: str) -> bytes:
    """Encodes a text payload into an unmasked WS server frame (RFC 6455)."""
    data = payload.encode("utf-8")
    length = len(data)
    if length <= 125:
        header = bytes([0x81, length])
    elif length <= 65535:
        header = bytes([0x81, 126]) + struct.pack(">H", length)
    else:
        header = bytes([0x81, 127]) + struct.pack(">Q", length)
    return header + data


class VibeWebSocketServer:
    """Minimal zero-dependency WebSocket Server for streaming agent logs and updates."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8001):
        self.host = host
        self.port = port
        self.clients: Set[socket.socket] = set()
        self.lock = threading.Lock()
        self.server_socket: socket.socket | None = None
        self.running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(10)
        self.running = True

        def _listen():
            while self.running:
                try:
                    client, addr = self.server_socket.accept()
                    t = threading.Thread(target=self._handle_client, args=(client,), daemon=True)
                    t.start()
                except Exception:
                    if not self.running:
                        break

        self._thread = threading.Thread(target=_listen, daemon=True)
        self._thread.start()
        logger.info("WebSocket server started on ws://%s:%d", self.host, self.port)

    def _handle_client(self, client: socket.socket) -> None:
        try:
            # Simple HTTP handshake for WebSocket
            data = client.recv(4096).decode("utf-8", errors="ignore")
            if "Upgrade: websocket" not in data and "Upgrade: WebSocket" not in data:
                client.close()
                return

            key = ""
            for line in data.split("\r\n"):
                if line.lower().startswith("sec-websocket-key:"):
                    key = line.split(":", 1)[1].strip()
                    break

            if not key:
                client.close()
                return

            MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
            accept_key = base64.b64encode(hashlib.sha1((key + MAGIC).encode("utf-8")).digest()).decode("utf-8")

            response = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
            )
            client.sendall(response.encode("utf-8"))

            with self.lock:
                self.clients.add(client)

            # Send welcome message
            welcome_frame = make_ws_frame(json.dumps({"type": "connected", "timestamp": time.time()}))
            client.sendall(welcome_frame)

            # Keep reading frames or wait until disconnection
            while self.running:
                chunk = client.recv(2)
                if not chunk:
                    break
        except Exception as e:
            logger.debug("WS client disconnected: %s", e)
        finally:
            with self.lock:
                if client in self.clients:
                    self.clients.remove(client)
            try:
                client.close()
            except Exception:
                pass

    def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        payload = json.dumps({"type": event_type, "data": data, "timestamp": time.time()})
        frame = make_ws_frame(payload)

        with self.lock:
            disconnected = []
            for client in self.clients:
                try:
                    client.sendall(frame)
                except Exception:
                    disconnected.append(client)
            for c in disconnected:
                self.clients.remove(c)

    def stop(self) -> None:
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        with self.lock:
            for c in list(self.clients):
                try:
                    c.close()
                except Exception:
                    pass
            self.clients.clear()


# Global WebSocket instance manager
_ws_instance: VibeWebSocketServer | None = None


def get_ws_server(host: str = "127.0.0.1", port: int = 8001) -> VibeWebSocketServer:
    global _ws_instance
    if _ws_instance is None:
        _ws_instance = VibeWebSocketServer(host=host, port=port)
        _ws_instance.start()
    return _ws_instance
