"""Non-functional measurements on the *real* engine: five operating-system
processes (one per device), real TCP sockets, real wall-clock timers.

    python docs/report/evidence/live_test.py            # all five devices on this machine (loopback)
    python docs/report/evidence/live_test.py --config story/mesh_two_laptops.json --only L1,L2,L3
        # ...with the other devices already running on a second laptop

This is the evidence for "running on multiple devices": every device is its
own process with its own SQLite log and its own socket, and they exchange
only bytes over TCP. Timings use HTTP polling of each device's own API, so
latencies carry up to one polling interval (20 ms) of measurement error.

Writes docs/report/evidence/results/live.json.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "results"
POLL = 0.02


def http(port, method, path, body=None, timeout=10, host="127.0.0.1"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://{host}:{port}{path}", method=method, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summary(values):
    return {"n": len(values), "median": pct(values, 0.5), "p95": pct(values, 0.95), "max": max(values) if values else None,
            "mean": statistics.fmean(values) if values else None}


def process_stats(pids):
    cmd = ("Get-Process -Id " + ",".join(map(str, pids)) +
           " | Select-Object Id,WorkingSet64,@{n='cpu';e={$_.TotalProcessorTime.TotalSeconds}} | ConvertTo-Json -Compress")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL, timeout=60).stdout
    rows = json.loads(out)
    return {r["Id"]: (r["WorkingSet64"] / 1e6, r["cpu"]) for r in (rows if isinstance(rows, list) else [rows])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "story" / "mesh.json"))
    parser.add_argument("--only", help="start only these devices locally; the others are assumed to be running elsewhere")
    parser.add_argument("--sos", type=int, default=30)
    parser.add_argument("--failovers", type=int, default=8)
    parser.add_argument("--flushes", type=int, default=4)
    args = parser.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    nodes = cfg["nodes"]
    ids = list(nodes)
    mine = args.only.split(",") if args.only else ids
    sender, rescue = ids[0], next(i for i, n in nodes.items() if n["role"] == "RESCUE")
    gateway = next(i for i, n in nodes.items() if n["role"] == "GATEWAY")
    web = {i: nodes[i]["web"] for i in ids}
    host = {i: ("127.0.0.1" if i in mine else nodes[i]["host"]) for i in ids}
    me = lambda i: http(web[i], "GET", "/api/me", host=host[i])
    power = lambda i, on: http(web[i], "POST", "/api/power", {"on": on}, host=host[i])

    procs, result = {}, {"devices": len(ids), "config": Path(args.config).name, "started_locally": mine}
    t_spawn = time.monotonic()
    for i in mine:
        procs[i] = subprocess.Popen([sys.executable, "-m", "story.node", "--id", i, "--config", args.config,
                                     "--web-host", "127.0.0.1"], cwd=ROOT, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pids = [p.pid for p in procs.values()]
    try:
        # ---- 1. convergence: process start -> every device knows every device, sender has a route to rescue
        deadline = time.monotonic() + 90
        converged = None
        while time.monotonic() < deadline:
            try:
                views = {i: me(i) for i in ids}
            except Exception:
                time.sleep(0.2)
                continue
            if all(all(n["known"] for n in v["nodes"]) for v in views.values()) and views[sender]["route"]:
                converged = time.monotonic() - t_spawn
                break
            time.sleep(0.1)
        assert converged, "mesh did not converge within 90 s"
        result["startup_to_full_convergence_s"] = round(converged, 2)
        result["route_sender_to_rescue"] = views[sender]["route"]
        print("converged in", round(converged, 2), "s; route", views[sender]["route"])
        time.sleep(5)

        # ---- 2. idle resource use
        a = process_stats(pids) if pids else {}
        t_a = time.monotonic()
        time.sleep(20)
        b = process_stats(pids) if pids else {}
        dt = time.monotonic() - t_a
        result["idle"] = {"seconds": round(dt, 1), "per_process": {
            i: {"working_set_mb": round(b[p.pid][0], 1), "cpu_percent_of_one_core": round(100 * (b[p.pid][1] - a[p.pid][1]) / dt, 2)}
            for i, p in procs.items()}}

        # ---- 3. end-to-end SOS latency, sequential
        def wait_for(pred, timeout=15):
            t0 = time.monotonic()
            while time.monotonic() - t0 < timeout:
                v = pred()
                if v:
                    return time.monotonic() - t0
                time.sleep(POLL)
            return None

        lat, ack_lat = [], []
        c0 = process_stats(pids) if pids else {}
        t_load0 = time.monotonic()
        for k in range(args.sos):
            tag = f"LATENCY-{k}-{int(time.time() * 1000)}"
            t0 = time.monotonic()
            res = http(web[sender], "POST", "/api/sos", {"text": tag}, host=host[sender])
            d = wait_for(lambda: any(m["body"] == tag for m in me(rescue)["thread"] if m["direction"] == "received"))
            if d is not None:
                lat.append((time.monotonic() - t0) * 1000)
            d2 = wait_for(lambda: any(m["body"] == tag and m["status"] == "delivered" for m in me(sender)["thread"] if m["direction"] == "sent"))
            if d2 is not None:
                ack_lat.append((time.monotonic() - t0) * 1000)
        load_dt = time.monotonic() - t_load0
        c1 = process_stats(pids) if pids else {}
        result["sos_latency_ms"] = {"arrive_at_rescue": summary(lat), "ack_back_at_sender": summary(ack_lat), "sent": args.sos,
                                    "delivered": len(lat), "acked": len(ack_lat)}
        result["under_load"] = {"seconds": round(load_dt, 1), "per_process": {
            i: {"working_set_mb": round(c1[p.pid][0], 1), "cpu_percent_of_one_core": round(100 * (c1[p.pid][1] - c0[p.pid][1]) / load_dt, 2)}
            for i, p in procs.items()}}
        print("SOS latency (ms):", result["sos_latency_ms"]["arrive_at_rescue"])

        # ---- 4. API response time (the UI refresh path)
        api_ms = []
        for _ in range(200):
            t0 = time.monotonic()
            me(rescue)
            api_ms.append((time.monotonic() - t0) * 1000)
        result["api_me_response_ms"] = summary(api_ms)

        # ---- 5. failover: kill the relay on the active path, time the re-route, then deliver
        failovers = []
        for k in range(args.failovers):
            route = me(sender)["route"]
            relays = [n for n in route[1:-1] if n != gateway]
            if not relays:
                break
            victim = relays[0]
            t0 = time.monotonic()
            power(victim, False)
            d = wait_for(lambda: (lambda r: r and victim not in r)(me(sender)["route"]), timeout=40)
            reroute_s = (time.monotonic() - t0) if d is not None else None
            tag = f"FAILOVER-{k}-{int(time.time() * 1000)}"
            http(web[sender], "POST", "/api/sos", {"text": tag}, host=host[sender])
            ok = wait_for(lambda: any(m["body"] == tag for m in me(rescue)["thread"] if m["direction"] == "received"), timeout=20)
            failovers.append({"victim": victim, "reroute_s": reroute_s, "delivered_after_failure": ok is not None})
            power(victim, True)
            wait_for(lambda: victim in me(sender)["hearing"] or victim in me(gateway)["hearing"], timeout=30)
            time.sleep(4)
        secs = [f["reroute_s"] for f in failovers if f["reroute_s"] is not None]
        result["failover"] = {"trials": failovers, "reroute_s": summary(secs),
                              "all_delivered": all(f["delivered_after_failure"] for f in failovers) if failovers else None}
        print("failover reroute (s):", result["failover"]["reroute_s"])

        # ---- 6. store-and-forward: gateway down, 5 SOS held, gateway back, all flush
        flushes = []
        for k in range(args.flushes):
            power(gateway, False)
            wait_for(lambda: not me(sender)["route"], timeout=30)
            tags = [f"HELD-{k}-{j}-{int(time.time() * 1000)}" for j in range(5)]
            for tg in tags:
                http(web[sender], "POST", "/api/sos", {"text": tg}, host=host[sender])
            time.sleep(1.0)
            held = me(sender)["held"]
            t0 = time.monotonic()
            power(gateway, True)
            got = wait_for(lambda: sum(1 for m in me(rescue)["thread"] if m["direction"] == "received" and m["body"] in tags) == 5, timeout=60)
            flushes.append({"held_before_restore": held, "all_five_delivered": got is not None,
                            "seconds_to_flush": (time.monotonic() - t0) if got is not None else None})
            wait_for(lambda: not me(sender)["held"] and me(sender)["route"], timeout=30)
            time.sleep(2)
        result["store_and_forward"] = {"trials": flushes,
                                       "seconds_to_flush": summary([f["seconds_to_flush"] for f in flushes if f["seconds_to_flush"] is not None]),
                                       "flush_rate": sum(f["all_five_delivered"] for f in flushes) / max(1, len(flushes))}
        print("flush:", result["store_and_forward"]["seconds_to_flush"])

        # ---- 7. security on the wire: nothing here, covered by unit tests; record the mesh settings used
        result["timing"] = {"hello_interval_s": 1.0, "neighbour_timeout_s": 4.0, "link_state_interval_s": 2.0,
                            "ack_timeout_s": 3.0, "max_retries": 3, "sf_retry_interval_s": 3.0}
        OUT.mkdir(exist_ok=True)
        (OUT / "live.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print("wrote results/live.json")
    finally:
        for p in procs.values():
            p.terminate()
        for p in procs.values():
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    main()
