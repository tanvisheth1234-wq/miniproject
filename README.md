# EcoMesh — Distributed Peer-to-Peer Disaster Relief Communication Mesh

A decentralised mesh network for disaster scenarios: every device is simultaneously an
endpoint and a router. Messages hop device to device — no internet, no cell towers, no
central server — until they reach their destination, a gateway with residual external
connectivity, or a rescue team.

## Project status

- **Phase 1–3 (backend engine): done.** Wire protocol, transport, discovery, weighted
  routing with network-wide gossip, reliability (priority queue, ACK/retry, dedup,
  bounded store-and-forward), security (AES-256-GCM + Ed25519, both opt-in), SQLite
  logging. 256 tests passing on `develop_3`.
- **Phase 4 (API + UI + integration): built on `develop_4`.** FastAPI + WebSocket server
  (`api/`), a mesh lab that runs many real `Node`s in one process, a virtual-time simulator
  with the section 16 metrics (`sim/scenarios.py`), and a React website (`ui/`) with the node
  view, rescue dashboard, live demo, and pages for routing, reliability, wire protocol,
  security and the simulator. See [`docs/PHASE4_HANDOFF.md`](docs/PHASE4_HANDOFF.md).

## Run the website

```
pip install -r requirements.txt
cd ui && npm install && npm run build && cd ..
python -m api.server            # http://127.0.0.1:8000  (UI + API + WebSocket)
```

For UI development run `python -m api.server` and `npm run dev` (in `ui/`) side by side;
the dev server on :5173 proxies `/api` and `/ws` to :8000. Simulator scenarios also run from
the command line: `python -m sim.scenarios --scenario hopcount_vs_weighted --runs 20`.

## Documents

- [`docs/SRS_EcoMesh_Group20.pdf`](docs/SRS_EcoMesh_Group20.pdf) — requirements (IEEE 830)
- [`docs/Design_of_Algorithms_EcoMesh_Group20.pdf`](docs/Design_of_Algorithms_EcoMesh_Group20.pdf) — algorithms, pseudocode, complexity analysis
- [`docs/project-plan.md`](docs/project-plan.md) — master reference document
- [`docs/contribution-log.md`](docs/contribution-log.md) — who built what, by phase

## Running the tests

```
pip install -r requirements.txt
python -m pytest -q
```

## Branch layout

Each phase lives on its own branch, inheriting everything before it rather than merging
back: `develop` (Phase 1) → `develop_2` (+ Phase 2) → `develop_3` (+ Phase 3) →
`develop_4` (+ Phase 4) → `develop_5` (+ Phase 5, in progress). See `CONTRIBUTING.md` for commit conventions.

## Team

- **Miti Shah** — Phase 1–2 code (discovery, relay, simulator) and Phase 3 components (Dijkstra routing, dedup and priority queue, ACK/retry and store-and-forward, encryption and signing, SQLite log)
- **Twissha Shah** — Phase 3 cost function, link-state gossip and node wiring; Phase 4 integration, multi-device demo and report
- **Tanvi Sheth** — Phase 4 (API, UI, integration)
