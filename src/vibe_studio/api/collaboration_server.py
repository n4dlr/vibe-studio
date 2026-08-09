"""Collaboration Server — WebSocket-based real-time agent state broadcasting.

Allows multiple Vibe Studio instances on a local network to observe
and interact with the same AI agent session.

Usage:
    server = CollaborationServer(workspace_root="/path/to/project")
    server.start(host="0.0.0.0", port=7891)
    # Then from another machine:
    #   ws://your-ip:7891
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Set

logger = logging.getLogger(__name__)


@dataclass
class CollabMessage:
    type: str                    # "agent_event" | "command" | "join" | "leave" | "ping"
    data: dict[str, Any] = field(default_factory=dict)
    sender: str = "server"
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "CollabMessage":
        try:
            d = json.loads(raw)
            return cls(
                type=d.get("type", "unknown"),
                data=d.get("data", {}),
                sender=d.get("sender", "client"),
                timestamp=d.get("timestamp", time.time()),
            )
        except Exception:
            return cls(type="unknown")


class CollaborationServer:
    """Broadcasts agent state to all connected WebSocket clients."""

    def __init__(
        self,
        workspace_root: str | Path,
        host: str = "127.0.0.1",
        port: int = 7891,
        command_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.workspace_root = Path(workspace_root)
        self.host = host
        self.port = port
        self.command_callback = command_callback
        self._clients: Set[Any] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the WebSocket server in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True, name="collab-server")
        self._thread.start()
        logger.info("Collaboration server starting on ws://%s:%d", self.host, self.port)

    def stop(self) -> None:
        """Stop the WebSocket server."""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def broadcast_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Broadcast an agent event to all connected clients (thread-safe)."""
        if not self._clients or not self._loop:
            return
        msg = CollabMessage(type="agent_event", data={"event": event_type, **data})
        self._broadcast_sync(msg.to_json())

    def _broadcast_sync(self, message: str) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._broadcast(message), self._loop)

    # ------------------------------------------------------------------
    # Async internals
    # ------------------------------------------------------------------

    def _run_server(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception as exc:
            logger.warning("Collaboration server stopped: %s", exc)
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        try:
            import websockets
        except ImportError:
            logger.warning("websockets not installed — collaboration server disabled. Run: pip install websockets")
            return

        async with websockets.serve(self._handle_client, self.host, self.port):
            logger.info("Collaboration server ready: ws://%s:%d", self.host, self.port)
            while self._running:
                await asyncio.sleep(0.5)

    async def _handle_client(self, websocket: Any, path: str = "/") -> None:
        self._clients.add(websocket)
        client_id = id(websocket)
        logger.info("Client %d connected (total: %d)", client_id, len(self._clients))

        # Send welcome
        welcome = CollabMessage(type="join", data={
            "workspace": str(self.workspace_root),
            "client_count": len(self._clients),
        })
        await websocket.send(welcome.to_json())

        try:
            async for raw in websocket:
                msg = CollabMessage.from_json(raw)
                await self._handle_command(msg, websocket)
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("Client %d disconnected (remaining: %d)", client_id, len(self._clients))

    async def _handle_command(self, msg: CollabMessage, sender: Any) -> None:
        """Handle incoming commands from connected clients."""
        if msg.type == "command":
            cmd = msg.data.get("cmd", "")
            args = msg.data.get("args", {})

            if cmd in ("pause", "resume", "cancel", "suggest"):
                logger.info("Remote command received: %s %s", cmd, args)
                if self.command_callback:
                    try:
                        self.command_callback(cmd, args)
                    except Exception as exc:
                        logger.warning("Command callback error: %s", exc)

            # Echo acknowledgment to all clients
            ack = CollabMessage(
                type="command_ack",
                data={"cmd": cmd, "status": "received"},
                sender="server",
            )
            await self._broadcast(ack.to_json())

        elif msg.type == "ping":
            pong = CollabMessage(type="pong", data={"ts": time.time()})
            await sender.send(pong.to_json())

    async def _broadcast(self, message: str) -> None:
        dead: set = set()
        for client in list(self._clients):
            try:
                await client.send(message)
            except Exception:
                dead.add(client)
        self._clients -= dead

    @property
    def client_count(self) -> int:
        return len(self._clients)

    @property
    def is_running(self) -> bool:
        return self._running and self._thread is not None and self._thread.is_alive()


# ---------------------------------------------------------------------------
# Convenience: create a server wired to a ChatService activity callback
# ---------------------------------------------------------------------------

def create_collab_server_for_chat(
    workspace_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 7891,
) -> CollaborationServer:
    """Create and return a CollaborationServer (not yet started)."""
    server = CollaborationServer(workspace_root=workspace_root, host=host, port=port)
    return server
