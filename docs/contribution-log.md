# Contribution log

One row per delivery. Phase V is graded partly on this file plus Git history
(`git shortlog -sn`), since it's the only record an external examiner has of
who did what.

| Week / Phase | Member | Delivered |
|---|---|---|
| Phase 1 | Tanvi | `packet.py` (52-byte header pack/unpack + tests), `transport.py` interface, `transport_udp.py`, two-node terminal demo |
| Phase 2 | Miti | `discovery.py` (HELLO, neighbour table, death detection), `relay.py` (single-hop A→B→C forwarding), `node.py` skeleton, `transport_sim.py`, `sim/runner.py` skeleton |
| Phase 3 | Twissha | `routing.py` — link-state gossip, weighted cost function, Dijkstra, gateway/rescue routing, route caching |
| Phase 3 | Twissha | `reliability.py` — dedup set, priority queue, ACK tracking with retry, store-and-forward queue |
| Phase 3 | Twissha | `crypto.py` — AES-256-GCM payload encryption, Ed25519 signing primitives |
| Phase 3 | Twissha | `store.py` — SQLite (WAL) message/event/peer log, section 11 schema |
| Phase 3 | Twissha | Wired routing, reliability, store, and crypto into `node.py`: multi-hop forwarding via `route_resolver`, role propagation through gossip, dedup on the receive path, priority-ordered sending, `Node.send()` with ACK/retry/store-and-forward, full event logging, opt-in payload encryption |
