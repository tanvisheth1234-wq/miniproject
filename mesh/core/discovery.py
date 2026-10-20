"""Peer discovery: HELLO broadcast, neighbour table, death detection.

Spec: docs/project-plan.md section 6.3 (discovery task) and section 14.1
(``visible_neighbours`` range emulation). Runs over any ``Transport``
implementation — real sockets today, ``SimulatedTransport`` later.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .packet import BROADCAST_DST, Packet, PacketError, PacketType, Priority
from .transport import Transport

# --- Section 7.3 constants relevant to discovery -----------------------------

HELLO_INTERVAL = 3.0        # seconds
NEIGHBOUR_TIMEOUT = 10.0    # seconds
PRUNE_INTERVAL = 1.0        # how often the prune loop checks for dead neighbours

PUBLIC_KEY_SIZE = 32  # raw Ed25519 public key, appended to a HELLO's payload

# Section 8.2: link_quality is "the fraction of the last 20 expected HELLOs
# that actually arrived". LINK_QUALITY_REPORT_DELTA keeps the estimate from
# firing a topology change on every tiny wobble -- only a real shift is
# worth recomputing routes for.
LINK_QUALITY_WINDOW = 20
LINK_QUALITY_REPORT_DELTA = 0.1


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
    public_key: Optional[bytes] = None


class NeighbourTable:
    """Live neighbour set: who we've heard from and when.

    Death detection (section 9: "Heartbeat") is a pull, not a push — the
    prune loop compares ``last_seen_ms`` against ``NEIGHBOUR_TIMEOUT``
    rather than the neighbour announcing its own departure.
    """

    def __init__(self) -> None:
        self._neighbours: dict[str, NeighbourInfo] = {}

    def update(
        self, node_id: str, role: str, now_ms: Optional[int] = None, public_key: Optional[bytes] = None
    ) -> bool:
        """Record a HELLO from ``node_id``. Returns True if this is a
        previously-unseen (or previously-dead) neighbour."""
        now_ms = _now_ms() if now_ms is None else now_ms
        is_new = node_id not in self._neighbours
        self._neighbours[node_id] = NeighbourInfo(
            node_id=node_id, role=role, last_seen_ms=now_ms, public_key=public_key
        )
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
        public_key: Optional[bytes] = None,
    ) -> None:
        self.node_id = node_id
        self.role = role
        self.neighbours = NeighbourTable()
        # distributed with every HELLO (section 10, SEC-6) so a neighbour
        # can verify our signatures without a separate key-exchange step;
        # None means this node doesn't sign -- opt-in, like session_key.
        self._public_key = public_key

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
        # fired with (neighbour_id, link_quality) when the HELLO reception
        # ratio for a link has moved meaningfully since last reported
        self.on_link_quality: Optional[Callable[[str, float], None]] = None

        self._hello_times: dict[str, deque[float]] = {}
        self._first_heard: dict[str, float] = {}
        self._reported_quality: dict[str, float] = {}

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
        payload = self.role.encode("ascii")
        if self._public_key is not None:
            payload += self._public_key  # fixed 32 bytes appended after the role
        pkt = Packet(
            type=PacketType.HELLO,
            priority=Priority.STATUS,
            src=self.node_id,
            dst=BROADCAST_DST,
            ttl=1,  # HELLO is a single-hop shout, never relayed
            payload=payload,
        )
        await self._transport.broadcast(pkt.pack())

    async def _prune_loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(self._prune_interval)
                for node_id in self.neighbours.prune(self._neighbour_timeout):
                    if self.on_peer_down is not None:
                        self.on_peer_down(node_id)
                self._expire_link_history()

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

        # a public key, if present, is always the last PUBLIC_KEY_SIZE bytes
        # (role names top out well under that, so this never misreads a
        # legacy no-key payload as carrying a truncated key)
        public_key: Optional[bytes] = None
        role_bytes = pkt.payload
        if len(pkt.payload) > PUBLIC_KEY_SIZE:
            role_bytes, public_key = pkt.payload[:-PUBLIC_KEY_SIZE], pkt.payload[-PUBLIC_KEY_SIZE:]

        try:
            role = role_bytes.decode("ascii") or NodeRole.NORMAL
        except UnicodeDecodeError:
            role = NodeRole.NORMAL

        is_new = self.neighbours.update(pkt.src, role, public_key=public_key)
        if is_new and self.on_peer_up is not None:
            self.on_peer_up(pkt.src, role)
        # after on_peer_up: that hook resets the link to a default perfect
        # score, which a returning-but-lossy neighbour must then correct
        self._note_hello(pkt.src, fresh_link=is_new)

    # -- link quality (section 8.2) ---------------------------------------------

    def link_quality(self, neighbour_id: str, now: Optional[float] = None) -> Optional[float]:
        """Fraction of the last ``LINK_QUALITY_WINDOW`` expected HELLOs from
        ``neighbour_id`` that actually arrived, in [0, 1]; ``None`` if we
        have never heard from it. While a neighbour is still new, fewer than
        20 HELLOs have been *expected*, so the denominator is however many
        have been due so far -- otherwise every fresh link would look lossy."""
        first = self._first_heard.get(neighbour_id)
        if first is None:
            return None
        now = time.monotonic() if now is None else now
        window_s = LINK_QUALITY_WINDOW * self._hello_interval
        expected = min(LINK_QUALITY_WINDOW, int((now - first) / self._hello_interval) + 1)
        received = sum(1 for t in self._hello_times[neighbour_id] if now - t <= window_s)
        return min(1.0, received / max(1, expected))

    def _note_hello(self, neighbour_id: str, fresh_link: bool = False) -> None:
        now = time.monotonic()
        window_s = LINK_QUALITY_WINDOW * self._hello_interval
        times = self._hello_times.get(neighbour_id)
        if times is not None and now - times[-1] > window_s:
            # silent for longer than the whole window: the old history says
            # nothing about this link any more, so start counting afresh
            del self._hello_times[neighbour_id]
            del self._first_heard[neighbour_id]
            times = None
        if times is None:
            times = self._hello_times[neighbour_id] = deque(maxlen=LINK_QUALITY_WINDOW * 2)
        self._first_heard.setdefault(neighbour_id, now)
        times.append(now)
        if self.on_link_quality is None:
            return
        quality = self.link_quality(neighbour_id, now)
        if quality is None:
            return
        # a link that has just (re)appeared starts from the default 1.0 the
        # routing graph was reset to; otherwise compare against what we last said
        baseline = 1.0 if fresh_link else self._reported_quality.get(neighbour_id, 1.0)
        if abs(quality - baseline) >= LINK_QUALITY_REPORT_DELTA:
            self._reported_quality[neighbour_id] = quality
            self.on_link_quality(neighbour_id, quality)
        elif fresh_link:
            self._reported_quality[neighbour_id] = 1.0

    def _expire_link_history(self) -> None:
        """Bound memory: forget neighbours we haven't heard from in two windows."""
        horizon = 2 * LINK_QUALITY_WINDOW * self._hello_interval
        now = time.monotonic()
        for neighbour_id in [n for n, t in self._hello_times.items() if t and now - t[-1] > horizon]:
            self._forget_link_quality(neighbour_id)

    def _forget_link_quality(self, neighbour_id: str) -> None:
        self._hello_times.pop(neighbour_id, None)
        self._first_heard.pop(neighbour_id, None)
        self._reported_quality.pop(neighbour_id, None)
