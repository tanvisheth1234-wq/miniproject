"""The mesh lab: many real ``Node`` objects in one process, wired together
over the simulator's in-memory radio.

Nothing here reimplements the protocol. Every node is the same ``Node``
class a laptop would run -- discovery, link-state gossip, Dijkstra, ACK and
retry, store-and-forward, AES-GCM, Ed25519, SQLite logging -- and only the
transport underneath is swapped for ``SimulatedTransport`` (section 6.1's
whole point). The lab adds what a single process needs on top: switching
nodes off and on, editing links, a global event feed for the UI, and
whole-mesh views that a real node could never have (it can see every node's
log; a real node sees only its own).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Optional

from mesh.core import crypto
from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import RESCUE_DST, Priority
from mesh.core.routing import Router
from mesh.core.store import Store
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport

from . import views
from .events import EventBus
from .metrics import compute_metrics, receive_times
from .presets import LATENCY_MS, LinkSpec, NodeSpec, Preset, build_preset
from .radio import RadioConfig, RadioTransport

MAX_PAYLOAD = 400  # bytes of message text; plenty for "4 of us in room 302"


class LabError(Exception):
    """A request the lab can't honour (unknown node, node is down, ...).
    The server maps it to a 4xx."""


@dataclass(frozen=True)
class Timing:
    hello_interval: float = 0.8
    neighbour_timeout: float = 3.0
    prune_interval: float = 0.5
    link_state_interval: float = 1.5
    ack_timeout: float = 2.5
    max_retries: int = 3
    ack_poll_interval: float = 0.25
    sf_retry_interval: float = 1.5


# for tests: everything fast enough to converge in a fraction of a second
FAST = Timing(
    hello_interval=0.05, neighbour_timeout=0.4, prune_interval=0.05, link_state_interval=0.08,
    ack_timeout=0.4, max_retries=3, ack_poll_interval=0.03, sf_retry_interval=0.15,
)
# the live lab: the spec's shape, compressed ~4x so a demo fits on a stage
LIVE = Timing()
# section 7.3's constants exactly as written -- for the virtual-time simulator
SPEC = Timing(
    hello_interval=3.0, neighbour_timeout=10.0, prune_interval=1.0,
    link_state_interval=5.0, ack_timeout=4.0, max_retries=3,
    ack_poll_interval=0.5, sf_retry_interval=10.0,
)


class PersistentStore(Store):
    """A node's log that survives the node being switched off.

    ``Node.stop()`` closes its store. A real phone's log is on disk and is
    still there after a crash; here it's in memory, so ``close()`` is a no-op
    and the lab hands the same object to the node's next incarnation. Every
    event is also reported to a listener -- that's how the UI's live feed
    works without touching the engine."""

    def __init__(self, node_id: str, listener) -> None:
        super().__init__(":memory:")
        self.node_id = node_id
        self._listener = listener

    def close(self) -> None:  # called by Node.stop()
        pass

    def shutdown(self) -> None:
        super().close()

    def record_event(self, kind, msg_id=None, peer=None, detail=None, ts_ms=None) -> int:
        ts_ms = ts_ms if ts_ms is not None else int(time.time() * 1000)
        row_id = super().record_event(kind, msg_id=msg_id, peer=peer, detail=detail, ts_ms=ts_ms)
        if self._listener is not None:
            self._listener(self.node_id, {"id": row_id, "ts_ms": ts_ms, "kind": kind, "msg_id": msg_id,
                                          "peer": peer, "detail": detail})
        return row_id


class MeshLab:
    def __init__(self, bus: Optional[EventBus] = None, timing: Timing = LIVE) -> None:
        self.bus = bus
        self.timing = timing
        self.preset_id = "demo5"
        self.preset_title = ""
        self.sender = ""
        self.encryption = False
        self.signing = False
        self.routing = "weighted"
        self.seed: Optional[int] = None
        self.radio = RadioConfig()

        self.network = SimulatedNetwork()
        self.specs: dict[str, NodeSpec] = {}
        self.links: dict[tuple[str, str], LinkSpec] = {}
        self.nodes: dict[str, Node] = {}  # running nodes only
        self.stores: dict[str, PersistentStore] = {}  # every node ever created, even switched-off ones
        self.recent_events: deque[dict] = deque(maxlen=600)
        self.actions: deque[dict] = deque(maxlen=200)
        self.wire: dict[str, dict] = {}  # msg_id -> what a relay saw on the wire
        self.started_at = time.time()
        self._session_key: Optional[bytes] = None
        self._keypairs: dict[str, crypto.KeyPair] = {}
        self._lock = asyncio.Lock()
        self._restore_radio: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------ lifecycle

    async def load(
        self,
        preset_id: str = "demo5",
        *,
        preset: Optional[Preset] = None,
        encryption: bool = False,
        signing: bool = False,
        routing: str = "weighted",
        radio_service_ms: float = 0.0,
        seed: Optional[int] = None,
    ) -> None:
        """(Re)build the whole mesh from a preset and start every node."""
        async with self._lock:
            await self._teardown()
            if routing not in ("weighted", "hopcount"):
                raise LabError("routing must be 'weighted' or 'hopcount'")
            try:
                preset = preset or build_preset(preset_id)
            except KeyError as exc:
                raise LabError(f"unknown preset {preset_id!r}") from exc

            self.preset_id = preset.id
            self.preset_title = preset.title
            self.sender = preset.sender
            self.encryption = encryption
            self.signing = signing
            self.routing = routing
            self.seed = seed
            self.radio = RadioConfig(service_ms=radio_service_ms)
            self.network = SimulatedNetwork(seed=seed)
            self.specs = {n.node_id: n for n in preset.nodes}
            self.links = {l.key: l for l in preset.links}
            self.recent_events.clear()
            self.wire.clear()
            self.stores.clear()
            self._session_key = crypto.generate_session_key() if encryption else None
            self._keypairs = {nid: crypto.generate_keypair() for nid in self.specs} if signing else {}
            self.started_at = time.time()

            for link in self.links.values():
                self.network.set_link(link.a, link.b, loss=link.loss, latency_ms=link.latency_ms)
            await asyncio.gather(*(self._spawn(nid) for nid in self.specs))
            self._notify("reset", f"Loaded “{preset.title}”: {len(self.specs)} nodes, {len(self.links)} links")

    async def shutdown(self) -> None:
        async with self._lock:
            await self._teardown()

    async def _teardown(self) -> None:
        if self._restore_radio is not None:
            self._restore_radio.cancel()
            self._restore_radio = None
        for node in list(self.nodes.values()):
            with contextlib.suppress(Exception):
                await node.stop()
        self.nodes.clear()
        for store in self.stores.values():
            with contextlib.suppress(Exception):
                store.shutdown()
        self.stores.clear()

    async def _spawn(self, node_id: str) -> Node:
        spec = self.specs[node_id]
        t = self.timing
        transport = RadioTransport(SimulatedTransport(node_id, self.network), self.network, self.radio)
        node = Node(
            node_id, transport, role=spec.role,
            hello_interval=t.hello_interval, neighbour_timeout=t.neighbour_timeout,
            prune_interval=t.prune_interval, link_state_interval=t.link_state_interval,
            ack_timeout=t.ack_timeout, max_retries=t.max_retries,
            ack_poll_interval=t.ack_poll_interval, sf_retry_interval=t.sf_retry_interval,
            session_key=self._session_key, keypair=self._keypairs.get(node_id),
            hop_count_routing=(self.routing == "hopcount"),
        )
        store = self.stores.get(node_id)
        if store is None:
            store = PersistentStore(node_id, self._on_store_event)
            self.stores[node_id] = store
        node.store.close()  # the throwaway in-memory store Node made for itself
        node.store = store
        node.on_forward = self._on_forward
        await node.start()
        self.nodes[node_id] = node
        return node

    # ------------------------------------------------------------------ event feed

    def _on_store_event(self, node_id: str, event: dict) -> None:
        event = {**event, "node": node_id}
        store = self.stores.get(node_id)
        if store is not None and event["msg_id"]:
            row = store.get_message(event["msg_id"])
            if row is not None:
                event.update(priority=row["priority"], src=row["src"], dst=row["dst"])
        self.recent_events.append(event)
        if self.bus is not None:
            self.bus.publish({"type": "event", **event})

    def _on_forward(self, pkt, next_hop: str) -> None:
        # what a relay actually handled: the header in the clear, the payload
        # as ciphertext when encryption is on -- the proof it can't read it
        self.wire.setdefault(str(pkt.msg_id), {
            "encrypted": pkt.encrypted,
            "signed": pkt.signed,
            "payload_len": len(pkt.payload),
            "payload_hex": pkt.payload[:40].hex(),
        })

    def _notify(self, kind: str, text: str, **data: Any) -> None:
        entry = {"ts_ms": int(time.time() * 1000), "kind": kind, "text": text, **data}
        self.actions.append(entry)
        if self.bus is not None:
            self.bus.publish({"type": "lab", **entry})

    # ------------------------------------------------------------------ operator controls

    def _require_spec(self, node_id: str) -> NodeSpec:
        spec = self.specs.get(node_id)
        if spec is None:
            raise LabError(f"unknown node {node_id!r}")
        return spec

    def is_online(self, node_id: str) -> bool:
        return node_id in self.nodes

    async def kill(self, node_id: str) -> None:
        async with self._lock:
            self._require_spec(node_id)
            node = self.nodes.pop(node_id, None)
            if node is None:
                return
            await node.stop()
            # the retention queue and pending-ACK table are in memory: a crash
            # loses them, so anything still in flight from here is gone
            store = self.stores[node_id]
            for status in ("pending", "queued_sf"):
                for row in store.messages_by_status(status):
                    if row["direction"] == "sent":
                        store.update_message_status(row["msg_id"], "failed")
                        store.record_event("lost_on_crash", msg_id=row["msg_id"], detail="node switched off")
            self._notify("kill", f"{node_id} switched off", node=node_id)

    async def revive(self, node_id: str) -> None:
        async with self._lock:
            self._require_spec(node_id)
            if node_id in self.nodes:
                return
            await self._spawn(node_id)
            self._notify("revive", f"{node_id} switched back on", node=node_id)

    async def set_link(self, a: str, b: str, loss: float = 0.0, latency_ms: tuple[float, float] = LATENCY_MS) -> dict:
        self._require_spec(a)
        self._require_spec(b)
        if a == b:
            raise LabError("a node can't link to itself")
        if not 0.0 <= loss <= 1.0:
            raise LabError("loss must be between 0 and 1")
        lo, hi = latency_ms
        if lo < 0 or hi < lo:
            raise LabError("latency range must satisfy 0 <= min <= max")
        link = LinkSpec(a, b, loss=loss, latency_ms=(lo, hi))
        existed = link.key in self.links
        self.links[link.key] = link
        self.network.set_link(a, b, loss=loss, latency_ms=(lo, hi))
        verb = "retuned" if existed else "created"
        self._notify("link", f"Link {a} ⇄ {b} {verb} (loss {loss:.0%})", a=a, b=b)
        return link.to_dict()

    async def remove_link(self, a: str, b: str) -> None:
        link = LinkSpec(a, b)
        if link.key not in self.links:
            raise LabError(f"no link between {a!r} and {b!r}")
        del self.links[link.key]
        self.network.remove_link(a, b)
        self._notify("link", f"Link {a} ⇄ {b} cut", a=a, b=b)

    async def add_node(self, node_id: str, role: str = NodeRole.NORMAL, label: str = "",
                       x: float = 0.5, y: float = 0.5, links: Optional[list[str]] = None) -> dict:
        async with self._lock:
            if not node_id or len(node_id) > 8 or not node_id.isascii() or not node_id.isalnum():
                raise LabError("node id must be 1-8 letters or digits")
            if node_id in self.specs:
                raise LabError(f"node {node_id!r} already exists")
            if role not in NodeRole.ALL:
                raise LabError(f"role must be one of {', '.join(NodeRole.ALL)}")
            for other in links or []:
                self._require_spec(other)
            spec = NodeSpec(node_id, role, label or ("Survivor" if role == NodeRole.NORMAL else role.title()), x, y)
            self.specs[node_id] = spec
            if self.signing:
                self._keypairs[node_id] = crypto.generate_keypair()
            for other in links or []:
                link = LinkSpec(node_id, other)
                self.links[link.key] = link
                self.network.set_link(node_id, other, loss=link.loss, latency_ms=link.latency_ms)
            await self._spawn(node_id)
            self._notify("add_node", f"{node_id} ({role}) joined with {len(links or [])} link(s)", node=node_id)
            return spec.to_dict()

    def configure(self, radio_service_ms: Optional[float] = None) -> None:
        if radio_service_ms is not None:
            if radio_service_ms < 0 or radio_service_ms > 2000:
                raise LabError("radio_service_ms must be between 0 and 2000")
            self.radio.service_ms = radio_service_ms
            self._notify("config", f"Radio capacity: {'unlimited' if radio_service_ms == 0 else f'one packet per {radio_service_ms:.0f} ms'}")

    # ------------------------------------------------------------------ sending

    async def send(self, src: str, dst: str, text: str, priority: int = Priority.NORMAL,
                   needs_ack: bool = True) -> dict:
        node = self._online(src)
        text = (text or "").strip()
        if not text:
            raise LabError("message text is empty")
        payload = text.encode("utf-8")
        if len(payload) > MAX_PAYLOAD:
            raise LabError(f"message too long ({len(payload)} bytes, max {MAX_PAYLOAD})")
        if priority not in (Priority.SOS, Priority.NORMAL, Priority.STATUS):
            raise LabError("priority must be 0 (SOS), 1 (NORMAL) or 2 (STATUS)")
        if dst != RESCUE_DST:
            self._require_spec(dst)
            if dst == src:
                raise LabError("can't send a message to yourself")
        pkt = await node.send(dst, payload, priority=priority, needs_ack=needs_ack)
        return {"msg_id": str(pkt.msg_id), "src": src, "dst": dst, "priority": priority,
                "priority_name": views.PRIORITY_NAMES[priority], "created_ms": pkt.timestamp}

    async def sos(self, src: str, text: Optional[str] = None) -> dict:
        label = self.specs[src].label if src in self.specs else src
        return await self.send(src, RESCUE_DST, text or f"SOS from {src} ({label}) — need rescue", Priority.SOS)

    async def burst(self, src: str, dst: str = RESCUE_DST, normal: int = 6, service_ms: float = 150.0) -> dict:
        """Section 9.1's demonstration: pile up ordinary traffic behind a
        slow radio, then raise an SOS *after* it. The SOS should still land
        first because every hop's queue picks priority before arrival order."""
        self._online(src)
        normal = max(1, min(int(normal), 20))
        if self.radio.service_ms < service_ms:
            self.radio.service_ms = service_ms
            self._notify("config", f"Radio capacity throttled to one packet per {service_ms:.0f} ms for the priority test")
        if self._restore_radio is not None:
            self._restore_radio.cancel()
        previous = 0.0
        self._restore_radio = asyncio.create_task(self._restore_after(previous, 12.0 + normal * service_ms / 400.0))

        tasks = [self.send(src, dst, f"routine update {i + 1}", Priority.NORMAL) for i in range(normal)]
        tasks.append(self.sos(src, f"SOS from {src} — sent AFTER {normal} routine messages"))
        results = await asyncio.gather(*tasks)
        self._notify("burst", f"{src} queued {normal} routine messages then 1 SOS", node=src)
        return {"normal": [r["msg_id"] for r in results[:-1]], "sos": results[-1]["msg_id"]}

    async def _restore_after(self, service_ms: float, delay: float) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(delay)
            self.radio.service_ms = service_ms
            self._notify("config", "Radio capacity restored to unlimited")

    def _online(self, node_id: str) -> Node:
        self._require_spec(node_id)
        node = self.nodes.get(node_id)
        if node is None:
            raise LabError(f"{node_id} is switched off")
        return node

    # ------------------------------------------------------------------ views

    def snapshot(self) -> dict:
        nodes = []
        for nid, spec in self.specs.items():
            node = self.nodes.get(nid)
            store = self.stores.get(nid)
            entry = {**spec.to_dict(), "online": node is not None}
            if node is not None:
                entry.update(
                    neighbours=sorted(node.neighbours.ids()),
                    known_nodes=len(node.graph.reachable_from(node.node_id)),
                    store_forward=len(node.store_forward),
                    pending_acks=len(node.ack_tracker),
                    dedup=len(node.dedup),
                )
            else:
                entry.update(neighbours=[], known_nodes=0, store_forward=0, pending_acks=0, dedup=0)
            if store is not None:
                entry.update(
                    sent=store.count_messages(direction="sent"),
                    received=store.count_messages(direction="received"),
                    forwarded=store.count_events("forward"),
                )
            nodes.append(entry)

        links = []
        for link in self.links.values():
            qualities = []
            for x, y in ((link.a, link.b), (link.b, link.a)):
                node = self.nodes.get(x)
                edge = node.graph.edge(x, y) if node is not None else None
                if edge is not None:
                    qualities.append(edge.link_quality)
            links.append({
                **link.to_dict(),
                "up": link.a in self.nodes and link.b in self.nodes,
                "quality": round(min(qualities), 3) if qualities else None,
            })

        return {
            "config": {
                "preset": self.preset_id, "title": self.preset_title, "sender": self.sender,
                "encryption": self.encryption, "signing": self.signing, "routing": self.routing,
                "radio_service_ms": self.radio.service_ms, "seed": self.seed,
                "timing": {"hello_interval": self.timing.hello_interval,
                           "neighbour_timeout": self.timing.neighbour_timeout,
                           "link_state_interval": self.timing.link_state_interval,
                           "ack_timeout": self.timing.ack_timeout, "max_retries": self.timing.max_retries},
            },
            "uptime_s": round(time.time() - self.started_at, 1),
            "nodes": nodes,
            "links": links,
            "stats": self.live_stats(),
        }

    def live_stats(self) -> dict:
        """The stat strip: cheap enough to recompute on every snapshot."""
        metrics = compute_metrics(self.stores)
        sf = sum(len(n.store_forward) for n in self.nodes.values())
        return {
            "sent": metrics["sent"],
            "delivered": metrics["delivered"],
            "delivery_ratio": metrics["delivery_ratio"],
            "mean_hops": metrics["mean_hops"],
            "nodes_online": len(self.nodes),
            "nodes_total": len(self.specs),
            "queued_in_store_forward": sf,
            "retries": metrics["retries"],
            "sos_sent": metrics["by_priority"]["SOS"]["sent"],
            "sos_delivered": metrics["by_priority"]["SOS"]["delivered"],
        }

    def metrics(self) -> dict:
        return compute_metrics(self.stores)

    def node_view(self, node_id: str) -> dict:
        spec = self._require_spec(node_id)
        node = self.nodes.get(node_id)
        view = (views.offline_node_view(node_id, spec.role, self.stores[node_id], spec.label) if node is None
                else views.node_view(node, spec.label))
        # a sender only learns the route from the ACK that came back; the lab
        # can see what the destination really recorded, so show that
        _sent, received = self._sent_and_received()
        for m in view["thread"]:
            if m["direction"] == "sent" and m["msg_id"] in received:
                m["relays"] = views.split_path(received[m["msg_id"]][1]["path"])
                m["hop_count"] = len(m["relays"])
                m["received_by"] = received[m["msg_id"]][0]
        return view

    def terminals(self) -> list[str]:
        return [nid for nid, spec in self.specs.items() if views.role_is_terminal(spec.role)]

    def _sent_and_received(self) -> tuple[dict[str, tuple[str, dict]], dict[str, tuple[str, dict]]]:
        sent: dict[str, tuple[str, dict]] = {}
        received: dict[str, tuple[str, dict]] = {}
        for nid, store in self.stores.items():
            for row in store.list_messages(direction="sent"):
                sent[row["msg_id"]] = (nid, row)
            for row in store.list_messages(direction="received"):
                received.setdefault(row["msg_id"], (nid, row))
        return sent, received

    def rescue_view(self, limit: int = 120) -> dict:
        """What the rescue coordinators see: SOS queue, delivery log, stats."""
        sent, received = self._sent_and_received()
        recv_ms = receive_times(self.stores)
        now = int(time.time() * 1000)

        def route_of(mid: str, row: dict) -> tuple[list[str], Optional[str]]:
            if mid in received:
                rnode, rrow = received[mid]
                return [row["src"], *views.split_path(rrow["path"]), rnode], rnode
            return [row["src"], *views.split_path(row["path"])], None

        queue, unreached = [], []
        for mid, (src, row) in sent.items():
            if row["priority"] != Priority.SOS:
                continue
            route, rnode = route_of(mid, row)
            item = {
                "msg_id": mid, "sender": row["src"], "body": row["body"], "created_ms": row["created_ms"],
                "age_s": round((now - row["created_ms"]) / 1000.0, 1), "route": route, "hops": len(route) - 2 if rnode else None,
                "received_by": rnode, "status": row["status"],
                "latency_ms": (recv_ms[mid] - row["created_ms"]) if mid in recv_ms else None,
            }
            (queue if rnode else unreached).append(item)
        # urgency first (all SOS here), then the longest-waiting on top
        queue.sort(key=lambda m: -m["age_s"])
        unreached.sort(key=lambda m: -m["age_s"])

        log = []
        for mid, (src, row) in sent.items():
            route, rnode = route_of(mid, row)
            log.append({
                "msg_id": mid, "src": row["src"], "dst": row["dst"], "priority": row["priority"],
                "priority_name": views.PRIORITY_NAMES.get(row["priority"], "?"),
                "route": route, "hops": len(route) - 2 if rnode else None, "received_by": rnode,
                "status": row["status"], "created_ms": row["created_ms"],
                "outcome": "delivered" if rnode else {"pending": "in flight", "queued_sf": "held in store-and-forward",
                                                      "failed": "failed"}.get(row["status"], row["status"]),
                "latency_ms": (recv_ms[mid] - row["created_ms"]) if mid in recv_ms else None,
                "body": row["body"],
            })
        log.sort(key=lambda m: -m["created_ms"])
        return {
            "terminals": self.terminals(),
            "sos_queue": queue[:limit],
            "unreached_sos": unreached[:limit],
            "delivery_log": log[:limit],
            "stats": self.live_stats(),
        }

    def message_detail(self, msg_id: str) -> dict:
        """One message's whole story, stitched together from every node's log."""
        records, events = [], []
        for nid, store in self.stores.items():
            row = store.get_message(msg_id)
            if row is not None:
                records.append({"node": nid, **views.message_view(row)})
            for ev in store.events_for_message(msg_id):
                events.append({"node": nid, **ev})
        if not records:
            raise LabError(f"unknown message {msg_id!r}")
        events.sort(key=lambda e: (e["ts_ms"], e["id"]))
        origin = next((r for r in records if r["direction"] == "sent"), records[0])
        arrived = next((r for r in records if r["direction"] == "received"), None)
        route = [origin["src"], *(arrived["relays"] if arrived else origin["relays"])]
        if arrived:
            route.append(arrived["node"])
        t0 = origin["created_ms"]
        for ev in events:
            ev["t_ms"] = ev["ts_ms"] - t0
        received_at = receive_times(self.stores).get(msg_id) if arrived else None
        return {
            "msg_id": msg_id, "origin": origin, "arrived": arrived, "route": route,
            "hops": (len(route) - 2) if arrived else None, "events": events,
            "wire": self.wire.get(msg_id),
            "latency_ms": (received_at - t0) if received_at is not None else None,
        }

    def graph_view(self, node_id: str) -> dict:
        """The mesh as ``node_id`` believes it to be, edge costs included."""
        node = self._online(node_id)
        known = node.graph.reachable_from(node_id)
        edges = []
        for a in sorted(known):
            for b, edge in node.graph.neighbours_of(a).items():
                if b in known:
                    edges.append({"from": a, "to": b, "link_quality": round(edge.link_quality, 3),
                                  "recent_failures": edge.recent_failures, "cost": round(edge.cost, 3)})
        return {
            "viewer": node_id,
            "nodes": [{"id": n, "role": node.router.role_of(n)} for n in sorted(known)],
            "edges": edges,
        }

    def route_compare(self, src: str, dst: str) -> dict:
        """Weighted Dijkstra vs plain hop-count over the same learned graph:
        the comparison section 8.2 calls the strongest claim in the project."""
        node = self._online(src)
        if dst != RESCUE_DST:
            self._require_spec(dst)
        weighted = views.route_view(node.router, node.graph, dst)
        flat = Router(src, node.graph, cost_fn=lambda _e: 1.0)
        for n in node.graph.nodes():
            flat.set_role(n, node.router.role_of(n))
        hop = views.route_view(flat, node.graph, dst)
        if hop is not None:
            # price the hop-count path with the real cost function: what it actually costs to use
            hop["weighted_cost"] = round(sum(e["cost"] for e in hop["edges"]), 3)
        return {"src": src, "dst": dst, "weighted": weighted, "hop_count": hop,
                "same_path": bool(weighted and hop and weighted["path"] == hop["path"])}
