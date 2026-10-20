"""A finite-capacity radio model for the simulator.

``SimulatedTransport`` delivers instantly, so nothing ever queues and the
priority queue that section 9.1 describes has nothing to reorder. A real
radio sends one frame at a time. ``RadioTransport`` wraps a transport and,
when ``RadioConfig.service_ms`` is above zero, makes every unicast wait for
the air: one packet per ``service_ms``, picked in priority order (SOS before
NORMAL before STATUS, oldest first within a priority). That is what lets the
lab show an SOS overtaking a backlog of ordinary traffic.

HELLO broadcasts bypass the scheduler -- they are tiny, single-hop beacons,
and starving them would make nodes look dead for the wrong reason.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import itertools
from dataclasses import dataclass
from typing import Callable, Optional

from mesh.core.transport import TransportError
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport

_PRIORITY_BYTE = 4  # packet.py HEADER_FORMAT: magic(2) version(1) type(1) priority(1)


@dataclass
class RadioConfig:
    """Shared by every node in a lab so one slider changes the whole mesh."""

    service_ms: float = 0.0


class RadioTransport:
    def __init__(
        self,
        inner: SimulatedTransport,
        network: SimulatedNetwork,
        config: RadioConfig,
    ) -> None:
        self.node_id = inner.node_id
        self._inner = inner
        self._network = network
        self._config = config
        self._heap: list[tuple[int, int, str, bytes, asyncio.Future]] = []
        self._counter = itertools.count()
        self._worker: Optional[asyncio.Task] = None

    # -- Transport interface -------------------------------------------------------

    def on_receive(self, callback: Callable[[str, bytes], None]) -> None:
        self._inner.on_receive(callback)

    async def start(self) -> None:
        await self._inner.start()

    async def stop(self) -> None:
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None
        while self._heap:
            *_, future = heapq.heappop(self._heap)
            if not future.done():
                future.set_exception(TransportError(f"{self.node_id!r} went offline"))
        await self._inner.stop()

    async def broadcast(self, data: bytes) -> None:
        await self._inner.broadcast(data)

    async def send(self, node_id: str, data: bytes) -> None:
        # same up-front check SimulatedNetwork.send makes, so the caller still
        # sees a TransportError for "no link" synchronously (Node._dispatch
        # relies on that to fall back to store-and-forward) rather than from
        # inside the scheduler.
        if not self._network.linked(self.node_id, node_id):
            raise TransportError(f"{self.node_id!r} has no link to {node_id!r}")
        if self._config.service_ms <= 0 and not self._heap and self._worker is None:
            await self._inner.send(node_id, data)
            return

        priority = data[_PRIORITY_BYTE] if len(data) > _PRIORITY_BYTE else 1
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        heapq.heappush(self._heap, (priority, next(self._counter), node_id, data, future))
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._drain())
        await future

    # -- scheduler -------------------------------------------------------------------

    async def _drain(self) -> None:
        while self._heap:
            _priority, _seq, node_id, data, future = heapq.heappop(self._heap)
            if self._config.service_ms > 0:
                await asyncio.sleep(self._config.service_ms / 1000.0)
            try:
                await self._inner.send(node_id, data)
            except TransportError as exc:
                if not future.done():
                    future.set_exception(exc)
            else:
                if not future.done():
                    future.set_result(None)
        self._worker = None
