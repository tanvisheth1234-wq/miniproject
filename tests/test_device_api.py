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


async def thread_entry(client, msg_id):
    thread = (await client.get("/api/me")).json()["thread"]
    return next((m for m in thread if m["msg_id"] == msg_id), None)


@pytest.mark.asyncio
async def test_send_delivers_a_text_message_across_the_mesh(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        await wait_for(lambda: route_to_rescue(dev["A"]))
        sent = await dev["A"].post("/api/send", json={"dst": "C", "text": "Two of us on floor 3"})
        msg_id = sent.json()["msg_id"]
        received = await wait_for(lambda: thread_entry(dev["C"], msg_id))

        async def delivered():
            entry = await thread_entry(dev["A"], msg_id)
            return entry if entry and entry["status"] == "delivered" else None

        at_sender = await wait_for(delivered)
    assert sent.status_code == 200
    assert received["body"] == "Two of us on floor 3"
    assert received["priority_name"] == "NORMAL"
    assert at_sender["status"] == "delivered"


@pytest.mark.asyncio
async def test_send_rejects_bad_requests(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "RESCUE"})
    async with running(cfg) as dev:
        unknown = await dev["A"].post("/api/send", json={"dst": "ZZ", "text": "hello"})
        empty = await dev["A"].post("/api/send", json={"dst": "B", "text": "   "})
        to_self = await dev["A"].post("/api/send", json={"dst": "A", "text": "hello"})
        bad_priority = await dev["A"].post("/api/send", json={"dst": "B", "text": "hi", "priority": "LOUD"})
        await dev["A"].post("/api/power", json={"on": False})
        switched_off = await dev["A"].post("/api/send", json={"dst": "B", "text": "hello"})
    assert unknown.status_code == 404
    assert empty.status_code == 400
    assert to_self.status_code == 400
    assert bad_priority.status_code == 400
    assert switched_off.status_code == 409


@pytest.mark.asyncio
async def test_history_filters_by_priority_and_direction(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        await wait_for(lambda: route_to_rescue(dev["A"]))
        sos = (await dev["A"].post("/api/sos", json={"text": "trapped"})).json()["msg_id"]
        note = (await dev["A"].post("/api/send", json={"dst": "C", "text": "hello"})).json()["msg_id"]

        async def both_received():
            got = (await dev["C"].get("/api/history", params={"direction": "received"})).json()["messages"]
            return got if {m["msg_id"] for m in got} == {sos, note} else None

        received = await wait_for(both_received)
        only_sos = (await dev["C"].get("/api/history", params={"kind": "SOS"})).json()["messages"]
        relay = (await dev["B"].get("/api/history", params={"direction": "forwarded"})).json()["messages"]
        sent_normal = (await dev["A"].get("/api/history", params={"kind": "normal", "direction": "sent"})).json()["messages"]
        bad_kind = await dev["A"].get("/api/history", params={"kind": "URGENT"})
        bad_direction = await dev["A"].get("/api/history", params={"direction": "sideways"})

    assert [m["msg_id"] for m in received] == [note, sos]          # newest first
    assert [m["msg_id"] for m in only_sos] == [sos]
    assert {m["msg_id"] for m in relay} == {sos, note}
    assert all(m["body"] is None for m in relay)                    # a relay keeps no message text
    assert [m["msg_id"] for m in sent_normal] == [note]
    assert bad_kind.status_code == 400 and bad_direction.status_code == 400


def test_payload_parsing_handles_structured_and_plain_text():
    structured = device.structured_payload("Two of us", "Injured", "Stairwell B")
    assert device.parse_payload(structured) == {"text": "Two of us", "need": "Injured", "where": "Stairwell B"}
    assert device.parse_payload("trapped, need help") == {"text": "trapped, need help", "need": "", "where": ""}
    assert device.parse_payload('{"no": "version"}')["text"] == '{"no": "version"}'   # not ours: shown raw
    assert device.parse_payload(None) == {"text": None, "need": "", "where": ""}


@pytest.mark.asyncio
async def test_structured_sos_round_trip_and_plain_sos_still_works(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        await wait_for(lambda: route_to_rescue(dev["A"]))
        rich = (await dev["A"].post("/api/sos", json={"text": "Two of us", "need": "Injured",
                                                       "where": "3rd floor"})).json()["msg_id"]
        plain = (await dev["A"].post("/api/sos", json={"text": "trapped"})).json()["msg_id"]
        at_rescue = await wait_for(lambda: thread_entry(dev["C"], rich))
        plain_at_rescue = await wait_for(lambda: thread_entry(dev["C"], plain))
        at_sender = await thread_entry(dev["A"], rich)
        history = (await dev["C"].get("/api/history", params={"kind": "SOS"})).json()["messages"]
    assert (at_rescue["body"], at_rescue["need"], at_rescue["where"]) == ("Two of us", "Injured", "3rd floor")
    assert (plain_at_rescue["body"], plain_at_rescue["need"], plain_at_rescue["where"]) == ("trapped", "", "")
    assert at_sender["need"] == "Injured"                     # the sender's own copy reads the same way
    assert {m["need"] for m in history} == {"Injured", ""}


@pytest.mark.asyncio
async def test_safe_check_in_reaches_rescue_at_status_priority(fast_timers):
    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        await wait_for(lambda: route_to_rescue(dev["A"]))
        reply = await dev["A"].post("/api/safe", json={"where": "Assembly point"})
        entry = await wait_for(lambda: thread_entry(dev["C"], reply.json()["msg_id"]))
        bare = await dev["A"].post("/api/safe")
    assert reply.status_code == 200 and bare.status_code == 200
    assert entry["priority_name"] == "STATUS"
    assert (entry["need"], entry["where"], entry["body"]) == ("Safe", "Assembly point", "Device A is safe")


def test_a_safe_check_in_never_overtakes_an_sos():
    from mesh.core.packet import Packet, PacketType, Priority
    from mesh.core.reliability import MessagePriorityQueue

    queue = MessagePriorityQueue()
    safe = Packet(type=PacketType.DATA, priority=Priority.STATUS, src="A", dst="C", payload=b"safe")
    sos = Packet(type=PacketType.DATA, priority=Priority.SOS, src="B", dst="C", payload=b"sos")
    queue.push(safe)            # the check-in was queued first ...
    queue.push(sos)
    assert queue.pop() is sos   # ... but the SOS leaves first


@pytest.mark.asyncio
async def test_rescue_exports_received_requests_as_csv(fast_timers):
    import csv
    import io

    cfg = line_config({"A": "NORMAL", "B": "GATEWAY", "C": "RESCUE"})
    async with running(cfg) as dev:
        await wait_for(lambda: route_to_rescue(dev["A"]))
        sos = (await dev["A"].post("/api/sos", json={"text": "Two of us", "need": "Injured",
                                                      "where": "3rd floor, room 304"})).json()["msg_id"]
        await wait_for(lambda: thread_entry(dev["C"], sos))
        export = await dev["C"].get("/api/export.csv")
        refused = await dev["A"].get("/api/export.csv")
    rows = list(csv.reader(io.StringIO(export.text)))
    assert export.status_code == 200 and export.headers["content-type"].startswith("text/csv")
    assert rows[0] == ["time", "from", "priority", "need", "where", "hops", "route", "message"]
    assert len(rows) == 2                                           # header + the one request
    assert rows[1][1:8] == ["Device A", "SOS", "Injured", "3rd floor, room 304", "2",
                            "Device A > Device B > Device C", "Two of us"]
    assert refused.status_code == 403
