"""Collect the measured evidence quoted in the project report.

    python docs/report/evidence/collect.py tests         # pytest -> tests.json
    python docs/report/evidence/collect.py scenarios     # every scenario, N runs each
    python docs/report/evidence/collect.py scale         # 10..60 nodes
    python docs/report/evidence/collect.py loss          # 0..40 % per-link loss
    python docs/report/evidence/collect.py throughput    # real-time messages/second
    python docs/report/evidence/collect.py all

Every number in Chapters 8-10 of the report comes from a JSON file written
here -- nothing is typed in by hand. Run from the repository root.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import subprocess
import sys
import time
import tracemalloc
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "results"
sys.path.insert(0, str(ROOT))


def save(name: str, data) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"wrote results/{name}.json")


# --- tests -----------------------------------------------------------------------------

def collect_tests(repeats: int = 3) -> None:
    """Run the whole suite ``repeats`` times. A test that passes in some runs and
    fails in others is reported as flaky rather than hidden."""
    OUT.mkdir(exist_ok=True)
    per_test: dict[tuple[str, str], list[str]] = {}
    times: dict[tuple[str, str], float] = {}
    runs = []
    for r in range(repeats):
        xml_path = OUT / f"pytest_{r}.xml"
        log_path = OUT / f"pytest_{r}.txt"
        started = time.time()
        # output goes to a file, not a pipe: the API tests leave worker processes
        # alive that would otherwise hold the pipe open and block forever
        with open(log_path, "w", encoding="utf-8") as log:
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml_path}"],
                                  cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=900)
        lines = [l for l in log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines() if l.strip()]
        runs.append({"run": r + 1, "wall_s": round(time.time() - started, 1), "exit_code": proc.returncode, "summary": lines[-1]})
        for case in ET.parse(xml_path).getroot().iter("testcase"):
            status = "failed" if (case.find("failure") is not None or case.find("error") is not None) else (
                "skipped" if case.find("skipped") is not None else "passed")
            key = (case.get("classname", "").split(".")[-1], case.get("name"))
            per_test.setdefault(key, []).append(status)
            times[key] = max(times.get(key, 0.0), float(case.get("time", 0)))
        print(" ", runs[-1])
    cases = [{"file": f, "name": n, "status": "passed" if all(x == "passed" for x in st) else (
              "flaky" if "passed" in st else "failed"), "results": st, "time_s": times[(f, n)]}
             for (f, n), st in per_test.items()]
    save("tests", {"repeats": repeats, "runs": runs, "cases": cases,
                   "flaky": [c["file"] + "::" + c["name"] for c in cases if c["status"] == "flaky"]})


# --- scenarios -------------------------------------------------------------------------

def _run(args):
    from sim.scenarios import run_once
    return run_once(*args)


def _raw(result: dict) -> dict:
    m = result["metrics"]
    return {"seed": result["seed"], "delivery": m["delivery_ratio"], "sent": m["sent"], "delivered": m["delivered"],
            "median_hops": m["median_hops"], "convergence_s": result["convergence_s"], "recovery_s": result["recovery_s"],
            "by_priority": m["by_priority"], "transmissions": m.get("transmissions"), "retries": m["retries"],
            "sf_queued": m["store_forward_queued"], "sf_flushed": m["store_forward_flushed"], "virtual_s": result["virtual_s"]}


def collect_scenarios(runs: int) -> None:
    from sim.scenarios import SCENARIOS, aggregate
    out = {}
    with ProcessPoolExecutor() as pool:
        for sc in SCENARIOS.values():
            modes = ["weighted", "hopcount"] if sc.compare_routing else ["weighted"]
            n = max(runs, 50) if sc.id == "collapse_40" else runs   # plan 24.4: recovery time "across 50 trials"
            out[sc.id] = {"title": sc.title, "summary": sc.summary, "nodes": sc.nodes, "loss": sc.loss,
                          "messages": sc.messages, "runs": n}
            for mode in modes:
                results = list(pool.map(_run, [(sc.id, 1 + i, None, None, mode) for i in range(n)]))
                out[sc.id][mode] = aggregate(results)
                out[sc.id][mode]["raw"] = [_raw(r) for r in results]
                print(f"  {sc.id:22} {mode:9} n={n} delivery {out[sc.id][mode]['delivery_ratio']['mean']:.1%}")
    save("scenarios", {"runs_per_scenario": runs, "scenarios": out})


# --- scale / loss sweeps --------------------------------------------------------------------

def _measured_run(args):
    """One run, with the Python heap peak and CPU time of the whole simulated mesh."""
    from sim.scenarios import run_once
    scenario, seed, nodes, loss = args
    tracemalloc.start()
    cpu0, t0 = time.process_time(), time.perf_counter()
    result = run_once(scenario, seed, nodes, loss, "weighted")
    cpu, wall = time.process_time() - cpu0, time.perf_counter() - t0
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    m = result["metrics"]
    return {"nodes": result["nodes"], "links": result["links"], "loss": result["loss"], "delivery": m["delivery_ratio"],
            "convergence_s": result["convergence_s"], "cpu_s": cpu, "wall_s": wall, "peak_mb": peak / 1e6,
            "sent": m["sent"], "delivered": m["delivered"], "transmissions": m.get("transmissions"),
            "by_priority": m["by_priority"], "median_hops": m["median_hops"]}


def _avg(values):
    values = [v for v in values if v is not None]
    return statistics.fmean(values) if values else None


def _sweep(scenario: str, points: list[tuple], runs: int) -> list[dict]:
    rows = []
    with ProcessPoolExecutor() as pool:
        for nodes, loss in points:
            res = list(pool.map(_measured_run, [(scenario, 100 + i, nodes, loss) for i in range(runs)]))
            conv = [r["convergence_s"] for r in res if r["convergence_s"] is not None]
            rows.append({
                "requested_nodes": nodes, "loss": loss, "nodes": res[0]["nodes"], "links": res[0]["links"], "runs": runs,
                "delivery_mean": statistics.fmean(r["delivery"] for r in res),
                "delivery_min": min(r["delivery"] for r in res),
                "convergence_mean_s": statistics.fmean(conv) if conv else None,
                "convergence_max_s": max(conv) if conv else None,
                "cpu_s_mean": statistics.fmean(r["cpu_s"] for r in res),
                "peak_mb_mean": statistics.fmean(r["peak_mb"] for r in res),
                "sent_per_run": statistics.fmean(r["sent"] for r in res),
                "overhead_tx_per_delivered": statistics.fmean(
                    r["transmissions"] / r["delivered"] for r in res if r["delivered"] and r["transmissions"] is not None),
                "median_hops": statistics.fmean(r["median_hops"] for r in res if r["median_hops"] is not None),
                "latency_ms": {
                    name: {"median": _avg([r["by_priority"][name]["median_latency_ms"] for r in res]),
                           "p95": _avg([r["by_priority"][name]["p95_latency_ms"] for r in res])}
                    for name in ("SOS", "NORMAL")},
            })
            print(f"  nodes={rows[-1]['nodes']:3} loss={loss:.2f} delivery={rows[-1]['delivery_mean']:.1%} "
                  f"conv={rows[-1]['convergence_mean_s']}")
    return rows


def collect_scale(runs: int) -> None:
    save("scale", _sweep("baseline_10", [(n, 0.05) for n in (10, 20, 30, 40, 50, 60)], runs))
    save("scale_lossy", _sweep("baseline_10", [(n, 0.20) for n in (10, 20, 30, 40, 50, 60)], runs))


def collect_loss(runs: int) -> None:
    save("loss", _sweep("baseline_10", [(20, p) for p in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)], runs))


# --- real-time engine throughput ---------------------------------------------------------------

async def _throughput(count: int) -> dict:
    from mesh.core.discovery import NodeRole
    from mesh.core.node import Node
    from mesh.core.packet import Priority
    from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport

    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B")
    net.set_link("B", "C")
    kw = dict(hello_interval=0.05, neighbour_timeout=0.5, link_state_interval=0.1, ack_timeout=2.0)
    a = Node("A", SimulatedTransport("A", net), **kw)
    b = Node("B", SimulatedTransport("B", net), **kw)
    c = Node("C", SimulatedTransport("C", net), role=NodeRole.GATEWAY, **kw)
    got = []
    c.on_deliver = got.append
    for n in (a, b, c):
        await n.start()
    await asyncio.sleep(0.5)

    t0 = time.perf_counter()
    await asyncio.gather(*(a.send("C", f"m{i}".encode(), priority=Priority.NORMAL, needs_ack=True) for i in range(count)))
    while len(got) < count and time.perf_counter() - t0 < 60:
        await asyncio.sleep(0.01)
    elapsed = time.perf_counter() - t0
    while len(a.ack_tracker) and time.perf_counter() - t0 < 60:
        await asyncio.sleep(0.01)
    ack_elapsed = time.perf_counter() - t0
    acked = count - len(a.ack_tracker)
    for n in (a, b, c):
        await n.stop()
    return {"messages": count, "delivered": len(got), "acked": acked, "seconds": round(elapsed, 3),
            "ack_seconds": round(ack_elapsed, 3), "msgs_per_s": round(len(got) / elapsed, 1)}


def collect_throughput() -> None:
    rows = []
    for count in (100, 500, 1000, 2000):
        row = asyncio.run(_throughput(count))
        print(" ", row)
        rows.append(row)
    save("throughput", rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("part", choices=["tests", "scenarios", "scale", "loss", "throughput", "all"])
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if args.part in ("tests", "all"):
        collect_tests()
    if args.part in ("scenarios", "all"):
        collect_scenarios(args.runs)
    if args.part in ("scale", "all"):
        collect_scale(min(args.runs, 10))
    if args.part in ("loss", "all"):
        collect_loss(min(args.runs, 10))
    if args.part in ("throughput", "all"):
        collect_throughput()
