# Contribution log

One row per delivery. Phase V is graded partly on this file plus Git history
(`git shortlog -sn`), since it's the only record an external examiner has of
who did what.

| Week / Phase | Member | Delivered |
|---|---|---|
| Phase 1 | Tanvi | `packet.py` (52-byte header pack/unpack + tests), `transport.py` interface, `transport_udp.py`, two-node terminal demo |
| Phase 2 | Miti | `discovery.py` (HELLO, neighbour table, death detection), `relay.py` (single-hop A→B→C forwarding), `node.py` skeleton, `transport_sim.py`, `sim/runner.py` skeleton |
| Phase 3 | Twissha | `routing.py` — `MeshGraph` with the weighted cost function and link-state gossip; later link-state re-flooding so the graph is network-wide, and ACK-timeout failures fed into the cost |
| Phase 3 | Miti | `routing.py` — Dijkstra pathfinding with gateway/rescue handling and route caching |
| Phase 3 | Miti | `reliability.py` — dedup set, priority queue, ACK tracking with retry, store-and-forward queue |
| Phase 3 | Miti | `crypto.py` — AES-256-GCM payload encryption, Ed25519 signing primitives |
| Phase 3 | Miti | `store.py` — SQLite (WAL) message/event/peer log, section 11 schema |
| Phase 3 | Twissha | Wired routing, reliability, store, and crypto into `node.py`: multi-hop forwarding via `route_resolver`, role propagation through gossip, dedup on the receive path, priority-ordered sending, `Node.send()` with ACK/retry/store-and-forward, full event logging, opt-in payload encryption |
| Phase 4 | Tanvi | `api/` FastAPI + WebSocket server, mesh lab (real `Node`s over the simulated radio, kill/revive, link editing, event feed), protocol inspector and security drill endpoints |
| Phase 4 | Tanvi | `ui/` React + Vite + Tailwind PWA: overview, live demo with the six-beat script, node view (long-press SOS), rescue dashboard, routing, reliability, protocol, security, simulator pages |
| Phase 4 | Tanvi | `sim/scenarios.py` + `api/vtime.py`: the six required scenarios plus a priority-under-load scenario on a virtual clock, with the section 16 metrics |
| Phase 4 | Tanvi | Engine fixes found by integration: relay dedup keyed on (type, msg_id[, attempt]) with a retransmission counter in the formerly reserved header byte and re-ACK of duplicates (multi-hop ACK and retry did not work before); link quality measured from HELLO reception; link-state reports now replace rather than merge; hop-count routing mode; Store query helpers |
| Phase 3 | Miti | Documentation: Phase 2 UML diagrams and the master project-plan reference PDF; SRS and Design of Algorithms implementation-status notes (v1.2); Phase 4 hand-off and frontend build prompt |
| Phase 4 | Twissha | Integration and the multi-device demo (`story/`: `LanTransport`, per-device web page, survivor, gateway and rescue screens), packet-parser hardening, robustness and socket tests, the evidence scripts and the mini-project report (`docs/report/`) |

## Correction of commit authorship (24 October 2026)

Nine Phase 3 commits were made from Twissha's laptop while Miti was working on it, and so were recorded under
Twissha's Git account. At Miti's request, and with the agreement of all three team members, their author and
committer were changed to Miti (`mitishah2109`) on `develop_3`, `develop_4` and `develop_5`. File contents are
unchanged; only commit identities and IDs changed. The nine commits are the Dijkstra pathfinding, dedup set and
priority queue, ACK tracking with retry and store-and-forward queue, AES-256-GCM and Ed25519, and SQLite log
commits of 14 September 2026, and the four documentation commits of 11 October 2026 listed above.
All other Phase 3 commits remain under Twissha's account.
