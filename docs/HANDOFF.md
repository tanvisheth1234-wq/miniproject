# EcoMesh: project hand-off

Single status document for the team (Twissha, Tanvi, Miti) and for anyone, or any Claude session, picking this repo up cold. Branch: `develop_4` (Phase 4). Repo: https://github.com/tanvisheth1234-ug/miniproject

## 1. What the project is

EcoMesh is a peer-to-peer messaging system for disasters. When an earthquake, fire or building collapse takes down towers, internet and SMS, people are still within reach of each other's devices. In EcoMesh every device is both an endpoint and a relay: an SOS hops from device to device until it reaches a rescue team or a gateway to the outside. No server, no internet.

Core behaviour:
- Devices find neighbours by HELLO beacons and gossip link-state reports, so each node knows the whole mesh.
- Routing is Dijkstra over a cost that penalises lossy links and recent failures: `cost = 1 + 5(1 - q) + 3f` (q = link quality, f = recent ACK timeouts).
- SOS packets have priority over routine messages at every hop.
- Delivery is acknowledged. A missed ACK triggers a retry on a recomputed route.
- No route means the message is held (bounded: 500 messages, 30 minutes) and sent automatically when a path appears.
- Payloads are AES-256-GCM encrypted (one pre-shared key for the mesh); each packet's identity is signed with Ed25519.
- Every node keeps its own SQLite log. All reported metrics are queries over those logs.

Stack: Python 3.10 asyncio engine; FastAPI + WebSocket API; React PWA website; simulator on a virtual clock; real-socket multi-device deployment.

## 2. Who built what (phases)

| Phase | Branch | Content |
|---|---|---|
| 1 | `develop` | 52-byte binary packet, `Transport` interface |
| 2 | `develop_2` | discovery, single-hop relay, simulated transport |
| 3 | `develop_3` (Twissha) | routing, reliability, crypto, store-and-forward, SQLite, `Node` |
| 4 | `develop_4` (Tanvi: API/UI; Twissha: integration, fixes, devices, report) | FastAPI + WebSocket, React site, simulator scenarios and metrics, multi-device demo, tests, report |

Rules we agreed: one branch per phase; never merge between phase branches; each person runs their own git commands.

## 3. What is done (Phase 4)

**Engine and tests**
- All engine modules in `mesh/core/`; 312 automated tests pass (`python -m pytest -q`). Two timing-sensitive tests fail occasionally when the machine is busy (they pass alone); fix is to replace fixed sleeps with polling.
- Defects found and fixed in this phase: multi-hop ACK/retry dedup bug, dead nodes staying routable, a parser raising the wrong exception on non-ASCII node ids (found by fuzzing), a `Node.stop()` hang on Windows.
- Robustness tests (`tests/test_robustness.py`: fuzzing) and real-socket transport tests (`tests/test_lan_transport.py`).

**Multi-device deployment (`story/`)**
- `LanTransport` (`story/lan_transport.py`): real TCP between processes, a topology file defines who can hear whom (emulates radio range).
- `story/node.py` + `story/node.html`: one program per device; the page becomes a survivor phone, gateway view or rescue console by role. Redesigned this round as a calm, plain, text-first interface (no emojis).
- Run all five devices on one machine: `python -m story.local` then open `http://127.0.0.1:8101` (survivor) and `http://127.0.0.1:8105` (rescue console). Two laptops: `story/mesh_two_laptops.json` (each laptop starts its own devices with `--only`). It worked on Twissha's and Tanvi's laptops over a hotspot.

**Website (`ui/`, Tanvi)**
- React PWA: overview, six-beat live demo, node view with long-press SOS, rescue dashboard, routing, reliability, protocol, security and simulator pages. Runs against `api/server.py`. Not restyled in this round: it keeps its original look.

**Simulator and metrics (`sim/`, `api/`)**
- Seven scenarios up to 65 nodes with seeded loss; metrics per priority including p95 latency and transmissions.

**Report (`docs/report/`)**
- Final PDF: `docs/report/EcoMesh_Mini_Project_Report.pdf` (55 pages: 12 front matter, 11 chapters, references). Follows the department Overleaf template and the Mini Project Report Preparation Guidelines. Source in `docs/report/latex/`; numbers are generated from `docs/report/evidence/results/*.json` by scripts in `docs/report/evidence/` (see `docs/report/README.md`).
- Page count is above the template's 25-40 target; the bottom margin is 30 mm instead of the template's 50 mm to keep it at 55. Decide with the guide if that is acceptable.

## 4. Measured results (all in the report)

- 40 nodes, 20% per-link loss, relay and gateway failures: 92.6% mean delivery over 50 runs (worst run 76%).
- SOS median latency 4.4x lower than routine traffic under congestion.
- Weighted routing delivered 99.2% vs 57.4% for hop-count routing on identical seeds (designed topology).
- Five real processes: SOS median 47 ms (p95 102 ms) on loopback; relay failover about 4 s; held messages flushed in about 4.5 s.
- Recovery after relay death is quantised by the 10 s heartbeat timeout (27 of 50 trials just over 10 s); delivery falls below 90% beyond about 43 nodes at 20% loss.

## 5. What is left (not code)

| Item | Owner | Notes |
|---|---|---|
| Poster and/or research paper for the end-semester evaluation | all | the college email asks for a poster at ESE; reports and posters come from `docs/report` content |
| Plagiarism report | all | upload the report PDF/LaTeX to the college-approved checker; add the result as asked |
| Phase IV presentation deck | all | not built yet; Claude can generate it from the report |
| Photo or screen capture of the two-laptop run | Twissha + Tanvi | add to Chapter 10 (Figure on deployment) |
| Contribution log confirmation | each member | report Section 7.8 lists commits: Twissha 24, Tanvi 19, Miti 2 (Miti's commits are under the name "Delta Student"); each member must confirm their real contribution and fix Git identity going forward |
| Date and place on the declaration; guide's review | all | |
| Printed, spiral-bound copy for Phase IV | all | per the college email |
| Optional: usability test with 5 people | any | report states none was performed; either do it or leave the statement |

## 6. Known limits (stated honestly in the report)

- No radio hardware: the "radio" is a neighbour-restricted LAN. A real phone-to-phone version needs a Bluetooth LE or Wi-Fi Direct transport (the `Transport` interface is built for that swap).
- One pre-shared key for the whole mesh, so any key holder could read forwarded payloads. Per-pair key agreement is future work.
- Partial: immediate flush when a new neighbour appears (SNF-3); history filter control on the screens (LOG-5).
- No automated browser tests; scale tested to 65 simulated nodes; live timings were on one machine.

## 7. Working with this repo

- Python 3.10 on Windows. Install `pip install -r requirements.txt`; the website needs `cd ui && npm install`.
- Run tests: `python -m pytest -q`.
- Rebuild the report: `cd docs/report/latex && tectonic -X compile main.tex --outdir build` (or upload `latex/` to Overleaf). Regenerate evidence with the commands in `docs/report/README.md`.
- Edit names, UIDs, guide and HoD only in `docs/report/latex/students.tex`.
- Do not edit `docs/report/latex/generated/*` by hand; it is regenerated from the evidence scripts.
- Do not commit the template zips, the guidelines docx or `ui/package-lock.json` changes.
