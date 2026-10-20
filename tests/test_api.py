"""The Phase 4 API, driven through FastAPI's test client against a lab of
real nodes (fast timers, so the mesh converges in a second)."""

import time

import pytest
from fastapi.testclient import TestClient

from api.lab import FAST, MeshLab
from api.server import create_app


def wait_for(predicate, timeout=6.0, step=0.1):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("condition not met in time")


@pytest.fixture(scope="module")
def client():
    app = create_app(lab=MeshLab(None, timing=FAST), serve_ui=False)
    with TestClient(app) as c:
        wait_for(lambda: all(n["known_nodes"] == 5 for n in c.get("/api/lab").json()["nodes"]))
        yield c


def test_snapshot_describes_a_converged_mesh(client):
    snap = client.get("/api/lab").json()
    assert {n["id"] for n in snap["nodes"]} == {"L1", "L2", "L3", "L4", "L5"}
    assert all(n["online"] for n in snap["nodes"])
    assert snap["stats"]["nodes_online"] == 5
    assert len(snap["links"]) == 5


def test_presets_and_scenarios_are_listed(client):
    assert "demo5" in {p["id"] for p in client.get("/api/presets").json()}
    assert "hopcount_vs_weighted" in {s["id"] for s in client.get("/api/sim/scenarios").json()}


def test_sos_reaches_the_rescue_queue_and_the_sender_sees_it_delivered(client):
    sent = client.post("/api/nodes/L1/sos").json()
    assert sent["priority_name"] == "SOS"

    item = wait_for(lambda: next((m for m in client.get("/api/rescue").json()["sos_queue"]
                                  if m["msg_id"] == sent["msg_id"]), None))
    assert item["sender"] == "L1" and item["received_by"] in ("L4", "L5")

    wait_for(lambda: client.get(f"/api/messages/{sent['msg_id']}").json()["origin"]["status"] == "delivered")
    detail = client.get(f"/api/messages/{sent['msg_id']}").json()
    assert detail["route"][0] == "L1" and detail["route"][-1] == item["received_by"]
    assert {e["kind"] for e in detail["events"]} >= {"sent", "recv", "ack"}


def test_node_view_reports_peers_with_hop_distance(client):
    view = client.get("/api/nodes/L1").json()
    assert view["nearby"] == 2
    hops = {p["id"]: p["hops"] for p in view["reachable"]}
    assert hops["L2"] == 1 and hops["L4"] == 2 and hops["L5"] == 3
    assert view["rescue_route"]["hops"] >= 2


def test_route_compare_returns_both_routers(client):
    out = client.get("/api/nodes/L1/route", params={"dst": "L5"}).json()
    assert out["weighted"]["path"][0] == "L1" and out["weighted"]["path"][-1] == "L5"
    assert out["hop_count"]["hops"] == 3


def test_bad_requests_get_clear_errors(client):
    assert client.post("/api/nodes/NOPE/send", json={"dst": "L2", "text": "x"}).status_code == 404
    assert client.post("/api/nodes/L1/send", json={"dst": "L1", "text": "x"}).status_code == 400
    assert client.post("/api/nodes/L1/send", json={"dst": "L2", "text": ""}).status_code == 422
    assert client.post("/api/nodes/L1/send", json={"dst": "L2", "text": "x", "priority": 9}).status_code == 400


def test_killing_a_node_reroutes_and_reviving_restores_it(client):
    assert client.post("/api/lab/nodes/L3/kill").status_code == 200
    assert client.post("/api/nodes/L3/sos").status_code == 409          # a switched-off node can't send
    snap = client.get("/api/lab").json()
    assert next(n for n in snap["nodes"] if n["id"] == "L3")["online"] is False

    wait_for(lambda: "L3" not in [p["id"] for p in client.get("/api/nodes/L1").json()["reachable"]])
    sent = client.post("/api/nodes/L1/sos").json()                       # still gets out, via L2
    wait_for(lambda: client.get(f"/api/messages/{sent['msg_id']}").json()["origin"]["status"] == "delivered")

    assert client.post("/api/lab/nodes/L3/revive").status_code == 200
    wait_for(lambda: "L3" in [p["id"] for p in client.get("/api/nodes/L1").json()["reachable"]])


def test_websocket_streams_a_hello_snapshot_then_events(client):
    with client.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello" and len(hello["snapshot"]["nodes"]) == 5
        client.post("/api/nodes/L2/send", json={"dst": "L4", "text": "ping"})
        seen = set()
        for _ in range(60):
            msg = ws.receive_json()
            if msg["type"] == "event":
                seen.add(msg["kind"])
            if {"sent", "recv"} <= seen:
                break
        assert {"sent", "recv"} <= seen


def test_protocol_inspector_builds_and_parses_real_packets(client):
    built = client.post("/api/protocol/build", json={"text": "help", "priority": 0, "encrypt": True, "sign": True}).json()
    assert built["fields"][0]["value"].startswith("0x4D45")
    assert [r["name"] for r in built["regions"]] == ["header", "payload", "signature"]
    assert built["summary"]["flags"] == ["encrypted", "needs_ack", "store_forward_ok", "signed"] or "encrypted" in built["summary"]["flags"]
    parsed = client.post("/api/protocol/parse", json={"hex": built["hex"]}).json()
    assert parsed["summary"]["msg_id"] == built["summary"]["msg_id"]
    assert client.post("/api/protocol/parse", json={"hex": "zz"}).status_code == 400
    assert client.post("/api/protocol/parse", json={"hex": "00" * 10}).status_code == 400

    step = client.post("/api/protocol/relay", json={"hex": built["hex"], "relay": "L2"}).json()
    assert step["after"]["summary"]["ttl"] == step["before"]["summary"]["ttl"] - 1
    assert step["after"]["payload_hex"] == step["before"]["payload_hex"]


def test_security_playground_round_trips_and_detects_tampering(client):
    sealed = client.post("/api/security/seal", json={"text": "room 302"}).json()
    ok = client.post("/api/security/open", json={"wire": sealed["wire"]}).json()
    assert ok["ok"] and ok["plaintext"] == "room 302"
    bad = client.post("/api/security/open", json={"wire": sealed["wire"], "tamper": True}).json()
    assert bad["ok"] is False

    sig = client.post("/api/security/sign", json={"message": "SOS", "who": "alice"}).json()
    good = client.post("/api/security/verify", json={"message": "SOS", "public_key": sig["public_key"], "signature": sig["signature"]})
    assert good.json()["valid"] is True
    forged = client.post("/api/security/verify", json={"message": "SOS!", "public_key": sig["public_key"], "signature": sig["signature"]})
    assert forged.json()["valid"] is False


def test_attack_drill_defends_every_attack(client):
    steps = client.post("/api/security/drill").json()["steps"]
    assert [s["defended"] for s in steps] == [True, True, True, True]


def test_reset_swaps_the_preset_and_security_options(client):
    snap = client.post("/api/lab/reset", json={"preset": "chain6", "encryption": True, "signing": True}).json()
    assert snap["config"]["encryption"] and snap["config"]["signing"]
    assert len(snap["nodes"]) == 6
    wait_for(lambda: all(n["known_nodes"] == 6 for n in client.get("/api/lab").json()["nodes"]), timeout=10)
    sent = client.post("/api/nodes/C1/sos").json()
    wait_for(lambda: client.get(f"/api/messages/{sent['msg_id']}").json()["origin"]["status"] == "delivered", timeout=10)
    detail = client.get(f"/api/messages/{sent['msg_id']}").json()
    assert detail["hops"] == 4
    assert detail["wire"]["encrypted"] and detail["wire"]["signed"]
    assert "SOS" not in bytes.fromhex(detail["wire"]["payload_hex"]).decode("latin-1")   # relays saw ciphertext
    assert client.post("/api/lab/reset", json={"preset": "nope"}).status_code == 404
    client.post("/api/lab/reset", json={"preset": "demo5"})
