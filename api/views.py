"""JSON-ready views over one running ``Node`` and its ``Store``.

Everything the UI shows about a single node comes from here, and every
value is read from the real engine objects -- ``node.neighbours`` for
who's nearby, ``node.router`` for hop distance, ``node.store`` for history,
``node.store_forward`` / ``node.ack_tracker`` / ``node.dedup`` for the
reliability machinery. Nothing is invented for the UI. The lab (many nodes)
and the single-node server both build on these.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import RESCUE_DST
from mesh.core.routing import MeshGraph, Router
from mesh.core.store import Store

PRIORITY_NAMES = {0: "SOS", 1: "NORMAL", 2: "STATUS"}


def now_ms() -> int:
    return int(time.time() * 1000)


def split_path(path: Optional[str]) -> list[str]:
    return [p for p in (path or "").split(",") if p]


def message_view(row: dict[str, Any]) -> dict[str, Any]:
    """A ``messages`` row as the UI wants it: route split into a list and
    the numeric priority given its name."""
    return {
        "msg_id": row["msg_id"],
        "src": row["src"],
        "dst": row["dst"],
        "priority": row["priority"],
        "priority_name": PRIORITY_NAMES.get(row["priority"], str(row["priority"])),
        "direction": row["direction"],
        "status": row["status"],
        "body": row["body"],
        "created_ms": row["created_ms"],
        "resolved_ms": row["resolved_ms"],
        "hop_count": row["hop_count"],
        "relays": split_path(row["path"]),
    }


def thread_view(store: Store, limit: int = 60) -> list[dict[str, Any]]:
    """Messages this node sent or received (not the ones it merely relayed),
    oldest first, for the conversation thread."""
    rows = [r for r in store.list_messages(limit=limit * 3) if r["direction"] in ("sent", "received")]
    rows = rows[:limit]
    rows.reverse()
    return [message_view(r) for r in rows]


def edge_view(graph: MeshGraph, a: str, b: str) -> Optional[dict[str, Any]]:
    edge = graph.edge(a, b)
    if edge is None:
        return None
    return {
        "from": a,
        "to": b,
        "link_quality": round(edge.link_quality, 3),
        "recent_failures": edge.recent_failures,
        "cost": round(edge.cost, 3),
    }


def route_view(router: Router, graph: MeshGraph, dst: str) -> Optional[dict[str, Any]]:
    """The cheapest path to ``dst`` with the cost of every hop spelled out."""
    path = router.shortest_path(dst)
    if path is None:
        return None
    edges = [e for e in (edge_view(graph, a, b) for a, b in zip(path, path[1:])) if e]
    return {
        "dst": dst,
        "resolved": path[-1],
        "path": path,
        "hops": len(path) - 1,
        "edges": edges,
        "cost": round(sum(e["cost"] for e in edges), 3),
    }


def peers_view(node: Node) -> list[dict[str, Any]]:
    """Every node this one can currently reach, nearest first. ``hops`` is
    the length of the cheapest path through the link-state graph, so a peer
    two radios away shows 2 even though it was never heard directly."""
    peers = []
    for other in node.graph.nodes():
        if other == node.node_id:
            continue
        path = node.router.shortest_path(other)
        if path is None:
            continue
        peers.append(
            {
                "id": other,
                "role": node.router.role_of(other),
                "hops": len(path) - 1,
                "path": path,
                "direct": other in node.neighbours,
            }
        )
    peers.sort(key=lambda p: (p["hops"], p["id"]))
    return peers


def neighbours_view(node: Node) -> list[dict[str, Any]]:
    out = []
    for nid, info in sorted(node.neighbours.snapshot().items()):
        quality = node.discovery.link_quality(nid)
        out.append(
            {
                "id": nid,
                "role": info.role,
                "last_seen_ms": info.last_seen_ms,
                "link_quality": None if quality is None else round(quality, 3),
                "has_public_key": info.public_key is not None,
            }
        )
    return out


def queues_view(node: Node) -> dict[str, Any]:
    """The reliability machinery's live state: what store-and-forward is
    holding, what's awaiting an ACK, how big the dedup set is."""
    t = now_ms()
    retained = [
        {
            "msg_id": str(p.msg_id),
            "dst": p.dst,
            "priority": p.priority,
            "priority_name": PRIORITY_NAMES.get(p.priority, str(p.priority)),
            "age_s": round(max(0, t - p.timestamp) / 1000.0, 1),
        }
        for p in node.store_forward.all()
    ]
    retained.sort(key=lambda m: (m["priority"], -m["age_s"]))
    pending = [
        {
            "msg_id": str(entry.pkt.msg_id),
            "dst": entry.pkt.dst,
            "next_hop": entry.next_hop,
            "attempts": entry.attempts,
            "age_s": round(max(0, t - entry.sent_at_ms) / 1000.0, 1),
        }
        for entry in node.ack_tracker._pending.values()
    ]
    return {
        "store_forward": retained,
        "store_forward_limit": node.store_forward.max_count,
        "pending_acks": pending,
        "max_retries": node.ack_tracker._max_retries,
        "ack_timeout_s": node.ack_tracker._timeout_ms / 1000.0,
        "dedup_size": len(node.dedup),
    }


def counters_view(store: Store) -> dict[str, int]:
    kinds = ["sent", "recv", "forward", "ack", "retry", "sf_queue", "sf_flush", "peer_up", "peer_down", "route_change"]
    out = {k: store.count_events(k) for k in kinds}
    out["drops"] = sum(
        store.count_events(k)
        for k in ("drop_ttl", "drop_dup", "drop_loop", "drop_no_route", "drop_send_failed",
                  "drop_decrypt_failed", "drop_signature_invalid", "drop_unknown_signer", "drop_no_key")
    )
    out["drop_dup"] = store.count_events("drop_dup")
    return out


def node_view(node: Node, label: Optional[str] = None) -> dict[str, Any]:
    """The whole NODE VIEW payload for one running node."""
    rescue = route_view(node.router, node.graph, RESCUE_DST)
    return {
        "id": node.node_id,
        "label": label or node.node_id,
        "role": node.discovery.role,
        "online": True,
        "nearby": len(node.neighbours),
        "neighbours": neighbours_view(node),
        "reachable": peers_view(node),
        "rescue_route": rescue,
        "thread": thread_view(node.store),
        "queues": queues_view(node),
        "counters": counters_view(node.store),
        "security": {"encryption": node._session_key is not None, "signing": node._keypair is not None},
    }


def offline_node_view(node_id: str, role: str, store: Store, label: Optional[str] = None) -> dict[str, Any]:
    """A node that's switched off still has its history -- the log is on
    disk -- but it hears nobody and reaches nobody."""
    return {
        "id": node_id,
        "label": label or node_id,
        "role": role,
        "online": False,
        "nearby": 0,
        "neighbours": [],
        "reachable": [],
        "rescue_route": None,
        "thread": thread_view(store),
        "queues": {"store_forward": [], "store_forward_limit": 0, "pending_acks": [], "max_retries": 0,
                   "ack_timeout_s": 0, "dedup_size": 0},
        "counters": counters_view(store),
        "security": {"encryption": False, "signing": False},
    }


def role_is_terminal(role: str) -> bool:
    return role in (NodeRole.GATEWAY, NodeRole.RESCUE)
