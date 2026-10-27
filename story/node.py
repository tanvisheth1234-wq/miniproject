"""Run ONE EcoMesh device (one process, one laptop) over real sockets.

    python -m story.node --id L1 --config story/mesh.json

Each device runs the real ``Node`` engine, listens on its own TCP port for
packets from its configured neighbours, and serves a small web page (its
own screen) on its web port. Open that page on the laptop itself or on a
phone on the same Wi-Fi. ``python -m story.local`` starts all the devices of
the config on this one machine for a rehearsal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import socket
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from api import views
from mesh.core import crypto
from mesh.core.node import Node
from mesh.core.packet import RESCUE_DST, Priority

from .lan_transport import LanTransport

PAGE = Path(__file__).with_name("node.html")

# real-time settings: quick enough for a live demo, slow enough for Wi-Fi
HELLO_INTERVAL = 1.0
NEIGHBOUR_TIMEOUT = 4.0
PRUNE_INTERVAL = 0.5
LINK_STATE_INTERVAL = 2.0
ACK_TIMEOUT = 3.0
MAX_RETRIES = 3
ACK_POLL_INTERVAL = 0.5
SF_RETRY_INTERVAL = 3.0


class SosBody(BaseModel):
    text: Optional[str] = Field(None, max_length=400)


class PowerBody(BaseModel):
    on: bool


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["links"] = [tuple(pair) for pair in cfg["links"]]
    return cfg


def neighbours_of(cfg: dict, node_id: str) -> set[str]:
    out: set[str] = set()
    for a, b in cfg["links"]:
        if a == node_id:
            out.add(b)
        elif b == node_id:
            out.add(a)
    return out


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def friendly_log(node: Node, labels: dict[str, str], limit: int = 14) -> list[dict]:
    """The node's own event log, rewritten in plain English."""
    name = lambda i: labels.get(i, i)  # noqa: E731
    out = []
    for ev in node.store.events_since(0, 800)[-120:]:
        kind, peer = ev["kind"], ev.get("peer")
        text = None
        if kind == "peer_up":
            text = f"Can now hear {name(peer)}"
        elif kind == "peer_down":
            text = f"Lost contact with {name(peer)}"
        elif kind == "sent":
            text = f"Sent a message toward {name(peer)}"
        elif kind == "forward":
            row = node.store.get_message(ev["msg_id"]) if ev.get("msg_id") else None
            origin = f" from {name(row['src'])}" if row else ""
            text = f"Relayed a message{origin} on to {name(peer)}"
        elif kind == "recv":
            text = "A message arrived here"
        elif kind == "ack":
            text = "Delivery confirmed by the other side"
        elif kind == "retry":
            text = f"No confirmation yet, trying again via {name(peer)}"
        elif kind == "sf_queue":
            text = "No route right now, holding the message safely"
        elif kind == "sf_flush":
            text = f"A route is back, sending the held message via {name(peer)}"
        elif kind.startswith("drop_"):
            text = f"Dropped a message ({kind[5:].replace('_', ' ')})"
        if text:
            out.append({"t": ev["ts_ms"], "text": text})
    return out[-limit:][::-1]


def build_app(node_id: str, cfg: dict, secret: Optional[str], sign: bool) -> FastAPI:
    spec = cfg["nodes"][node_id]
    labels = {i: n.get("label", i) for i, n in cfg["nodes"].items()}
    peers = {i: (n["host"], n["port"]) for i, n in cfg["nodes"].items() if i != node_id}
    state: dict = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        transport = LanTransport(node_id, spec["port"], peers, neighbours_of(cfg, node_id))
        node = Node(
            node_id, transport, role=spec["role"],
            hello_interval=HELLO_INTERVAL, neighbour_timeout=NEIGHBOUR_TIMEOUT,
            prune_interval=PRUNE_INTERVAL, link_state_interval=LINK_STATE_INTERVAL,
            ack_timeout=ACK_TIMEOUT, max_retries=MAX_RETRIES, ack_poll_interval=ACK_POLL_INTERVAL,
            sf_retry_interval=SF_RETRY_INTERVAL,
            session_key=hashlib.sha256(secret.encode()).digest() if secret else None,
            keypair=crypto.generate_keypair() if sign else None,
        )
        state.update(node=node, transport=transport, started=time.time())
        await node.start()
        yield
        await node.stop()

    app = FastAPI(title=f"EcoMesh device {node_id}", lifespan=lifespan)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(PAGE)

    @app.get("/api/me")
    async def me():
        node: Node = state["node"]
        transport: LanTransport = state["transport"]
        online = transport.enabled
        known = node.graph.reachable_from(node_id) if online else {node_id}
        nodes = [
            {"id": i, "label": n.get("label", i), "role": n["role"], "x": n["x"], "y": n["y"],
             "known": i in known, "me": i == node_id}
            for i, n in cfg["nodes"].items()
        ]
        links = [
            {"a": a, "b": b, "known": online and (node.graph.edge(a, b) is not None or node.graph.edge(b, a) is not None)}
            for a, b in cfg["links"]
        ]
        rescue_ids = [i for i, n in cfg["nodes"].items() if n["role"] == "RESCUE" and i != node_id]
        route = views.route_view(node.router, node.graph, rescue_ids[0] if rescue_ids else RESCUE_DST) if online else None
        view = views.node_view(node, labels.get(node_id))
        thread = view["thread"]
        for m in thread:
            if m["direction"] != "sent":
                continue
            evs = node.store.events_for_message(m["msg_id"])
            hops = [e["peer"] for e in evs if e["kind"] in ("sent", "retry", "sf_flush") and e.get("peer")]
            m["first_hop"] = hops[-1] if hops else None
            m["retries"] = sum(1 for e in evs if e["kind"] == "retry")
        forwarded = [
            {"src": r["src"], "dst": r["dst"], "priority_name": views.PRIORITY_NAMES.get(r["priority"], "?"),
             "created_ms": r["created_ms"]}
            for r in node.store.list_messages(direction="forwarded", limit=8)
        ]
        return {
            "id": node_id, "label": labels.get(node_id, node_id), "role": spec["role"], "online": online,
            "nodes": nodes, "links": links,
            "route": route["path"] if route and route["path"][-1] != node_id else [],
            "hearing": [n["id"] for n in view["neighbours"]],
            "neighbours": view["neighbours"],
            "counters": view["counters"],
            "forwarded": forwarded,
            "now_ms": int(time.time() * 1000),
            "held": len(view["queues"]["store_forward"]),
            "thread": thread,
            "log": friendly_log(node, labels),
            "security": view["security"],
            "web_url": f"http://{lan_ip()}:{spec['web']}",
        }

    @app.post("/api/sos")
    async def sos(body: SosBody = SosBody()):
        node: Node = state["node"]
        if not state["transport"].enabled:
            raise HTTPException(409, "this device is switched off")
        text = body.text or f"SOS from {labels.get(node_id, node_id)}: need help"
        # address the rescue team itself when the config has one, so the
        # gateway is a relay on the way; otherwise "nearest rescue/gateway"
        rescue_ids = [i for i, n in cfg["nodes"].items() if n["role"] == "RESCUE" and i != node_id]
        dst = rescue_ids[0] if rescue_ids else RESCUE_DST
        pkt = await node.send(dst, text.encode("utf-8"), priority=Priority.SOS, needs_ack=True)
        return {"msg_id": str(pkt.msg_id)}

    @app.post("/api/power")
    async def power(body: PowerBody):
        state["transport"].enabled = body.on
        return {"online": body.on}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one EcoMesh device over real sockets")
    parser.add_argument("--id", required=True, help="this device's id from the config, e.g. L1")
    parser.add_argument("--config", default=str(Path(__file__).with_name("mesh.json")))
    parser.add_argument("--web-host", default="0.0.0.0", help="use 127.0.0.1 to keep the page local")
    parser.add_argument("--secret", help="shared passphrase: turns on AES-256-GCM payload encryption")
    parser.add_argument("--sign", action="store_true", help="turn on Ed25519 signing")
    args = parser.parse_args()

    cfg = load_config(args.config)
    if args.id not in cfg["nodes"]:
        raise SystemExit(f"unknown device {args.id!r}; config has {sorted(cfg['nodes'])}")
    web = cfg["nodes"][args.id]["web"]
    print(f"\n  device {args.id}  this laptop: http://127.0.0.1:{web}")
    if args.web_host == "127.0.0.1":
        print("  (page is local only; drop --web-host 127.0.0.1 to open it from a phone)\n")
    else:
        print(f"  Open on your phone: http://{lan_ip()}:{web}   (phone on the same Wi-Fi or hotspot)\n")
    uvicorn.run(build_app(args.id, cfg, args.secret, args.sign), host=args.web_host, port=web, log_level="warning")


if __name__ == "__main__":
    main()
