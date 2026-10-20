"""FastAPI + WebSocket server for EcoMesh.

    python -m api.server                # http://127.0.0.1:8000  (UI + API)
    python -m api.server --port 8001 --preset building12

REST wraps the real engine objects (see ``views.py`` / ``lab.py``); the
WebSocket pushes every node event as it is logged, plus a coalesced
snapshot of the whole mesh a few times a second. The built React app in
``ui/dist`` is served from the same port, so one command shows everything.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from mesh.core.discovery import NodeRole
from mesh.core.packet import RESCUE_DST, PacketError
from sim.scenarios import SCENARIOS

from . import protocol, security_demo
from .events import EventBus
from .jobs import JobManager
from .lab import LabError, MeshLab
from .presets import PRESETS

UI_DIST = Path(__file__).resolve().parent.parent / "ui" / "dist"


# --- request bodies ------------------------------------------------------------------

class ResetBody(BaseModel):
    preset: str = "demo5"
    encryption: bool = False
    signing: bool = False
    routing: Literal["weighted", "hopcount"] = "weighted"
    radio_service_ms: float = Field(0, ge=0, le=2000)
    seed: Optional[int] = None


class SendBody(BaseModel):
    dst: str
    text: str = Field(min_length=1, max_length=400)
    priority: int = 1
    needs_ack: bool = True


class SosBody(BaseModel):
    text: Optional[str] = Field(None, max_length=400)


class LinkBody(BaseModel):
    a: str
    b: str
    loss: float = Field(0.0, ge=0, le=1)
    latency_ms: tuple[float, float] = (50.0, 120.0)


class AddNodeBody(BaseModel):
    id: str
    role: str = NodeRole.NORMAL
    label: str = ""
    x: float = 0.5
    y: float = 0.5
    links: list[str] = []


class ConfigBody(BaseModel):
    radio_service_ms: Optional[float] = Field(None, ge=0, le=2000)


class BurstBody(BaseModel):
    src: str
    dst: str = RESCUE_DST
    normal: int = Field(6, ge=1, le=20)
    service_ms: float = Field(150.0, ge=10, le=2000)


class BuildPacketBody(BaseModel):
    type: str = "DATA"
    priority: int = 0
    src: str = "L1"
    dst: str = RESCUE_DST
    ttl: int = Field(10, ge=0, le=255)
    hop_count: int = Field(0, ge=0, le=255)
    path: list[str] = []
    text: str = Field("", max_length=400)
    needs_ack: bool = True
    store_forward_ok: bool = True
    encrypt: bool = False
    sign: bool = False


class HexBody(BaseModel):
    hex: str


class RelayBody(BaseModel):
    hex: str
    relay: str = "L2"


class SealBody(BaseModel):
    text: str = Field(max_length=400)
    key: Optional[str] = None


class OpenBody(BaseModel):
    wire: str
    key: Optional[str] = None
    tamper: bool = False


class SignBody(BaseModel):
    message: str = Field(max_length=400)
    who: Literal["alice", "mallory"] = "alice"


class VerifyBody(BaseModel):
    message: str = Field(max_length=400)
    public_key: str
    signature: str


class SimRunBody(BaseModel):
    scenario: str
    runs: int = Field(5, ge=1, le=300)
    nodes: Optional[int] = Field(None, ge=4, le=60)
    loss: Optional[float] = Field(None, ge=0, le=0.6)
    seed: int = 1


# --- app factory ----------------------------------------------------------------------

def create_app(lab: Optional[MeshLab] = None, initial_preset: str = "demo5", serve_ui: bool = True) -> FastAPI:
    bus = EventBus()
    lab = lab or MeshLab(bus)
    lab.bus = bus
    jobs = JobManager()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await lab.load(initial_preset)
        yield
        await lab.shutdown()
        jobs.shutdown()

    app = FastAPI(title="EcoMesh API", version="0.4", lifespan=lifespan)
    app.state.lab, app.state.bus, app.state.jobs = lab, bus, jobs

    @app.exception_handler(LabError)
    async def _lab_error(_request: Request, exc: LabError):
        code = 404 if "unknown" in str(exc) else 409 if "switched off" in str(exc) else 400
        return JSONResponse({"detail": str(exc)}, status_code=code)

    @app.exception_handler(PacketError)
    async def _packet_error(_request: Request, exc: PacketError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(security_demo.SecurityError)
    async def _security_error(_request: Request, exc: security_demo.SecurityError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # ---- lab ----------------------------------------------------------------------

    @app.get("/api/health")
    async def health():
        return {"ok": True, "nodes_online": len(lab.nodes), "subscribers": bus.subscriber_count, "time": time.time()}

    @app.get("/api/presets")
    async def presets():
        return [p.meta() for p in PRESETS.values()]

    @app.get("/api/lab")
    async def lab_snapshot():
        return lab.snapshot()

    @app.post("/api/lab/reset")
    async def lab_reset(body: ResetBody):
        await lab.load(body.preset, encryption=body.encryption, signing=body.signing, routing=body.routing,
                       radio_service_ms=body.radio_service_ms, seed=body.seed)
        return lab.snapshot()

    @app.patch("/api/lab/config")
    async def lab_config(body: ConfigBody):
        lab.configure(radio_service_ms=body.radio_service_ms)
        return lab.snapshot()["config"]

    @app.post("/api/lab/nodes")
    async def lab_add_node(body: AddNodeBody):
        return await lab.add_node(body.id, body.role, body.label, body.x, body.y, body.links)

    @app.post("/api/lab/nodes/{node_id}/kill")
    async def lab_kill(node_id: str):
        await lab.kill(node_id)
        return {"node": node_id, "online": False}

    @app.post("/api/lab/nodes/{node_id}/revive")
    async def lab_revive(node_id: str):
        await lab.revive(node_id)
        return {"node": node_id, "online": True}

    @app.put("/api/lab/links")
    async def lab_set_link(body: LinkBody):
        return await lab.set_link(body.a, body.b, body.loss, body.latency_ms)

    @app.delete("/api/lab/links/{a}/{b}")
    async def lab_remove_link(a: str, b: str):
        await lab.remove_link(a, b)
        return {"removed": [a, b]}

    @app.post("/api/lab/burst")
    async def lab_burst(body: BurstBody):
        return await lab.burst(body.src, body.dst, body.normal, body.service_ms)

    # ---- one node -----------------------------------------------------------------

    @app.get("/api/nodes/{node_id}")
    async def node_view(node_id: str):
        return lab.node_view(node_id)

    @app.post("/api/nodes/{node_id}/send")
    async def node_send(node_id: str, body: SendBody):
        return await lab.send(node_id, body.dst, body.text, body.priority, body.needs_ack)

    @app.post("/api/nodes/{node_id}/sos")
    async def node_sos(node_id: str, body: SosBody = SosBody()):
        return await lab.sos(node_id, body.text)

    @app.get("/api/nodes/{node_id}/graph")
    async def node_graph(node_id: str):
        return lab.graph_view(node_id)

    @app.get("/api/nodes/{node_id}/route")
    async def node_route(node_id: str, dst: str = Query(RESCUE_DST)):
        return lab.route_compare(node_id, dst)

    # ---- mesh-wide views ----------------------------------------------------------

    @app.get("/api/rescue")
    async def rescue():
        return lab.rescue_view()

    @app.get("/api/stats")
    async def stats():
        return lab.metrics()

    @app.get("/api/messages/{msg_id}")
    async def message(msg_id: str):
        return lab.message_detail(msg_id)

    @app.get("/api/events")
    async def events(limit: int = Query(100, ge=1, le=600)):
        return list(lab.recent_events)[-limit:]

    # ---- protocol inspector -------------------------------------------------------

    @app.get("/api/protocol/constants")
    async def protocol_constants():
        return protocol.constants()

    @app.post("/api/protocol/build")
    async def protocol_build(body: BuildPacketBody):
        return protocol.build(
            type_=body.type, priority=body.priority, src=body.src, dst=body.dst, ttl=body.ttl,
            hop_count=body.hop_count, path=body.path, text=body.text, needs_ack=body.needs_ack,
            store_forward_ok=body.store_forward_ok, encrypt=body.encrypt, sign=body.sign,
        )

    @app.post("/api/protocol/parse")
    async def protocol_parse(body: HexBody):
        return protocol.parse(body.hex)

    @app.post("/api/protocol/relay")
    async def protocol_relay(body: RelayBody):
        return protocol.relay_step(body.hex, body.relay)

    # ---- security -----------------------------------------------------------------

    @app.get("/api/security/info")
    async def security_info():
        return security_demo.info()

    @app.post("/api/security/seal")
    async def security_seal(body: SealBody):
        return security_demo.seal(body.text, body.key)

    @app.post("/api/security/open")
    async def security_open(body: OpenBody):
        return security_demo.open_(body.wire, body.key, body.tamper)

    @app.post("/api/security/sign")
    async def security_sign(body: SignBody):
        return security_demo.sign(body.message, body.who)

    @app.post("/api/security/verify")
    async def security_verify(body: VerifyBody):
        return security_demo.verify(body.message, body.public_key, body.signature)

    @app.post("/api/security/drill")
    async def security_drill():
        return await security_demo.attack_drill()

    # ---- simulator ----------------------------------------------------------------

    @app.get("/api/sim/scenarios")
    async def sim_scenarios():
        return [s.meta() for s in SCENARIOS.values()]

    @app.post("/api/sim/run")
    async def sim_run(body: SimRunBody):
        if body.scenario not in SCENARIOS:
            raise HTTPException(404, f"unknown scenario {body.scenario!r}")
        return jobs.submit(body.scenario, body.runs, body.nodes, body.loss, body.seed)

    @app.get("/api/sim/jobs")
    async def sim_jobs():
        return jobs.list()

    @app.get("/api/sim/jobs/{job_id}")
    async def sim_job(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "unknown job")
        return job

    # ---- live stream --------------------------------------------------------------

    @app.websocket("/ws")
    async def stream(ws: WebSocket):
        await ws.accept()
        queue = bus.subscribe()

        async def drain_client() -> None:
            try:
                while True:
                    await ws.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                pass

        reader = asyncio.create_task(drain_client())
        try:
            await ws.send_json({
                "type": "hello", "snapshot": lab.snapshot(),
                "events": list(lab.recent_events)[-80:], "actions": list(lab.actions)[-40:],
            })
            dirty, last_snapshot = False, time.monotonic()
            while not reader.done():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=0.4)
                    await ws.send_json(event)
                    dirty = True
                except asyncio.TimeoutError:
                    pass
                now = time.monotonic()
                if (dirty and now - last_snapshot >= 0.35) or now - last_snapshot >= 2.0:
                    await ws.send_json({"type": "snapshot", "snapshot": lab.snapshot()})
                    dirty, last_snapshot = False, now
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            reader.cancel()
            bus.unsubscribe(queue)

    # ---- the built UI ---------------------------------------------------------------

    if serve_ui:
        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa(full_path: str):
            if full_path.startswith(("api/", "ws")):
                raise HTTPException(404)
            if UI_DIST.exists():
                candidate = (UI_DIST / full_path).resolve()
                if full_path and candidate.is_file() and UI_DIST.resolve() in candidate.parents:
                    return FileResponse(candidate)
                return FileResponse(UI_DIST / "index.html")
            return JSONResponse({
                "detail": "UI not built yet. Run `npm install && npm run build` in ./ui, "
                          "or `npm run dev` there for the dev server (it proxies /api and /ws to this port).",
                "api_docs": "/docs",
            }, status_code=200)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="EcoMesh: API + UI server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--preset", default="demo5", choices=sorted(PRESETS))
    args = parser.parse_args()
    uvicorn.run(create_app(initial_preset=args.preset), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
