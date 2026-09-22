"""WebSocket connection manager with per-connection real broadcast loops."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger("ibvap.ws")


class ConnectionManager:
    """Each connected client gets a real asyncio.Queue + sender task, so
    broadcast truly pushes to every client (no dead sockets)."""

    def __init__(self) -> None:
        self.active: dict[WebSocket, asyncio.Queue] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self.active[ws] = q
        log.info("ws connected (%d active)", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        self.active.pop(ws, None)
        log.info("ws disconnected (%d active)", len(self.active))

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def broadcast_threadsafe(self, payload: dict) -> None:
        """Called from pipeline threads. Marshals onto the event loop."""
        if self._loop is None or not self.active:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload), self._loop)

    async def broadcast(self, payload: dict) -> None:
        if not self.active:
            return
        msg = json.dumps(payload, default=str)
        for ws, q in list(self.active.items()):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                log.warning("ws queue full; dropping frame for a slow client")

    async def sender_loop(self, ws: WebSocket) -> None:
        """Per-client sender task — drains its queue to the socket."""
        q = self.active.get(ws)
        if q is None:
            return
        try:
            while True:
                msg = await q.get()
                if msg is None:
                    break
                await ws.send_text(msg)
        except Exception:
            self.disconnect(ws)


ws_manager = ConnectionManager()
