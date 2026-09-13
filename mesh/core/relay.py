"""Minimal packet relay: forward DATA/ACK packets not addressed to us.

This is the "receiver task" from docs/project-plan.md section 6.3, scoped
down for the week 2 milestone ("single-hop relay A->B->C") to a static
next-hop table rather than routing.py's graph -- Dijkstra and the weighted
cost function don't land until week 5. It exists to prove forwarding works
end-to-end before the graph is built on top of it.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Callable, Optional

from .packet import Packet, PacketError, PacketType
from .transport import Transport, TransportError


class RelayNode:
    """Wraps a ``Transport``: delivers packets addressed to us, forwards
    everything else toward a statically configured next hop."""

    def __init__(
        self,
        node_id: str,
        transport: Transport,
        next_hop: Optional[dict[str, str]] = None,
    ) -> None:
        self.node_id = node_id
        self._transport = transport
        self._next_hop: dict[str, str] = dict(next_hop or {})

        self.on_deliver: Optional[Callable[[Packet], None]] = None
        self.on_forward: Optional[Callable[[Packet, str], None]] = None
        self.on_drop: Optional[Callable[[Packet, str], None]] = None

    def set_next_hop(self, dst_id: str, peer_id: str) -> None:
        """Route messages for ``dst_id`` toward ``peer_id``."""
        self._next_hop[dst_id] = peer_id

    def register(self) -> None:
        self._transport.on_receive(self._on_receive)

    def _on_receive(self, sender_id: str, data: bytes) -> None:
        try:
            pkt = Packet.unpack(data)
        except PacketError:
            return
        if pkt.type not in (PacketType.DATA, PacketType.ACK):
            return  # HELLO/LINK_STATE belong to discovery.py, not the relay

        if pkt.dst == self.node_id:
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
