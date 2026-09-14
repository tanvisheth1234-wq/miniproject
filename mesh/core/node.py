"""Wires one node's pieces together: discovery finds neighbours, routing
builds the mesh graph and computes paths, relay forwards or delivers
packets. Spec: docs/project-plan.md section 6.2 ("layers inside one
node") and section 14 (repo layout lists node.py as "wires everything
together").

Direct neighbours are routed to immediately (one hop, set the moment
discovery sees them) rather than waiting for the first link-state
gossip round; multi-hop destinations resolve through ``routing.Router``,
which ``relay.py`` falls back to via ``route_resolver`` whenever a
destination isn't a direct neighbour.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from .discovery import PRUNE_INTERVAL, Discovery, NodeRole
from .packet import Packet, RESCUE_DST
from .relay import RelayNode
from .routing import LINK_STATE_INTERVAL, LinkStateGossip, MeshGraph, Router
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
        link_state_interval: float = LINK_STATE_INTERVAL,
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

        self.graph = MeshGraph()
        self.router = Router(node_id, self.graph)
        self.gossip = LinkStateGossip(
            node_id, transport, self.graph,
            neighbours_provider=self.discovery.neighbours.ids,
            role_provider=self._role_of,
            interval=link_state_interval,
        )
        self.gossip.on_topology_change = self.router.invalidate
        self.gossip.on_role_learned = self.router.set_role

        self.relay = RelayNode(
            node_id, transport,
            route_resolver=self.router.next_hop,
            accepts_dst=self._is_rescue_terminal,
        )

        self.discovery.on_peer_up = self._on_peer_up
        self.discovery.on_peer_down = self._on_peer_down
        self.router.set_role(node_id, role)

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
        await self.gossip.start()
        self.transport.on_receive(self._on_receive)

    async def stop(self) -> None:
        await self.gossip.stop()
        await self.discovery.stop()
        await self.transport.stop()

    @property
    def neighbours(self):
        return self.discovery.neighbours

    def _role_of(self, neighbour_id: str) -> str:
        """A direct neighbour's advertised role, for inclusion in our own
        outgoing link-state report -- this is how a role propagates
        beyond one hop."""
        info = self.discovery.neighbours.get(neighbour_id)
        return info.role if info is not None else NodeRole.NORMAL

    def _is_rescue_terminal(self, dst: str) -> bool:
        """Section 8.3: a node advertising GATEWAY or RESCUE is a valid
        terminal for RESCUE__, regardless of its own node_id."""
        return dst == RESCUE_DST and self.discovery.role in (NodeRole.GATEWAY, NodeRole.RESCUE)

    def _on_peer_up(self, peer_id: str, role: str) -> None:
        # a freshly discovered neighbour is reachable in exactly one hop:
        # send straight to them, and reflect the direct link into the
        # graph immediately rather than waiting for the first gossip
        # round. Its role is recorded too, so RESCUE__ routing can treat
        # it as a terminal the moment it's discovered.
        self.relay.set_next_hop(peer_id, peer_id)
        self.graph.set_edge(self.node_id, peer_id)
        self.router.set_role(peer_id, role)

    def _on_peer_down(self, peer_id: str) -> None:
        self.relay.clear_next_hop(peer_id)
        self.router.forget_role(peer_id)
        self.gossip.forget_neighbour(peer_id)  # drops the graph edge and invalidates routes

    def _on_receive(self, sender_id: str, data: bytes) -> None:
        # the single dispatch point: each of these already ignores packet
        # types it doesn't own (discovery only acts on HELLO, gossip only
        # on LINK_STATE, relay only on DATA/ACK), so simply feeding all
        # three is correct, if not the most efficient -- each re-parses
        # the header once. Fine at this scale.
        self.discovery._on_receive(sender_id, data)
        self.gossip._on_receive(sender_id, data)
        self.relay._on_receive(sender_id, data)

    @staticmethod
    def _call(hook, *args) -> None:
        if hook is not None:
            hook(*args)
