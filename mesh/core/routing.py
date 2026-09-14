"""Mesh-wide routing: link-state graph, weighted cost function, Dijkstra.

Spec: docs/project-plan.md section 8 (Routing). Each node gossips its own
neighbour list (section 8.1); this module merges those reports into a
``MeshGraph`` and computes the cheapest path to any destination over it
(section 8.3), using link quality rather than hop count as the cost
(section 8.2). This is what ``node.py`` plugs into ``relay.py`` in place
of the static next-hop table it uses today.
"""

from __future__ import annotations

import asyncio
import contextlib
import struct
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from .packet import NODE_ID_SIZE, Packet, PacketError, PacketType, Priority
from .transport import Transport, TransportError


# --- Section 8.2 cost function -----------------------------------------------

def edge_cost(link_quality: float, recent_failures: int) -> float:
    """Weight of one directed link, per section 8.2.

    ``link_quality`` is the fraction of the last 20 expected HELLOs that
    actually arrived, in [0, 1] -- 1.0 is a perfect link. ``recent_failures``
    is the count of ACK timeouts attributed to this link in the last 60s.
    Weak or failing links cost more, so Dijkstra prefers reliable links
    over merely short ones.
    """
    if not 0.0 <= link_quality <= 1.0:
        raise ValueError(f"link_quality must be in [0, 1], got {link_quality}")
    if recent_failures < 0:
        raise ValueError(f"recent_failures must be >= 0, got {recent_failures}")
    return 1.0 + (1.0 - link_quality) * 5.0 + recent_failures * 3.0


@dataclass
class EdgeInfo:
    link_quality: float = 1.0
    recent_failures: int = 0

    @property
    def cost(self) -> float:
        return edge_cost(self.link_quality, self.recent_failures)


class MeshGraph:
    """The mesh as a weighted directed graph: vertices are node IDs, edges
    are active links (section 8.1). Built up from link-state reports --
    this class only stores the graph, it doesn't gossip or pathfind."""

    def __init__(self) -> None:
        # adjacency[a][b] = EdgeInfo for the directed edge a -> b
        self._adjacency: dict[str, dict[str, EdgeInfo]] = {}

    def add_node(self, node_id: str) -> None:
        """Ensure ``node_id`` exists in the graph, even with no edges yet."""
        self._adjacency.setdefault(node_id, {})

    def set_edge(
        self,
        a: str,
        b: str,
        link_quality: float = 1.0,
        recent_failures: int = 0,
    ) -> None:
        """Add or update the directed edge a -> b. Link-state reports are
        per-direction (a node reports its own view of a link), so this does
        not automatically add the reverse edge b -> a."""
        self.add_node(a)
        self.add_node(b)
        self._adjacency[a][b] = EdgeInfo(link_quality=link_quality, recent_failures=recent_failures)

    def remove_edge(self, a: str, b: str) -> None:
        if a in self._adjacency:
            self._adjacency[a].pop(b, None)

    def remove_node(self, node_id: str) -> None:
        """Drop ``node_id`` and every edge touching it -- used when a peer
        is declared dead (section 9: heartbeat)."""
        self._adjacency.pop(node_id, None)
        for neighbours in self._adjacency.values():
            neighbours.pop(node_id, None)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._adjacency

    def nodes(self) -> list[str]:
        return list(self._adjacency.keys())

    def neighbours_of(self, node_id: str) -> dict[str, EdgeInfo]:
        """The outgoing edges from ``node_id``, as {neighbour_id: EdgeInfo}."""
        return dict(self._adjacency.get(node_id, {}))

    def edge(self, a: str, b: str) -> EdgeInfo | None:
        return self._adjacency.get(a, {}).get(b)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._adjacency

    def __len__(self) -> int:
        return len(self._adjacency)


# --- Section 8.1 link-state gossip -------------------------------------------

LINK_STATE_INTERVAL = 5.0  # seconds, per section 7.3

_ENTRY_FORMAT = ">8s f B"  # neighbour node id, link_quality (float32), recent_failures
_ENTRY_SIZE = struct.calcsize(_ENTRY_FORMAT)


def _encode_node_id(node_id: str) -> bytes:
    raw = node_id.encode("ascii")
    if len(raw) > NODE_ID_SIZE:
        raise ValueError(f"node id {node_id!r} exceeds {NODE_ID_SIZE} bytes")
    return raw.ljust(NODE_ID_SIZE, b"\x00")


def _decode_node_id(raw: bytes) -> str:
    return raw.rstrip(b"\x00").decode("ascii")


def encode_report(entries: dict[str, EdgeInfo]) -> bytes:
    """Serialise "my neighbours and how good each link is" into a LINK_STATE
    payload: one fixed-size entry per neighbour, concatenated."""
    return b"".join(
        struct.pack(_ENTRY_FORMAT, _encode_node_id(node_id), info.link_quality, min(info.recent_failures, 0xFF))
        for node_id, info in entries.items()
    )


def decode_report(payload: bytes) -> dict[str, EdgeInfo]:
    """Inverse of ``encode_report``. Raises ``ValueError`` on truncated input."""
    if len(payload) % _ENTRY_SIZE != 0:
        raise ValueError(f"link-state payload not a multiple of entry size ({_ENTRY_SIZE})")
    entries: dict[str, EdgeInfo] = {}
    for offset in range(0, len(payload), _ENTRY_SIZE):
        node_id_raw, quality, failures = struct.unpack(
            _ENTRY_FORMAT, payload[offset: offset + _ENTRY_SIZE]
        )
        entries[_decode_node_id(node_id_raw)] = EdgeInfo(link_quality=quality, recent_failures=failures)
    return entries


class LinkStateGossip:
    """Periodically tells neighbours "here's who I can hear and how well",
    and merges everyone else's reports into a shared ``MeshGraph`` (section
    8.1). Sent UDP-unicast per-neighbour, per the transport choice in
    section 7.4 -- not broadcast, since it is neighbour-directed and
    self-correcting on loss.

    Link quality and failure counts aren't tracked by this class -- HELLO
    reception ratio belongs to discovery.py, ACK timeouts belong to
    reliability.py. Both feed this class via ``record_link_quality`` /
    ``record_failure``; until wired up (node.py, later in Phase 3) every
    direct link defaults to a perfect 1.0/0 score.
    """

    def __init__(
        self,
        node_id: str,
        transport: Transport,
        graph: MeshGraph,
        neighbours_provider: Callable[[], Iterable[str]],
        interval: float = LINK_STATE_INTERVAL,
    ) -> None:
        self.node_id = node_id
        self.graph = graph
        self._transport = transport
        self._neighbours_provider = neighbours_provider
        self._interval = interval

        self._own_edges: dict[str, EdgeInfo] = {}
        self.on_topology_change: Optional[Callable[[], None]] = None

        self._task: Optional[asyncio.Task] = None

    # -- link quality / failure feed, called by discovery.py / reliability.py --

    def record_link_quality(self, neighbour_id: str, link_quality: float) -> None:
        info = self._own_edges.setdefault(neighbour_id, EdgeInfo())
        info.link_quality = link_quality

    def record_failure(self, neighbour_id: str) -> None:
        info = self._own_edges.setdefault(neighbour_id, EdgeInfo())
        info.recent_failures += 1

    def forget_neighbour(self, neighbour_id: str) -> None:
        """Neighbour went down (section 9: heartbeat) -- drop it from our
        own report and from the graph."""
        self._own_edges.pop(neighbour_id, None)
        self.graph.remove_node(neighbour_id)
        self._fire_topology_change()

    # -- lifecycle -------------------------------------------------------------

    async def start(self) -> None:
        self._task = asyncio.create_task(self._gossip_loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _gossip_loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await self.send_report()
                await asyncio.sleep(self._interval)

    # -- sending -----------------------------------------------------------------

    def _sync_own_edges(self) -> None:
        """A node always knows its own direct links without waiting for a
        gossip round-trip -- reflect current neighbours straight into the
        graph. Neighbours we no longer have a tracked score for (freshly
        discovered) default to a perfect link."""
        current = set(self._neighbours_provider())
        for neighbour_id in current:
            info = self._own_edges.setdefault(neighbour_id, EdgeInfo())
            self.graph.set_edge(self.node_id, neighbour_id, info.link_quality, info.recent_failures)
        for stale in set(self._own_edges) - current:
            del self._own_edges[stale]
            self.graph.remove_edge(self.node_id, stale)

    async def send_report(self) -> None:
        self._sync_own_edges()
        neighbour_ids = list(self._neighbours_provider())
        payload = encode_report({n: self.graph.edge(self.node_id, n) for n in neighbour_ids})
        for neighbour_id in neighbour_ids:
            pkt = Packet(
                type=PacketType.LINK_STATE,
                priority=Priority.STATUS,
                src=self.node_id,
                dst=neighbour_id,
                ttl=1,  # neighbour-directed, never relayed
                payload=payload,
            )
            try:
                await self._transport.send(neighbour_id, pkt.pack())
            except TransportError:
                pass  # loss is tolerable for link-state; section 7.4

    # -- receiving -----------------------------------------------------------------

    def _on_receive(self, sender_id: str, data: bytes) -> None:
        try:
            pkt = Packet.unpack(data)
        except PacketError:
            return
        if pkt.type != PacketType.LINK_STATE:
            return  # not this component's concern

        try:
            entries = decode_report(pkt.payload)
        except ValueError:
            return

        changed = False
        for neighbour_id, info in entries.items():
            existing = self.graph.edge(sender_id, neighbour_id)
            if existing is None or existing.link_quality != info.link_quality or existing.recent_failures != info.recent_failures:
                changed = True
            self.graph.set_edge(sender_id, neighbour_id, info.link_quality, info.recent_failures)

        if changed:
            self._fire_topology_change()

    def _fire_topology_change(self) -> None:
        if self.on_topology_change is not None:
            self.on_topology_change()
