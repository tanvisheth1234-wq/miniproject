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
- **Phase 4 (API + UI + integration): in progress.** See
  [`docs/PHASE4_HANDOFF.md`](docs/PHASE4_HANDOFF.md) for the backend API surface and what
  needs building, and [`docs/FRONTEND_PROMPT.md`](docs/FRONTEND_PROMPT.md) for the
  frontend build prompt and design-tool setup.

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
`develop_4` (+ Phase 4, in progress). See `CONTRIBUTING.md` for commit conventions.

## Team

- **Miti Shah** — Phase 1–2 code (discovery, relay, simulator)
- **Twissha Shah** — Phase 3 code (routing, reliability, security, storage)
- **Tanvi Sheth** — Phase 4 (API, UI, integration)
