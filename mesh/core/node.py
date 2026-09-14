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

import asyncio
import contextlib
from dataclasses import replace
from typing import Callable, Iterable, Optional

from . import crypto
from .discovery import PRUNE_INTERVAL, Discovery, NodeRole
from .packet import DEFAULT_TTL, FLAG_ENCRYPTED, FLAG_NEEDS_ACK, Packet, PacketType, Priority, RESCUE_DST
from .relay import RelayNode
from .reliability import ACK_TIMEOUT, AckTracker, DedupSet, MAX_RETRIES, SF_RETRY_INTERVAL, StoreForwardQueue
from .routing import LINK_STATE_INTERVAL, LinkStateGossip, MeshGraph, Router
from .store import Store
from .transport import Transport, TransportError

# section 9: relay.py's drop reasons ("ttl_expired", "loop_detected", ...)
# mapped onto the section 11 event log's kind naming convention
# ("drop_ttl", "drop_dup", ...).
_DROP_EVENT_KIND = {
    "ttl_expired": "drop_ttl",
    "duplicate": "drop_dup",
    "loop_detected": "drop_loop",
    "no_route": "drop_no_route",
    "send_failed": "drop_send_failed",
}


def _safe_text(payload: bytes) -> str:
    """For the store's TEXT body column -- payloads are expected to be
    plain text messages (section 4's examples), but never let a stray
    non-UTF-8 byte crash logging."""
    return payload.decode("utf-8", errors="replace")


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
        ack_timeout: float = ACK_TIMEOUT,
        max_retries: int = MAX_RETRIES,
        ack_poll_interval: float = 0.5,
        sf_retry_interval: float = SF_RETRY_INTERVAL,
        db_path: str = ":memory:",
        session_key: Optional[bytes] = None,
    ) -> None:
        self.node_id = node_id
        self.transport = transport
        self.store = Store(db_path)
        # section 10, Phase 1: every node pre-shares the same AES-256 key
        # out of band. None (the default) means "run unencrypted" -- opt-in,
        # same as dedup/priority-queue elsewhere in this codebase.
        self._session_key = session_key

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
        self.gossip.on_topology_change = self._on_topology_change
        self.gossip.on_role_learned = self.router.set_role

        self.dedup = DedupSet()
        self.relay = RelayNode(
            node_id, transport,
            route_resolver=self.router.next_hop,
            accepts_dst=self._is_rescue_terminal,
            dedup=self.dedup,
        )

        self.discovery.on_peer_up = self._on_peer_up
        self.discovery.on_peer_down = self._on_peer_down
        self.router.set_role(node_id, role)

        self.ack_tracker = AckTracker(timeout_s=ack_timeout, max_retries=max_retries)
        self.store_forward = StoreForwardQueue()
        self._ack_poll_interval = ack_poll_interval
        self._sf_retry_interval = sf_retry_interval
        self._ack_retry_task: Optional[asyncio.Task] = None
        self._sf_flush_task: Optional[asyncio.Task] = None

        # re-exposed so callers (demos, tests, eventually store.py) can
        # observe delivery/forward/drop without reaching into self.relay
        self.on_deliver: Optional[Callable[[Packet], None]] = None
        self.on_forward: Optional[Callable[[Packet, str], None]] = None
        self.on_drop: Optional[Callable[[Packet, str], None]] = None
        self.relay.on_deliver = self._on_relay_deliver
        self.relay.on_forward = self._on_relay_forward
        self.relay.on_drop = self._on_relay_drop

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
        self._ack_retry_task = asyncio.create_task(self._ack_retry_loop())
        self._sf_flush_task = asyncio.create_task(self._sf_flush_loop())

    async def stop(self) -> None:
        for task in (self._ack_retry_task, self._sf_flush_task):
            if task is not None:
                task.cancel()
        for task in (self._ack_retry_task, self._sf_flush_task):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._ack_retry_task = None
        self._sf_flush_task = None
        await self.gossip.stop()
        await self.discovery.stop()
        await self.transport.stop()
        self.store.close()

    @property
    def neighbours(self):
        return self.discovery.neighbours

    def _role_of(self, neighbour_id: str) -> str:
        """A direct neighbour's advertised role, for inclusion in our own
        outgoing link-state report -- this is how a role propagates
        beyond one hop."""
        info = self.discovery.neighbours.get(neighbour_id)
        return info.role if info is not None else NodeRole.NORMAL

    def _on_topology_change(self) -> None:
        self.router.invalidate()
        self.store.record_event("route_change")

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
        self.store.upsert_peer(peer_id, role=role)
        self.store.record_event("peer_up", peer=peer_id)

    def _on_peer_down(self, peer_id: str) -> None:
        self.relay.clear_next_hop(peer_id)
        self.router.forget_role(peer_id)
        self.gossip.forget_neighbour(peer_id)  # drops the graph edge and invalidates routes
        self.store.record_event("peer_down", peer=peer_id)

    # -- originating messages (section 9: ACK + retry, store-and-forward) --------

    async def send(
        self,
        dst: str,
        payload: bytes,
        priority: int = Priority.NORMAL,
        needs_ack: bool = False,
        ttl: int = DEFAULT_TTL,
    ) -> Packet:
        """Originate a new message. Sent immediately if a route to ``dst``
        exists (which may be ``RESCUE__``, resolved by ``routing.Router``);
        otherwise queued in store-and-forward rather than dropped. Returns
        the constructed ``Packet`` (its ``msg_id`` is how callers correlate
        a later ACK or check ``store_forward``/``ack_tracker`` state)."""
        flags = FLAG_NEEDS_ACK if needs_ack else 0
        wire_payload = payload
        if self._session_key is not None:
            wire_payload = crypto.encrypt_payload(self._session_key, payload)
            flags |= FLAG_ENCRYPTED

        pkt = Packet(
            type=PacketType.DATA,
            priority=priority,
            src=self.node_id,
            dst=dst,
            ttl=ttl,
            flags=flags,
            payload=wire_payload,
        )
        self.store.record_message(
            str(pkt.msg_id), src=pkt.src, dst=pkt.dst, priority=pkt.priority,
            direction="sent", status="pending", created_ms=pkt.timestamp,
            body=_safe_text(payload),  # our own plaintext -- we're the src
        )
        await self._dispatch(pkt, track_ack=True)
        return pkt

    async def _dispatch(self, pkt: Packet, track_ack: bool = False) -> bool:
        """Resolve a next hop for ``pkt.dst`` and send it; store-and-forward
        if no route exists or the send itself fails. Returns whether it was
        actually sent."""
        next_hop = self.router.next_hop(pkt.dst)
        if next_hop is None:
            self._queue_for_store_forward(pkt)
            return False
        try:
            await self.transport.send(next_hop, pkt.pack())
        except TransportError:
            self._queue_for_store_forward(pkt)
            return False
        self.store.record_event("sent", msg_id=str(pkt.msg_id), peer=next_hop)
        if track_ack and pkt.needs_ack:
            self.ack_tracker.register(pkt, next_hop)
        elif pkt.type == PacketType.DATA:
            # best-effort send with no ACK requested: nothing left to
            # confirm, so this is as "delivered" as this node can attest to
            self.store.update_message_status(str(pkt.msg_id), "delivered")
        return True

    def _queue_for_store_forward(self, pkt: Packet) -> None:
        self.store_forward.enqueue(pkt)
        if pkt.type == PacketType.DATA:
            self.store.update_message_status(str(pkt.msg_id), "queued_sf")
        self.store.record_event("sf_queue", msg_id=str(pkt.msg_id))

    def _on_relay_deliver(self, pkt: Packet) -> None:
        """A packet addressed to us (or a RESCUE__ we resolve to) just
        arrived. ACKs are this node's own bookkeeping, not a user-visible
        message; a DATA packet asking for one gets one sent back before
        the user callback fires."""
        if pkt.type == PacketType.ACK:
            self.ack_tracker.acknowledge(pkt.msg_id)
            self.store.record_event("ack", msg_id=str(pkt.msg_id))
            self.store.update_message_status(str(pkt.msg_id), "delivered")
            return

        if pkt.encrypted:
            if self._session_key is None:
                self.store.record_event("drop_no_key", msg_id=str(pkt.msg_id))
                return
            try:
                plaintext = crypto.decrypt_payload(self._session_key, pkt.payload)
            except crypto.CryptoError:
                # section 10: GCM's tag catches a relay tampering with the
                # payload -- treat a failed decrypt as exactly that.
                self.store.record_event("drop_decrypt_failed", msg_id=str(pkt.msg_id))
                return
            pkt = replace(pkt, payload=plaintext)

        self.store.record_message(
            str(pkt.msg_id), src=pkt.src, dst=pkt.dst, priority=pkt.priority,
            direction="received", status="delivered",
            hop_count=pkt.hop_count, path=pkt.path,
            body=_safe_text(pkt.payload),  # our own plaintext -- we're the dst
        )
        self.store.record_event("recv", msg_id=str(pkt.msg_id))
        if pkt.needs_ack:
            self._send_ack_for(pkt)
        self._call(self.on_deliver, pkt)

    def _on_relay_forward(self, pkt: Packet, next_hop: str) -> None:
        self.store.record_message(
            str(pkt.msg_id), src=pkt.src, dst=pkt.dst, priority=pkt.priority,
            direction="forwarded", status="delivered",
            hop_count=pkt.hop_count, path=pkt.path,
        )
        self.store.record_event("forward", msg_id=str(pkt.msg_id), peer=next_hop)
        self._call(self.on_forward, pkt, next_hop)

    def _on_relay_drop(self, pkt: Packet, reason: str) -> None:
        kind = _DROP_EVENT_KIND.get(reason, f"drop_{reason}")
        self.store.record_event(kind, msg_id=str(pkt.msg_id), detail=reason)
        self._call(self.on_drop, pkt, reason)

    def _send_ack_for(self, original: Packet) -> None:
        ack = Packet(
            type=PacketType.ACK,
            priority=Priority.STATUS,
            src=self.node_id,
            dst=original.src,
            msg_id=original.msg_id,  # same id: how the sender's AckTracker correlates it
            ttl=DEFAULT_TTL,
        )
        asyncio.create_task(self._dispatch(ack))

    async def _ack_retry_loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(self._ack_poll_interval)
                to_retry, failed = self.ack_tracker.poll_timeouts()
                for entry in to_retry:
                    # route may have changed since the original send
                    # (section 9: "retrying down a path that has since
                    # died" is exactly the failure this recompute avoids)
                    next_hop = self.router.next_hop(entry.pkt.dst)
                    if next_hop is not None:
                        self.store.record_event("retry", msg_id=str(entry.pkt.msg_id), peer=next_hop)
                        asyncio.create_task(self._resend(next_hop, entry.pkt))
                    # else: no route right now -- leave it tracked, it'll
                    # either get a route by the next poll or exhaust its
                    # retries and fall into `failed` below.
                for entry in failed:
                    self._queue_for_store_forward(entry.pkt)

    async def _resend(self, next_hop: str, pkt: Packet) -> None:
        with contextlib.suppress(TransportError):
            await self.transport.send(next_hop, pkt.pack())

    async def _sf_flush_loop(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            while True:
                await asyncio.sleep(self._sf_retry_interval)
                for pkt in self.store_forward.all():
                    next_hop = self.router.next_hop(pkt.dst)
                    if next_hop is None:
                        continue
                    self.store_forward.remove(pkt.msg_id)
                    asyncio.create_task(self._flush_one(next_hop, pkt))

    async def _flush_one(self, next_hop: str, pkt: Packet) -> None:
        try:
            await self.transport.send(next_hop, pkt.pack())
        except TransportError:
            self._queue_for_store_forward(pkt)  # still no reliable path -- try again next round
            return
        self.store.record_event("sf_flush", msg_id=str(pkt.msg_id), peer=next_hop)
        if pkt.needs_ack:
            self.ack_tracker.register(pkt, next_hop)
        else:
            self.store.update_message_status(str(pkt.msg_id), "delivered")

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
