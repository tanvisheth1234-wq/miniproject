"""Wires one node's pieces together: discovery finds neighbours, relay
forwards or delivers packets. Spec: docs/project-plan.md section 6.2
("layers inside one node") and section 14 (repo layout lists node.py as
"wires everything together").

Scope note: real multi-hop routing (the graph, Dijkstra, the weighted
cost function) doesn't exist until routing.py lands in Phase 3. Until
then, ``Node`` can only route to peers it has *directly* discovered --
when discovery sees a new neighbour, that neighbour becomes reachable in
one hop automatically; when the neighbour dies, the route is forgotten.
Reaching anything further away correctly drops as "no_route" for now.
This is the seam routing.py is expected to plug into later: it should
feed ``relay.set_next_hop(dst, computed_next_hop)`` the same way
discovery does today, just with a real path instead of a direct link.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .discovery import PRUNE_INTERVAL, Discovery, NodeRole
from .packet import Packet
from .relay import RelayNode
from .transport import Transport


class Node:
    def __init__(
        self,
        node_id: str,
        transport: Transport,
        role: str = NodeRole.NORMAL,
        visible_neighbours: Optional[Iterable[str]] = None,
        hello_interval: float = 3.0,
        neighbour_timeout: float = 10.0,
        prune_interval: float = PRUNE_INTERVAL,
    ) -> None:
        self.node_id = node_id
        self.transport = transport

        self.discovery = Discovery(
            node_id,
            transport,
            role=role,
            visible_neighbours=visible_neighbours,
            hello_interval=hello_interval,
            neighbour_timeout=neighbour_timeout,
            prune_interval=prune_interval,
        )
        self.relay = RelayNode(node_id, transport)

        self.discovery.on_peer_up = self._on_peer_up
        self.discovery.on_peer_down = self._on_peer_down

        # re-exposed so callers (demos, tests, eventually store.py) can
        # observe delivery/forward/drop without reaching into self.relay
        self.on_deliver: Optional[Callable[[Packet], None]] = None
        self.on_forward: Optional[Callable[[Packet, str], None]] = None
        self.on_drop: Optional[Callable[[Packet, str], None]] = None
        self.relay.on_deliver = lambda pkt: self._call(self.on_deliver, pkt)
        self.relay.on_forward = lambda pkt, next_hop: self._call(self.on_forward, pkt, next_hop)
        self.relay.on_drop = lambda pkt, reason: self._call(self.on_drop, pkt, reason)

    async def start(self) -> None:
        await self.transport.start()
        # Discovery.start() and RelayNode.register() each call
        # transport.on_receive() internally -- but Transport only holds one
        # callback slot, so whichever registers last would silently steal
        # all packets from the other. Let both run their own start-up (the
        # HELLO/prune background tasks in discovery's case), then reclaim
        # the slot with our own dispatcher, registered last, so it wins.
        self.relay.register()
        await self.discovery.start()
        self.transport.on_receive(self._on_receive)

    async def stop(self) -> None:
        await self.discovery.stop()
        await self.transport.stop()

    @property
    def neighbours(self):
        return self.discovery.neighbours

    def _on_peer_up(self, peer_id: str, role: str) -> None:
        # a freshly discovered neighbour is reachable in exactly one hop:
        # send straight to them. Multi-hop destinations are routing.py's job.
        self.relay.set_next_hop(peer_id, peer_id)

    def _on_peer_down(self, peer_id: str) -> None:
        self.relay.clear_next_hop(peer_id)

    def _on_receive(self, sender_id: str, data: bytes) -> None:
        # the single dispatch point: each of these already ignores packet
        # types it doesn't own (discovery only acts on HELLO, relay only
        # on DATA/ACK), so simply feeding both is correct, if not the most
        # efficient -- each re-parses the header once. Fine at this scale.
        self.discovery._on_receive(sender_id, data)
        self.relay._on_receive(sender_id, data)

    @staticmethod
    def _call(hook, *args) -> None:
        if hook is not None:
            hook(*args)
