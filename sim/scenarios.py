"""The simulator's scenario model and the six required scenarios of
section 15, plus one for section 9.1's priority claim.

A scenario names a topology, a loss rate, a message workload and a script of
failures. ``run_once`` builds the mesh from real ``Node`` objects over
``SimulatedTransport``, plays the script on a *virtual* clock (so the spec's
real 3 s HELLO / 10 s timeout / 4 s ACK values run in a fraction of a
second), and reads every number back out of the nodes' SQLite logs.

    python -m sim.scenarios --scenario baseline_10 --runs 10
    python -m sim.scenarios --scenario hopcount_vs_weighted --runs 20
    python -m sim.scenarios --list
"""

from __future__ import annotations

import argparse
import asyncio
import math
import random
import statistics
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Optional

from api.lab import SPEC, MeshLab
from api.metrics import compute_metrics
from api.presets import LATENCY_MS, LinkSpec, NodeSpec, Preset, _grid
from api.vtime import run_virtual
from mesh.core.discovery import NodeRole
from mesh.core.packet import RESCUE_DST, Priority

SIM_LATENCY_MS = (5.0, 40.0)  # section 15's example latency range


# --- topologies -----------------------------------------------------------------------

def grid_topology(nodes: int, loss: float) -> Preset:
    rows = max(2, round(math.sqrt(nodes)))
    cols = max(2, math.ceil((nodes - 1) / rows))  # -1: the gateway and rescue post are added on top
    preset_nodes, links, sender = _grid(rows, cols, loss, (rows - 1, cols - 1))
    return Preset("sim_grid", f"{rows}x{cols} grid", "", preset_nodes, links, sender=sender)


def chain_topology(nodes: int, loss: float) -> Preset:
    ids = [f"C{i}" for i in range(1, nodes)] + ["G1"]
    specs = [NodeSpec(i, NodeRole.GATEWAY if i == "G1" else NodeRole.NORMAL, "", 0.05 + 0.9 * k / (len(ids) - 1), 0.5)
             for k, i in enumerate(ids)]
    links = [LinkSpec(a, b, loss=loss) for a, b in zip(ids, ids[1:])]
    return Preset("sim_chain", f"{nodes}-node chain", "", specs, links, sender="C1")


def no_gateway_topology(nodes: int, loss: float) -> Preset:
    preset = grid_topology(nodes, loss)
    keep = [n for n in preset.nodes if n.node_id not in ("G1", "R1")]
    ids = {n.node_id for n in keep}
    links = [l for l in preset.links if l.a in ids and l.b in ids]
    return Preset("sim_nogw", "grid, no gateway", "", keep, links, sender=preset.sender)


def flaky_shortcut_topology(nodes: int, loss: float) -> Preset:
    """Two ways from S to the gateway. The short one (2 hops) crosses a link
    that drops ``loss`` of packets; the long one (3 hops) is clean. Hop-count
    routing takes the short one every time."""
    specs = [
        NodeSpec("S", NodeRole.NORMAL, "Sender", 0.05, 0.5), NodeSpec("M", NodeRole.NORMAL, "Shortcut", 0.40, 0.18),
        NodeSpec("X", NodeRole.NORMAL, "Clean 1", 0.30, 0.82), NodeSpec("Y", NodeRole.NORMAL, "Clean 2", 0.65, 0.82),
        NodeSpec("G1", NodeRole.GATEWAY, "Gateway", 0.95, 0.5),
    ]
    links = [LinkSpec("S", "M"), LinkSpec("M", "G1", loss=loss), LinkSpec("S", "X"), LinkSpec("X", "Y"), LinkSpec("Y", "G1")]
    return Preset("sim_flaky", "flaky shortcut", "", specs, links, sender="S")


# --- scenario model --------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    summary: str
    build: Callable[[int, float], Preset]
    nodes: int
    loss: float
    messages: int
    sos_fraction: float = 0.3
    events: tuple[dict, ...] = ()
    warmup: float = 30.0
    traffic_window: float = 40.0
    settle: float = 40.0
    best_effort: bool = False       # no ACK, no retry: raw per-link loss shows through
    radio_service_ms: float = 0.0
    compare_routing: bool = False   # run weighted and hop-count on identical seeds
    sender_only: bool = False       # all traffic from the preset's designated sender
    all_to_rescue: bool = False     # every message (SOS or not) goes to RESCUE__: the only fair way to compare latencies

    def meta(self) -> dict:
        return {"id": self.id, "title": self.title, "summary": self.summary, "nodes": self.nodes, "loss": self.loss,
                "messages": self.messages, "compare_routing": self.compare_routing,
                "events": [f"t+{e['t']:g}s {e['do']} {e.get('target', '')}".strip() for e in self.events]}


SCENARIOS: dict[str, Scenario] = {s.id: s for s in (
    Scenario(
        "baseline_10", "Baseline, 10 nodes", "A small, healthy mesh: the reference for every other scenario.",
        grid_topology, nodes=10, loss=0.05, messages=16,
    ),
    Scenario(
        "collapse_40", "Collapse, 40 nodes",
        "Forty nodes at 20% loss. A relay on the active path dies at t=10, the gateway at t=25 (every SOS must "
        "queue), and the gateway returns at t=60 (they must flush).",
        grid_topology, nodes=40, loss=0.20, messages=30, traffic_window=70.0, settle=60.0,
        events=({"t": 10, "do": "kill", "target": "@on_path"},
                {"t": 25, "do": "kill", "target": "@gateway", "as": "gw"},
                {"t": 60, "do": "revive", "target": "gw"}),
    ),
    Scenario(
        "no_gateway", "No gateway",
        "No node has an uplink. SOS messages are retained in store-and-forward until a rescue team walks into "
        "range at t=45, then everything flushes at once.",
        no_gateway_topology, nodes=12, loss=0.05, messages=10, sos_fraction=1.0, traffic_window=30.0, settle=60.0,
        events=({"t": 45, "do": "rescue_walks_in"},),
    ),
    Scenario(
        "high_loss", "High loss", "Twenty nodes with 35% loss on every link: ACK, retry and rerouting under stress.",
        grid_topology, nodes=20, loss=0.35, messages=24, settle=60.0,
    ),
    Scenario(
        "chain_10hop", "Ten-hop chain", "A single line of eleven nodes: the longest path the TTL of 10 allows.",
        chain_topology, nodes=11, loss=0.05, messages=12, sender_only=True,
    ),
    Scenario(
        "hopcount_vs_weighted", "Weighted vs hop-count routing",
        "Same topology, same seeds, same traffic, two routers. The short path crosses a lossy link; the long path is "
        "clean. Messages are best-effort, so a bad choice shows up directly as lost messages.",
        flaky_shortcut_topology, nodes=5, loss=0.45, messages=40, sos_fraction=0.0, best_effort=True,
        compare_routing=True, warmup=60.0, sender_only=True, traffic_window=60.0, settle=15.0,
    ),
    Scenario(
        "priority_load", "SOS under load",
        "A slow radio (one packet per 80 ms) and a burst of routine traffic, all heading for the same gateway: "
        "does an SOS still overtake it at every hop?",
        grid_topology, nodes=16, loss=0.0, messages=90, sos_fraction=0.15, traffic_window=3.0, settle=40.0,
        radio_service_ms=80.0, all_to_rescue=True,
    ),
)}


# --- running one scenario --------------------------------------------------------------

async def _converged(lab: MeshLab, cap: float) -> Optional[float]:
    """Seconds until every node's graph holds every node (section 16: ≤ 15 s)."""
    start = time.monotonic()
    while time.monotonic() - start < cap:
        want = set(lab.specs)
        if all(want <= n.graph.reachable_from(n.node_id) for n in lab.nodes.values()):
            return time.monotonic() - start
        await asyncio.sleep(0.25)
    return None


async def _watch_recovery(lab: MeshLab, source: str, victim: str, cap: float = 40.0) -> Optional[float]:
    """Seconds from ``victim`` dying until ``source`` again has a route to
    the gateway that doesn't use it."""
    start = time.monotonic()
    while time.monotonic() - start < cap:
        node = lab.nodes.get(source)
        path = node.router.shortest_path(RESCUE_DST) if node is not None else None
        if path is not None and victim not in path:
            return time.monotonic() - start
        await asyncio.sleep(0.25)
    return None


def _pick_victim(lab: MeshLab, source: str) -> Optional[str]:
    node = lab.nodes.get(source)
    path = node.router.shortest_path(RESCUE_DST) if node is not None else None
    if path is None or len(path) < 3:
        return None
    return path[len(path) // 2] if len(path) == 3 else path[1]


async def _run(sc: Scenario, seed: int, nodes: Optional[int], loss: Optional[float], routing: str) -> dict:
    rng = random.Random(seed)
    preset = sc.build(nodes or sc.nodes, sc.loss if loss is None else loss)
    for link in preset.links:
        link.latency_ms = SIM_LATENCY_MS
    lab = MeshLab(None, timing=SPEC)
    await lab.load(preset=preset, routing=routing, radio_service_ms=sc.radio_service_ms, seed=seed)

    sender = preset.sender
    sources = [n.node_id for n in preset.nodes if n.role == NodeRole.NORMAL and n.node_id != sender] or [sender]
    if sc.sender_only:
        sources = [sender]
    aliases: dict[str, str] = {}
    recovery: list[Optional[float]] = []
    watchers: list[asyncio.Task] = []
    sends: list[asyncio.Task] = []

    convergence = await _converged(lab, sc.warmup)
    await asyncio.sleep(max(0.0, sc.warmup - (convergence or 0.0)))
    t0 = time.monotonic()

    async def at(t: float, coro_fn) -> None:
        await asyncio.sleep(max(0.0, t - (time.monotonic() - t0)))
        await coro_fn()

    async def send_one() -> None:
        src = rng.choice([s for s in sources if lab.is_online(s)] or [sender])
        if not lab.is_online(src):
            return
        sos = rng.random() < sc.sos_fraction
        if sos or not [s for s in sources if s != src]:
            dst, prio = RESCUE_DST, Priority.SOS
        else:
            dst, prio = rng.choice([s for s in sources if s != src]), Priority.NORMAL
        if sc.best_effort or sc.sender_only or sc.all_to_rescue:
            dst, prio = RESCUE_DST, (Priority.SOS if sos else Priority.NORMAL)
        try:
            await lab.send(src, dst, f"sim {src}->{dst}", prio, needs_ack=not sc.best_effort)
        except Exception:
            pass  # a node that's switched off at that instant simply doesn't get to send

    def resolve(target: str) -> Optional[str]:
        if target in aliases:
            return aliases[target]
        if target == "@gateway":
            return next((n.node_id for n in preset.nodes if n.role == NodeRole.GATEWAY), None)
        if target == "@on_path":
            return _pick_victim(lab, sender)
        return target if target in lab.specs else None

    def make_event(ev: dict):
        async def fire() -> None:
            if ev["do"] == "rescue_walks_in":
                anchor = rng.choice(sorted(lab.nodes))
                await lab.add_node("R9", NodeRole.RESCUE, "Rescue team", links=[anchor])
                return
            victim = resolve(ev["target"])
            if victim is None:
                return
            if "as" in ev:
                aliases[ev["as"]] = victim
            if ev["do"] == "kill":
                if ev["target"] == "@on_path":
                    watchers.append(asyncio.create_task(_watch_recovery(lab, sender, victim)))
                await lab.kill(victim)
            elif ev["do"] == "revive":
                await lab.revive(victim)
        return fire

    tasks = [asyncio.create_task(at(1.0 + rng.uniform(0, sc.traffic_window), send_one)) for _ in range(sc.messages)]
    sends.extend(tasks)
    event_tasks = [asyncio.create_task(at(ev["t"], make_event(ev))) for ev in sc.events]
    await asyncio.gather(*sends, *event_tasks)
    await asyncio.sleep(sc.settle)
    for w in watchers:
        recovery.append(await w)

    metrics = compute_metrics(lab.stores)
    out = {
        "scenario": sc.id, "seed": seed, "routing": routing, "nodes": len(lab.specs), "links": len(lab.links),
        "loss": sc.loss if loss is None else loss, "metrics": metrics, "convergence_s": convergence,
        "recovery_s": next((r for r in recovery if r is not None), None) if recovery else None,
        "fair_priority": sc.all_to_rescue,
        "virtual_s": round(time.monotonic() - t0 + sc.warmup, 1),
    }
    await lab.shutdown()
    return out


def run_once(sc_id: str, seed: int = 1, nodes: Optional[int] = None, loss: Optional[float] = None,
             routing: str = "weighted") -> dict:
    """One full scenario run on a virtual clock. Top-level and picklable, so
    the API's process pool can call it directly."""
    started = time.perf_counter()
    result = run_virtual(_run, SCENARIOS[sc_id], seed, nodes, loss, routing)
    result["wall_s"] = round(time.perf_counter() - started, 2)
    return result


# --- aggregation -----------------------------------------------------------------------

def _stats(values: list[float]) -> Optional[dict]:
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"mean": statistics.fmean(values), "min": min(values), "max": max(values),
            "stdev": statistics.pstdev(values) if len(values) > 1 else 0.0, "n": len(values)}


def aggregate(results: list[dict]) -> dict:
    """Pool a list of runs (all one scenario, one routing mode) into the
    section 16 table."""
    if not results:
        return {}
    ratios = [r["metrics"]["delivery_ratio"] for r in results]
    hops: Counter = Counter()
    lat: dict[str, list[float]] = {"SOS": [], "NORMAL": [], "STATUS": []}
    queued = flushed = retries = dup = 0
    dup_ratios = []
    for r in results:
        m = r["metrics"]
        for h, n in m["hop_histogram"].items():
            hops[int(h)] += n
        for name in lat:
            mid = m["by_priority"][name]["median_latency_ms"]
            if mid is not None:
                lat[name].append(mid)
        queued += m["store_forward_queued"]
        flushed += m["store_forward_flushed"]
        retries += m["retries"]
        if m["dedup_drop_ratio"] is not None:
            dup_ratios.append(m["dedup_drop_ratio"])
    all_hops = sorted(h for h, n in hops.items() for _ in range(n))
    sos_med = statistics.median(lat["SOS"]) if lat["SOS"] else None
    normal_med = statistics.median(lat["NORMAL"]) if lat["NORMAL"] else None
    return {
        "runs": len(results),
        "delivery_ratio": _stats(ratios),
        "median_hops": statistics.median(all_hops) if all_hops else None,
        "mean_hops": statistics.fmean(all_hops) if all_hops else None,
        "hop_histogram": dict(sorted(hops.items())),
        "latency_ms": {k: (statistics.median(v) if v else None) for k, v in lat.items()},
        # only meaningful when SOS and NORMAL took the same trip; otherwise it
        # compares different destinations and says nothing about priority
        "sos_latency_advantage": (normal_med / sos_med) if sos_med and normal_med and results[0].get("fair_priority") else None,
        "recovery_s": _stats([r["recovery_s"] for r in results]),
        "convergence_s": _stats([r["convergence_s"] for r in results]),
        "store_forward": {"queued": queued, "flushed": flushed, "flush_ratio": (flushed / queued) if queued else None},
        "retries_per_run": retries / len(results),
        "dedup_drop_ratio": statistics.fmean(dup_ratios) if dup_ratios else None,
        "wall_s": sum(r.get("wall_s", 0) for r in results),
    }


def format_report(sc: Scenario, summaries: dict[str, dict]) -> str:
    lines = [f"{sc.id}: {sc.title}", ""]
    for mode, s in summaries.items():
        dr = s["delivery_ratio"]
        lines.append(f"[{mode}] {s['runs']} runs — delivery {dr['mean']:.1%} (min {dr['min']:.0%}, max {dr['max']:.0%})"
                     + (f", median hops {s['median_hops']:g}" if s["median_hops"] is not None else ""))
        if s["sos_latency_advantage"]:
            lines.append(f"    SOS latency {s['latency_ms']['SOS']:.0f} ms vs NORMAL {s['latency_ms']['NORMAL']:.0f} ms "
                         f"= {s['sos_latency_advantage']:.1f}x faster")
        if s["recovery_s"]:
            lines.append(f"    recovery after relay death: {s['recovery_s']['mean']:.1f} s")
        if s["convergence_s"]:
            lines.append(f"    convergence: {s['convergence_s']['mean']:.1f} s")
        sf = s["store_forward"]
        if sf["queued"]:
            lines.append(f"    store-and-forward: {sf['flushed']}/{sf['queued']} flushed")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an EcoMesh simulation scenario on a virtual clock.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--nodes", type=int, default=None)
    parser.add_argument("--loss", type=float, default=None)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list or not args.scenario:
        for sc in SCENARIOS.values():
            print(f"{sc.id:22} {sc.title} — {sc.summary}")
        return
    sc = SCENARIOS[args.scenario]
    modes = ["weighted", "hopcount"] if sc.compare_routing else ["weighted"]
    summaries = {}
    for mode in modes:
        results = [run_once(sc.id, args.seed + i, args.nodes, args.loss, mode) for i in range(args.runs)]
        summaries[mode] = aggregate(results)
    print(format_report(sc, summaries))


if __name__ == "__main__":
    main()
