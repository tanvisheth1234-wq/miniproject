"""The one-device program (story/node.py) driven through its HTTP API.

Each test starts real devices in this process: the real ``Node`` engine on
``LanTransport`` (real TCP on loopback) behind the FastAPI app, with the
demo's timers shortened so the mesh converges in about a second.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import time

import httpx
import pytest

import story.node as device

FAST = dict(HELLO_INTERVAL=0.1, NEIGHBOUR_TIMEOUT=0.8, PRUNE_INTERVAL=0.1, LINK_STATE_INTERVAL=0.2,
            ACK_TIMEOUT=1.0, ACK_POLL_INTERVAL=0.1, SF_RETRY_INTERVAL=0.5)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def line_config(roles: dict[str, str]) -> dict:
    """Devices in a line, in the order given: first - second - ... - last."""
    ids = list(roles)
    nodes = {i: {"role": roles[i], "label": f"Device {i}", "host": "127.0.0.1", "port": free_port(),
                 "web": free_port(), "x": n / max(1, len(ids) - 1), "y": 0.5} for n, i in enumerate(ids)}
    return {"nodes": nodes, "links": list(zip(ids, ids[1:]))}


@pytest.fixture
def fast_timers(monkeypatch):
    for name, value in FAST.items():
        monkeypatch.setattr(device, name, value)


@contextlib.asynccontextmanager
async def running(cfg: dict):
    """Start every device of ``cfg``; yield {id: httpx client}."""
    apps = {i: device.build_app(i, cfg, None, False) for i in cfg["nodes"]}
    async with contextlib.AsyncExitStack() as stack:
        clients = {}
        for i, app in apps.items():
            await stack.enter_async_context(app.router.lifespan_context(app))
            clients[i] = await stack.enter_async_context(
                httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=f"http://{i}"))
        yield clients


async def wait_for(check, timeout: float = 6.0, step: float = 0.1):
    """Poll an async condition until it returns something truthy."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await check()
        if result:
            return result
        await asyncio.sleep(step)
    raise AssertionError("condition not met within %.1f s" % timeout)


async def route_to_rescue(client):
    me = (await client.get("/api/me")).json()
    return me["route"] if me["route"] else None


@pytest.mark.asyncio
async def test_device_learns_a_multi_hop_route_to_the_rescue_team(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        route = await wait_for(lambda: route_to_rescue(dev["A"]))
        me = (await dev["A"].get("/api/me")).json()
    assert route == ["A", "B", "C"]
    assert me["hearing"] == ["B"]          # A only hears its configured neighbour
    assert me["web_url"].startswith("http://") and me["web_url"].endswith(str(cfg["nodes"]["A"]["web"]))


def test_lan_ip_is_a_usable_ipv4_address():
    ip = device.lan_ip()
    assert len(ip.split(".")) == 4 and all(part.isdigit() for part in ip.split("."))


@pytest.mark.asyncio
async def test_events_show_the_neighbour_coming_up_and_since_filters(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        async def peer_up_seen():
            body = (await dev["A"].get("/api/events")).json()
            ups = [e for e in body["events"] if e["kind"] == "peer_up"]
            return body if ups else None

        first = await wait_for(peer_up_seen)
        later = (await dev["A"].get("/api/events", params={"since": first["now_ms"]})).json()
        bad = await dev["A"].get("/api/events", params={"limit": 0})

    ups = [e for e in first["events"] if e["kind"] == "peer_up"]
    assert {e["peer"] for e in ups} == {"B"}                       # only the configured neighbour
    assert set(first["events"][0]) == {"ts_ms", "kind", "peer", "msg_id", "detail"}
    times = [e["ts_ms"] for e in first["events"]]
    assert times == sorted(times)                                   # oldest first
    assert all(e["ts_ms"] > first["now_ms"] for e in later["events"])
    assert bad.status_code == 422
