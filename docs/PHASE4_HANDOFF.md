# Phase 4 Handoff — API + UI + Integration

For Tanvi, taking over Phase 4. This explains exactly what exists, what Phase 4 needs to
build on top of it, and how to actually use the backend from a UI without having to read
the whole codebase first.

## Where things stand

Branch `develop_3` has all of Phase 1–3 done: wire protocol, transport (real sockets +
in-memory simulator), discovery, routing (weighted Dijkstra with network-wide gossip),
reliability (priority queue, ACK/retry, dedup, store-and-forward with bounds), security
(AES-256-GCM encryption + Ed25519 signing, both optional), and SQLite-backed logging.
**256 tests passing.** None of it has a UI or an HTTP/WebSocket API yet — that's Phase 4.

Branch off `develop_3` for this work:
```
git checkout develop_3
git pull
git checkout -b develop_4
git push -u origin develop_4
```

## What Phase 4 needs (per the project plan)

1. **API layer** — FastAPI + WebSocket server, one per node, serving the UI and pushing
   live state (new message, delivery status change, node up/down).
2. **Node UI** — SOS button (long-press to arm), reachable-peers list with hop distance,
   message thread showing live status (`sending → relayed via N nodes → delivered`).
3. **Rescue dashboard** — live mesh graph (d3-force), SOS queue sorted by priority then
   age, delivery log, aggregate stats (delivery ratio, mean hops, nodes online).
4. **PWA packaging** — installable, works offline, React + Vite + Tailwind per the stack
   already chosen in the master plan.
5. Eventually: real multi-laptop testing over `UdpTcpTransport` (already built, not yet
   used outside tests) and the 6-beat demo script (§18 of the master plan PDF).

**Don't build the UI before the API has something real to show** — the whole point of
Phase 4 is wiring a real UI to the real engine, not a mockup.

## The only class the UI actually needs: `Node`

Everything the API layer needs to expose is already on `mesh.core.node.Node`. You don't
need to touch routing/reliability/crypto internals directly.

```python
from mesh.core.node import Node
from mesh.core.transport_udp import UdpTcpTransport   # real sockets, for actual demo use
from mesh.core.discovery import NodeRole

transport = UdpTcpTransport(...)
node = Node(
    node_id="A",
    transport=transport,
    role=NodeRole.NORMAL,       # or GATEWAY / RESCUE
    session_key=shared_key,     # optional — AES-256-GCM encryption
    keypair=my_keypair,         # optional — Ed25519 signing
)
await node.start()

# originate a message
pkt = await node.send(dst="B", payload=b"hello", priority=Priority.NORMAL, needs_ack=True)

# or raise an SOS
pkt = await node.send(dst=RESCUE_DST, payload=b"help", priority=Priority.SOS, needs_ack=True)

# live hooks — wire these straight to WebSocket pushes
node.on_deliver = lambda pkt: ...     # a message arrived, addressed to us
node.on_forward = lambda pkt, hop: ...  # we relayed something onward
node.on_drop    = lambda pkt, reason: ...  # something got discarded, with why

# who's currently reachable, with hop distance via node.router
node.neighbours          # live NeighbourTable
node.router.shortest_path(dst)   # full path, for "relayed via N nodes"
```

`RESCUE_DST` is importable from `mesh.core.packet`. `Priority.SOS` / `NORMAL` / `STATUS`
from the same module.

## Querying history and stats: `node.store`

Every node has a `Store` (SQLite, WAL mode) — this is what the message history view and
the rescue dashboard's aggregate stats read from. No new schema needed.

```python
node.store.get_message(msg_id)           # one message's full record
node.store.messages_by_status("queued_sf")  # for the "N retained" counter
node.store.events_for_message(msg_id)    # full timeline of one message
node.store.events_by_kind("peer_down")   # e.g. for a node-failure feed
node.store.count_events("delivered")     # for delivery-ratio style stats
node.store.all_peers()                   # for the live topology view
```

## Demo script to build the UI against (master plan §18)

Five nodes: L1 trapped sender (no gateway reachable), L2/L3 relays, L4 gateway (starts
switched off), L5 rescue dashboard. Beats: self-organise → SOS beats NORMAL → kill a
relay mid-transfer, watch it reroute → kill the gateway, watch SOS queue → bring gateway
back, watch the flush. The UI needs to make all six of these visually obvious — that's
the actual grading criterion, not feature count.

## Tests, if you touch the backend

```
python -m pytest -q
```
Should say `256 passed`. If you add API code, put its tests under `tests/` following the
existing naming (`test_<module>.py`), same as everything else.


---

## Phase 4 status (delivered on `develop_4`)

**Done:** API + WebSocket server, mesh lab, node view, rescue dashboard, live demo, routing /
reliability / protocol / security / simulator pages, PWA manifest and service worker, simulator
scenarios with metrics. 283 backend tests pass; the UI was exercised in a real browser.

**Engine changes made during integration** (all covered by new tests):
- `relay.py`: the dedup key is now `(type, msg_id)` at the destination and
  `(type, msg_id, attempt)` at relays. Before, an ACK returning along its DATA's path was
  dropped as a duplicate at the first shared relay, and a retry was swallowed by the first relay
  that had seen the original, so multi-hop ACK + retry did not work.
- `packet.py`: the reserved header byte (offset 51) is now `attempt`, a retransmission counter.
  The SRS and algorithm documents still call it "reserved" and should be updated.
- `node.py`: re-ACKs a duplicate of a message it already accepted; records the route on the
  sender's row from the returning ACK; optional `hop_count_routing`.
- `discovery.py` / `routing.py`: link quality is measured from HELLO reception (it was never
  fed before, so every link looked perfect); a link-state report replaces the origin's old edges
  (dead nodes were routed through indefinitely); `MeshGraph.reachable_from`.

**Not done / honest limits:**
- No single-node server over `UdpTcpTransport` for the multi-laptop demo yet. The lab hosts all
  nodes in one process over the simulated radio; `views.py` already works on any `Node`, so a
  one-node server is a small addition.
- The radio capacity slider and SOS-under-load numbers come from a finite-capacity radio model
  (`api/radio.py`) that schedules by priority at every hop including the origin; the engine's own
  priority queue only covers relayed packets.
- Signing is opt-in mesh-wide, so an unsigned forgery is not caught (shown on the Security page).
