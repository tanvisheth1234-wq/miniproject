# Frontend Build Prompt — Phase 4

This is for Tanvi. Two parts: (1) how to connect design/MCP tools before starting, and
(2) the actual prompt to paste into the AI assistant used to build the UI.

## 1. Connect MCP tools first

Before starting the build, connect these so the AI assistant can pull real design
references and components instead of guessing:

- **21st.dev** — component library MCP, gives ready-made React/Tailwind components to
  start from instead of building every button from scratch.
- **Figma** — if there's an existing design file/mockup, connect this so the assistant
  can read it directly rather than you describing it.
- **Framer Motion** — for the live state transitions that actually sell the demo (a
  message animating from `sending` → `relayed via 3 nodes` → `delivered`, a node dimming
  out on the topology graph when it goes down).
- **Penpot** — open-source design-file alternative to Figma, same idea if that's what's
  being used instead.
- **UI/UX Pro** — design-pattern/critique MCP, useful for a second opinion on the layout
  before committing to it.

In the assistant's MCP settings: add each one → follow its own auth flow (most are "find it, click
connect, approve in the browser tab that opens").

**Giving the assistant the actual backend code as context:** since the Python backend
(`mesh/core/`) isn't on whatever platform the frontend gets built on, zip the repo and
hand that over as a file/MCP source so the assistant has the real `Node`/`Store` API
surface instead of inventing one that doesn't match:

```
# from the project root
git archive -o mesh-backend.zip HEAD
```
That produces a clean zip of the tracked repo (no build artifacts, no `.git` folder).
Upload `mesh-backend.zip` in the chat, or connect it as an MCP filesystem source if the
tool supports one, and say explicitly: *"this zip is the real backend — build the
frontend and API against the actual `Node` and `Store` classes in here, not an assumed
API."* Point it at `docs/PHASE4_HANDOFF.md` inside the zip first — that's the real
reference for what's built and what the UI needs to call.

## 2. The prompt

```
I'm building the frontend + API layer for EcoMesh, a disaster-relief peer-to-peer mesh
networking project (Mini Project, Phase 4). The backend is fully built and tested —
routing, reliability, encryption, signing, SQLite logging, all wired into a single
`Node` class. I've attached the backend as a zip. Read docs/PHASE4_HANDOFF.md inside it
first — that's the authoritative reference for the Node/Store API, don't invent methods
that aren't there.

Build two things:

1. A FastAPI + WebSocket server (one per node) that wraps a `Node` instance and exposes:
   - REST: send a message, raise an SOS, get reachable peers, get message history,
     get aggregate delivery stats (query node.store for all of this, see the handoff doc)
   - WebSocket: push live events as they happen — use node.on_deliver / on_forward /
     on_drop as the trigger points, plus peer up/down from node.store's "peer_up"/
     "peer_down" events

2. A React + Vite + Tailwind frontend, PWA-installable, with exactly two views:

   NODE VIEW (what a trapped person/relay sees):
   - A large SOS button requiring a sustained long-press to arm (prevent accidental fire)
   - List of currently reachable peers with hop distance
   - Message composer + thread, each message showing live status:
     sending → relayed via N nodes → delivered (or queued / failed)
   - A "nearby count" so the user knows they're not alone
   - Nothing else — resist adding features, this view should feel like an emergency
     tool, not a chat app

   RESCUE DASHBOARD (what rescue coordinators see):
   - Live mesh topology graph (nodes appear on join, dim/grey out on failure, edges
     thicken with link quality) — use d3-force
   - SOS queue sorted by priority then age, with sender ID, hop path, time since sent
   - Delivery log: source, destination, hop path, outcome
   - Live stat strip: delivery ratio, mean hop count, nodes online

Style: dark, minimal, high-contrast — this is read under stress, not browsed casually.
Every state change should animate (Framer Motion) rather than snap, especially the hop
path building up on a message and nodes appearing/disappearing on the topology graph —
that's the single most important visual moment in the whole project's demo.

Don't build anything beyond these two views. Don't add authentication, user accounts, or
settings screens — none of that exists in the spec and it isn't being graded.
```

Paste that as-is, or trim it if the tool has a shorter context budget — the backend zip
+ the handoff doc inside it matter more than the prompt wording itself.
