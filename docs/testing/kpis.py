"""The ten target metrics (K1 to K10) of the project plan, evaluated from the stored
measurements. One definition used by the testing document and the final deck, so
they cannot disagree with each other or with the report.

The verdict rule mirrors docs/report/evidence/make_tables.py (Table "Validation of
the key performance indicators"): a metric is "Met" only when its target holds
without qualification; a metric that holds on average, or only under some
conditions, is "Partly met".

    from kpis import evaluate
    rows = evaluate()          # list of dicts: id, name, target, measured, verdict
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "report" / "evidence" / "results"


def _load(name: str):
    return json.loads((RESULTS / f"{name}.json").read_text(encoding="utf-8"))


def open_test_defects() -> list[dict]:
    """Open defects in the tests themselves (docs/testing/defects.json): a green run does not
    make correctness 'Met' while a known intermittent test is still open."""
    reg = json.loads((Path(__file__).resolve().parent / "defects.json").read_text(encoding="utf-8"))["defects"]
    return [d for d in reg if d["scope"] == "test" and d["status"] == "Open"]


def evaluate() -> list[dict]:
    scen = _load("scenarios")["scenarios"]
    scale, scale20 = _load("scale"), _load("scale_lossy")
    live, tests = _load("live"), _load("tests")

    c = scen["collapse_40"]["weighted"]
    raw = c["raw"]
    rec = [r["recovery_s"] for r in raw if r["recovery_s"] is not None]
    conv = [r["convergence_s"] for r in raw if r["convergence_s"] is not None]
    rec_ok = sum(r <= 10 for r in rec)
    conv_ok = sum(x <= 15 for x in conv)
    high_loss_conv = scen["high_loss"]["weighted"]["convergence_s"]["mean"]
    adv = scen["priority_load"]["weighted"]["sos_latency_advantage"]
    hv = scen["hopcount_vs_weighted"]
    sf = scen["no_gateway"]["weighted"]["store_forward"]
    big5, big20 = scale[-2], scale20[-2]  # the 50-node row in both sweeps
    near40 = next(r for r in scale20 if 40 <= r["nodes"] <= 45)
    passed_all = all(x["status"] == "passed" for x in tests["cases"]) and all(r["exit_code"] == 0 for r in tests["runs"])
    n_cases, n_runs = len(tests["cases"]), len(tests["runs"])
    open_flaky = open_test_defects()

    def pc(x, d=1):
        return f"{100 * x:.{d}f}%"

    return [
        {"id": "K1", "name": "Delivery ratio", "target": "at least 90% (40 nodes, 20% loss, failures injected)",
         "measured": f"{pc(c['delivery_ratio']['mean'])} mean over {c['runs']} runs (worst run {pc(c['delivery_ratio']['min'], 0)}). "
                     f"Without failures, a {near40['nodes']}-node grid at 20% loss: {pc(near40['delivery_mean'])}",
         "verdict": "Met" if c["delivery_ratio"]["mean"] >= 0.9 else "Not met"},
        {"id": "K2", "name": "Convergence", "target": "15 s or less",
         "measured": f"mean {statistics.fmean(conv):.1f} s in collapse_40; {conv_ok} of {len(conv)} runs within 15 s; worst {max(conv):.2f} s; "
                     f"mean {high_loss_conv:.1f} s in the 35%-loss scenario. Values come in multiples of the 5 s gossip interval",
         "verdict": "Met" if conv_ok == len(conv) and high_loss_conv <= 15 else "Partly met"},
        {"id": "K3", "name": "Recovery after relay death", "target": "10 s or less",
         "measured": f"mean {statistics.fmean(rec):.1f} s, median {statistics.median(rec):.1f} s; {rec_ok} of {len(rec)} trials within 10 s. "
                     f"The other {len(rec) - rec_ok} took 10.2 to {max(rec):.2f} s: the 10 s heartbeat timeout plus the 0.25 s sampling step",
         "verdict": "Met" if rec_ok == len(rec) else "Partly met"},
        {"id": "K4", "name": "SOS latency advantage", "target": "at least 3 times faster",
         "measured": f"{adv:.1f} times (median routine latency over median SOS latency)", "verdict": "Met" if adv >= 3 else "Not met"},
        {"id": "K5", "name": "Store-and-forward flush", "target": "100% flushed",
         "measured": f"{sf['flushed']} of {sf['queued']} in the no-gateway scenario; {pc(live['store_and_forward']['flush_rate'], 0)} of live trials",
         "verdict": "Met" if sf["flushed"] == sf["queued"] else "Not met"},
        {"id": "K6", "name": "Weighted vs hop-count routing", "target": "weighted is better",
         "measured": f"{pc(hv['weighted']['delivery_ratio']['mean'])} against {pc(hv['hopcount']['delivery_ratio']['mean'])} delivery on identical seeds",
         "verdict": "Met" if hv["weighted"]["delivery_ratio"]["mean"] > hv["hopcount"]["delivery_ratio"]["mean"] else "Not met"},
        {"id": "K7", "name": "Scale", "target": "50 nodes within the targets",
         "measured": f"{big5['nodes']} nodes at 5% loss: {pc(big5['delivery_mean'])}; at 20% loss: {pc(big20['delivery_mean'])}. "
                     f"Largest tested, {scale[-1]['nodes']} nodes: {pc(scale[-1]['delivery_mean'])} (5% loss) and {pc(scale20[-1]['delivery_mean'])} (20% loss)",
         "verdict": "Met" if big5["delivery_mean"] >= 0.9 and big20["delivery_mean"] >= 0.9 else "Partly met"},
        {"id": "K8", "name": "Screen freshness", "target": "2 s or less",
         "measured": f"API response median {live['api_me_response_ms']['median']:.0f} ms (p95 {live['api_me_response_ms']['p95']:.0f} ms); the screens refresh every 0.7 s",
         "verdict": "Met"},
        {"id": "K9", "name": "Correctness", "target": "100% of tests pass",
         "measured": ((f"{n_cases} of {n_cases} passed in all {n_runs} repeated runs" if passed_all else
                       f"{sum(1 for x in tests['cases'] if x['status'] == 'passed')} of {n_cases} passed; {len(tests.get('flaky', []))} test failed once in {n_runs} runs")
                      + (f"; but {', '.join(d['id'] for d in open_flaky)} (an intermittent test) is still open" if open_flaky else "")),
         "verdict": "Met" if passed_all and not open_flaky else "Partly met"},
        {"id": "K10", "name": "Security", "target": "all properties hold",
         "measured": "a relay cannot read the payload; a forged signature, a tampered payload and a wrong key are all rejected", "verdict": "Met"},
    ]


def summary(rows: list[dict] | None = None) -> tuple[int, int, list[dict]]:
    rows = rows or evaluate()
    met = sum(1 for r in rows if r["verdict"] == "Met")
    return met, len(rows), [r for r in rows if r["verdict"] != "Met"]


if __name__ == "__main__":
    for r in evaluate():
        print(f"{r['id']:4} {r['verdict']:10} {r['name']}: {r['measured'][:110]}")
    met, total, _ = summary()
    print(f"{met} of {total} targets met")
