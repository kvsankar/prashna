import asyncio
from collections import defaultdict

from fastapi import WebSocket

# Per-send timeout — a stalled client cannot delay other clients' messages
# nor block the API handler that called broadcast.
SEND_TIMEOUT_SECS = 2.0


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

    async def broadcast(self, room: str, message: dict) -> None:
        """Fan out concurrently with a per-send timeout.

        A slow or stalled client cannot delay the broadcast for others, and
        the API handler that awaited this returns promptly even when one
        socket is wedged. Sockets that timeout or error are removed.
        """
        clients = list(self.rooms.get(room, ()))
        if not clients:
            return
        results = await asyncio.gather(
            *(self._safe_send(ws, message) for ws in clients),
            return_exceptions=True,
        )
        for ws, ok in zip(clients, results):
            if ok is not True:
                self.leave(room, ws)

    async def _safe_send(self, ws: WebSocket, message: dict) -> bool:
        try:
            await asyncio.wait_for(ws.send_json(message), timeout=SEND_TIMEOUT_SECS)
            return True
        except Exception:
            return False


hub = Hub()
