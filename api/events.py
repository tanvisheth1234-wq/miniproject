"""A tiny in-process pub/sub the lab publishes engine events to and the
WebSocket endpoint fans out from. Deliberately lossy under pressure: a slow
browser tab must never be able to stall the mesh, so a full subscriber queue
drops its oldest entry rather than blocking the publisher."""

from __future__ import annotations

import asyncio
import itertools
from typing import Any


class EventBus:
    def __init__(self, queue_size: int = 1000) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._queue_size = queue_size
        self._seq = itertools.count(1)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: dict[str, Any]) -> dict[str, Any]:
        event = {"seq": next(self._seq), **event}
        for queue in self._subscribers:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(event)
        return event
