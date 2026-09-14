"""Minimal packet relay: forward DATA/ACK packets not addressed to us.

This is the "receiver task" from docs/project-plan.md section 6.3. It
started (week 2) as a static next-hop table for direct neighbours only;
``route_resolver`` is the seam routing.py's ``Router.next_hop`` now plugs
into for destinations beyond a direct link -- the static table still
wins when both know a route, since a direct link never needs Dijkstra.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Callable, Optional

from .packet import Packet, PacketError, PacketType
from .reliability import DedupSet
from .transport import Transport, TransportError


class RelayNode:
    """Wraps a ``Transport``: delivers packets addressed to us, forwards
    everything else toward a statically configured next hop."""

    def __init__(
        self,
        node_id: str,
        transport: Transport,
        next_hop: Optional[dict[str, str]] = None,
        route_resolver: Optional[Callable[[str], Optional[str]]] = None,
        accepts_dst: Optional[Callable[[str], bool]] = None,
        dedup: Optional[DedupSet] = None,
    ) -> None:
        self.node_id = node_id
        self._transport = transport
        self._next_hop: dict[str, str] = dict(next_hop or {})
        self._route_resolver = route_resolver
        # a packet's dst stays symbolic (e.g. RESCUE__) as it travels --
        # it is never rewritten to the resolved node id -- so a node also
        # needs a way to say "this symbolic destination means me" (section
        # 8.3: any GATEWAY/RESCUE node is a valid RESCUE__ terminal).
        self._accepts_dst = accepts_dst
        # section 9's "Dedup set": in a mesh with more than one path, the
        # same message can arrive here more than once. Without this, a
        # relay would forward every copy, and a multi-path mesh would
        # flood itself (a broadcast storm) instead of converging.
        self._dedup = dedup

        self.on_deliver: Optional[Callable[[Packet], None]] = None
        self.on_forward: Optional[Callable[[Packet, str], None]] = None
        self.on_drop: Optional[Callable[[Packet, str], None]] = None

    def set_next_hop(self, dst_id: str, peer_id: str) -> None:
        """Route messages for ``dst_id`` toward ``peer_id``."""
        self._next_hop[dst_id] = peer_id

    def clear_next_hop(self, dst_id: str) -> None:
        """Forget the route to ``dst_id`` -- e.g. because that neighbour
        just went down. Messages for it will drop as "no_route" until a
        route is learned again."""
        self._next_hop.pop(dst_id, None)

    def register(self) -> None:
        self._transport.on_receive(self._on_receive)

    def _on_receive(self, sender_id: str, data: bytes) -> None:
        try:
            pkt = Packet.unpack(data)
        except PacketError:
            return
        if pkt.type not in (PacketType.DATA, PacketType.ACK):
            return  # HELLO/LINK_STATE belong to discovery.py, not the relay

        if self._dedup is not None and self._dedup.seen_before(pkt.msg_id):
            self._drop(pkt, "duplicate")
            return

        if pkt.dst == self.node_id or (self._accepts_dst is not None and self._accepts_dst(pkt.dst)):
            if self.on_deliver is not None:
                self.on_deliver(pkt)
            return

        self._forward(pkt)

    def _forward(self, pkt: Packet) -> None:
        if pkt.ttl <= 0:
            self._drop(pkt, "ttl_expired")
            return
        if self.node_id in pkt.path:
            self._drop(pkt, "loop_detected")
            return
        next_hop = self._next_hop.get(pkt.dst)
        if next_hop is None and self._route_resolver is not None:
            next_hop = self._route_resolver(pkt.dst)
        if next_hop is None:
            self._drop(pkt, "no_route")
            return

        forwarded = replace(
            pkt,
            ttl=pkt.ttl - 1,
            hop_count=pkt.hop_count + 1,
            path=[*pkt.path, self.node_id],
        )
        if self.on_forward is not None:
            self.on_forward(forwarded, next_hop)
        asyncio.create_task(self._send(next_hop, forwarded))

    async def _send(self, next_hop: str, pkt: Packet) -> None:
        try:
            await self._transport.send(next_hop, pkt.pack())
        except TransportError:
            self._drop(pkt, "send_failed")

    def _drop(self, pkt: Packet, reason: str) -> None:
        if self.on_drop is not None:
            self.on_drop(pkt, reason)
