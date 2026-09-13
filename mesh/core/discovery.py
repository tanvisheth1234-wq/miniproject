"""Peer discovery: HELLO broadcast, neighbour table, death detection.

Spec: docs/project-plan.md section 6.3 (discovery task) and section 14.1
(``visible_neighbours`` range emulation). Runs over any ``Transport``
implementation — real sockets today, ``SimulatedTransport`` later.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .packet import BROADCAST_DST, Packet, PacketError, PacketType, Priority
from .transport import Transport

# --- Section 7.3 constants relevant to discovery -----------------------------

HELLO_INTERVAL = 3.0        # seconds
NEIGHBOUR_TIMEOUT = 10.0    # seconds
PRUNE_INTERVAL = 1.0        # how often the prune loop checks for dead neighbours


class NodeRole:
    NORMAL = "NORMAL"
    GATEWAY = "GATEWAY"
    RESCUE = "RESCUE"

    ALL = (NORMAL, GATEWAY, RESCUE)


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class NeighbourInfo:
    node_id: str
    role: str
    last_seen_ms: int


class NeighbourTable:
    """Live neighbour set: who we've heard from and when.

    Death detection (section 9: "Heartbeat") is a pull, not a push — the
    prune loop compares ``last_seen_ms`` against ``NEIGHBOUR_TIMEOUT``
    rather than the neighbour announcing its own departure.
    """

    def __init__(self) -> None:
        self._neighbours: dict[str, NeighbourInfo] = {}

    def update(self, node_id: str, role: str, now_ms: Optional[int] = None) -> bool:
        """Record a HELLO from ``node_id``. Returns True if this is a
        previously-unseen (or previously-dead) neighbour."""
        now_ms = _now_ms() if now_ms is None else now_ms
        is_new = node_id not in self._neighbours
        self._neighbours[node_id] = NeighbourInfo(node_id=node_id, role=role, last_seen_ms=now_ms)
        return is_new

    def prune(self, timeout_s: float, now_ms: Optional[int] = None) -> list[str]:
        """Remove neighbours silent for longer than ``timeout_s``. Returns
        the node IDs removed."""
        now_ms = _now_ms() if now_ms is None else now_ms
        timeout_ms = int(timeout_s * 1000)
        dead = [
            node_id
            for node_id, info in self._neighbours.items()
            if now_ms - info.last_seen_ms > timeout_ms
        ]
        for node_id in dead:
            del self._neighbours[node_id]
        return dead

    def get(self, node_id: str) -> Optional[NeighbourInfo]:
        return self._neighbours.get(node_id)

    def ids(self) -> list[str]:
        return list(self._neighbours.keys())

    def snapshot(self) -> dict[str, NeighbourInfo]:
        return dict(self._neighbours)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._neighbours

    def __len__(self) -> int:
        return len(self._neighbours)


class Discovery:
    """Broadcasts HELLO on an interval, listens for peers' HELLOs, and
    maintains a live ``NeighbourTable``.

    ``visible_neighbours``, if given, is the range-emulation knob from
    section 14.1: HELLOs from any node ID not in this set are ignored,
    which forces multi-hop behaviour on a flat LAN.
    """

    def __init__(
        self,
        node_id: str,
        transport: Transport,
        role: str = NodeRole.NORMAL,
        visible_neighbours: Optional[Iterable[str]] = None,
        hello_interval: float = HELLO_INTERVAL,
        neighbour_timeout: float = NEIGHBOUR_TIMEOUT,
        prune_interval: float = PRUNE_INTERVAL,
    ) -> None:
        self.node_id = node_id
        self.role = role
        self.neighbours = NeighbourTable()

        self._transport = transport
        self._visible_neighbours = (
            set(visible_neighbours) if visible_neighbours is not None else None
        )
        self._hello_interval = hello_interval
        self._neighbour_timeout = neighbour_timeout
        self._prune_interval = prune_interval

        # Hooks for routing.py / store.py to react to topology changes;
        # left unset until something is wired up.
        self.on_peer_up: Optional[Callable[[str, str], None]] = None
        self.on_peer_down: Optional[Callable[[str], None]] = None

        self._hello_task: Optional[asyncio.Task] = None
        self._prune_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self._transport.on_receive(self._on_receive)
        self._hello_task = asyncio.create_task(self._hello_loop())
        self._prune_task = asyncio.create_task(self._prune_loop())

    async def stop(self) -> None:
        for task in (self._hello_task, self._prune_task):
            if task is not None:
                task.cancel()
        for task in (self._hello_task, self._prune_task):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._hello_task = None
        self._prune_task = None

    async def _hello_loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await self._send_hello()
                await asyncio.sleep(self._hello_interval)

    async def _send_hello(self) -> None:
        pkt = Packet(
            type=PacketType.HELLO,
            priority=Priority.STATUS,
            src=self.node_id,
            dst=BROADCAST_DST,
            ttl=1,  # HELLO is a single-hop shout, never relayed
            payload=self.role.encode("ascii"),
        )
        await self._transport.broadcast(pkt.pack())

    async def _prune_loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(self._prune_interval)
                for node_id in self.neighbours.prune(self._neighbour_timeout):
                    if self.on_peer_down is not None:
                        self.on_peer_down(node_id)

    def _on_receive(self, sender_id: str, data: bytes) -> None:
        try:
            pkt = Packet.unpack(data)
        except PacketError:
            return
        if pkt.type != PacketType.HELLO:
            return  # not discovery's concern (DATA/ACK belong to node.py's receiver task)
        if pkt.src == self.node_id:
            return  # our own broadcast, possibly looped back by the transport
        if self._visible_neighbours is not None and pkt.src not in self._visible_neighbours:
            return  # range emulation, section 14.1

        try:
            role = pkt.payload.decode("ascii") or NodeRole.NORMAL
        except UnicodeDecodeError:
            role = NodeRole.NORMAL

        is_new = self.neighbours.update(pkt.src, role)
        if is_new and self.on_peer_up is not None:
            self.on_peer_up(pkt.src, role)
