from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class EventBroadcaster:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()
        self.last_event: dict[str, Any] | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)
        if self.last_event is not None:
            await websocket.send_json(self.last_event)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    def publish(self, event: dict[str, Any]) -> None:
        self.last_event = event
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(event), self.loop)

    async def _broadcast(self, event: dict[str, Any]) -> None:
        stale_connections = []
        for websocket in list(self.connections):
            try:
                await websocket.send_json(event)
            except RuntimeError:
                stale_connections.append(websocket)
        for websocket in stale_connections:
            self.disconnect(websocket)
