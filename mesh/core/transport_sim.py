"""In-memory ``Transport`` implementation for the network simulator.

Spec: docs/project-plan.md section 6.1 / 13 / 15. Unlike ``UdpTcpTransport``,
every send is a scheduled coroutine, not a socket write -- no ports, no
real network, deterministic given a seed, and fast enough to run fifty
nodes in one process. A ``SimulatedNetwork`` owns the link matrix ("who
can hear whom") and the per-link loss/latency model; each simulated node
gets its own ``SimulatedTransport`` wired to that shared network.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Callable, Optional

from .transport import Transport, TransportError


@dataclass
class LinkConfig:
    loss: float = 0.0  # probability in [0, 1] that a packet on this link is dropped
    latency_ms: tuple[float, float] = (0.0, 0.0)  # (min, max) delay, sampled uniformly

    def __post_init__(self) -> None:
        if not 0.0 <= self.loss <= 1.0:
            raise ValueError(f"loss must be in [0, 1], got {self.loss}")
        lo, hi = self.latency_ms
        if lo < 0 or hi < lo:
            raise ValueError(f"invalid latency_ms range: {self.latency_ms}")


class SimulatedNetwork:
    """Owns the link matrix and delivers packets between registered
    ``SimulatedTransport`` instances with configurable loss and latency."""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._transports: dict[str, "SimulatedTransport"] = {}
        self._links: dict[tuple[str, str], LinkConfig] = {}
        self._rng = random.Random(seed)

    # -- registration --------------------------------------------------------

    def register(self, node_id: str, transport: "SimulatedTransport") -> None:
        self._transports[node_id] = transport

    def unregister(self, node_id: str) -> None:
        self._transports.pop(node_id, None)

    # -- link matrix -----------------------------------------------------------

    def set_link(
        self,
        a: str,
        b: str,
        loss: float = 0.0,
        latency_ms: tuple[float, float] = (0.0, 0.0),
        bidirectional: bool = True,
    ) -> None:
        """Configure who can hear whom. ``loss`` is the per-packet drop
        probability; ``latency_ms`` is the (min, max) delivery delay."""
        config = LinkConfig(loss=loss, latency_ms=latency_ms)
        self._links[(a, b)] = config
        if bidirectional:
            self._links[(b, a)] = config

    def remove_link(self, a: str, b: str, bidirectional: bool = True) -> None:
        self._links.pop((a, b), None)
        if bidirectional:
            self._links.pop((b, a), None)

    def neighbours_of(self, node_id: str) -> list[str]:
        """Node IDs reachable in one hop from ``node_id`` per the link matrix."""
        return [dst for (src, dst) in self._links if src == node_id]

    def linked(self, a: str, b: str) -> bool:
        return (a, b) in self._links

    # -- delivery --------------------------------------------------------------

    async def send(self, src: str, dst: str, data: bytes) -> None:
        link = self._links.get((src, dst))
        if link is None:
            raise TransportError(f"{src!r} has no link to {dst!r}")
        self._dispatch(src, dst, data, link)

    async def broadcast(self, src: str, data: bytes) -> None:
        for dst in self.neighbours_of(src):
            self._dispatch(src, dst, data, self._links[(src, dst)])

    def _dispatch(self, src: str, dst: str, data: bytes, link: LinkConfig) -> None:
        if self._rng.random() < link.loss:
            return  # dropped: simulates real packet loss, never delivered
        lo, hi = link.latency_ms
        delay_s = self._rng.uniform(lo, hi) / 1000.0
        asyncio.create_task(self._deliver_after(src, dst, data, delay_s))

    async def _deliver_after(self, src: str, dst: str, data: bytes, delay_s: float) -> None:
        if delay_s > 0:
            await asyncio.sleep(delay_s)
        transport = self._transports.get(dst)
        if transport is not None:
            transport._deliver(src, data)


class SimulatedTransport:
    """``Transport`` implementation backed by a ``SimulatedNetwork`` instead
    of real sockets. Satisfies the same interface as ``UdpTcpTransport``, so
    routing and reliability code is written once against ``Transport`` and
    never against sockets or the simulator directly (section 6.1)."""

    def __init__(self, node_id: str, network: SimulatedNetwork) -> None:
        self.node_id = node_id
        self._network = network
        self._callback: Optional[Callable[[str, bytes], None]] = None

    def on_receive(self, callback: Callable[[str, bytes], None]) -> None:
        self._callback = callback

    async def start(self) -> None:
        self._network.register(self.node_id, self)

    async def stop(self) -> None:
        self._network.unregister(self.node_id)

    async def send(self, node_id: str, data: bytes) -> None:
        await self._network.send(self.node_id, node_id, data)

    async def broadcast(self, data: bytes) -> None:
        await self._network.broadcast(self.node_id, data)

    def _deliver(self, sender_id: str, data: bytes) -> None:
        if self._callback is not None:
            self._callback(sender_id, data)
