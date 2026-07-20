import asyncio
import os
import time
from collections import defaultdict

from fastapi import WebSocket

from .diagnostics import log_diagnostic as _log_diagnostic

# Per-send timeout — a stalled client cannot delay other clients' messages
# nor block the API handler that called broadcast.
SEND_TIMEOUT_SECS = float(os.environ.get("PRASHNA_WS_SEND_TIMEOUT_SECS") or 2.0)


class Hub:
    def __init__(self) -> None:
        self.rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def join(self, room: str, ws: WebSocket) -> None:
        await ws.accept()
        self.rooms[room].add(ws)

    def leave(self, room: str, ws: WebSocket) -> None:
        self.rooms[room].discard(ws)
        if not self.rooms[room]:
            self.rooms.pop(room, None)

    def client_count(self, room: str) -> int:
        return len(self.rooms.get(room, ()))

    async def broadcast(self, room: str, message: dict) -> None:
        """Fan out concurrently with a per-send timeout.

        A slow or stalled client cannot delay the broadcast for others, and
        the API handler that awaited this returns promptly even when one
        socket is wedged. Sockets that timeout or error are removed.
        """
        clients = list(self.rooms.get(room, ()))
        if not clients:
            return
        started = time.perf_counter()
        results = await asyncio.gather(
            *(self._safe_send(ws, message) for ws in clients),
            return_exceptions=True,
        )
        failure_count = 0
        for ws, ok in zip(clients, results):
            if ok is not True:
                failure_count += 1
                self.leave(room, ws)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        if failure_count or duration_ms >= 250:
            _log_diagnostic(
                "ws.broadcast",
                outcome="success" if failure_count == 0 else "partial_failure",
                client_count=len(clients),
                failure_count=failure_count,
                duration_ms=duration_ms,
                message_type=str(message.get("type", "")),
            )

    async def _safe_send(self, ws: WebSocket, message: dict) -> bool:
        try:
            await asyncio.wait_for(ws.send_json(message), timeout=SEND_TIMEOUT_SECS)
            return True
        except Exception:
            _log_diagnostic("ws.broadcast_failure", outcome="failure")
            return False


hub = Hub()
