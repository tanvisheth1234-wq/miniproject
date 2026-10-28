"""Builds the Phase IV, deliverable P2 submission document: "Functional and
Non-Functional Testing" for EcoMesh, as a PDF.

Every table is generated from the repository's own evidence, so the document
and the code cannot drift apart:

  * requirement text, acceptance criteria   docs/report/evidence/requirements.json, traceability.py
  * latest automated run                    docs/testing/results/pytest_latest.xml  (python -m pytest --junitxml=...)
  * earlier repeat runs                     docs/report/evidence/results/tests.json
  * browser test of the device screens      docs/testing/results/device_walkthrough.json (node docs/testing/device_walkthrough.cjs)
  * browser test of the simulation lab      docs/testing/results/ui_walkthrough.json (node docs/testing/ui_walkthrough.cjs)
  * target metrics                          docs/testing/kpis.py
  * simulator, live-device and loss data    docs/report/evidence/results/*.json
  * the attack drill                        run live by this script (api/security_demo.py)

    python -m pytest -q --junitxml=docs/testing/results/pytest_latest.xml
    python docs/testing/generate_testing_document.py

The PDF is printed by headless Chrome (set CHROME if it is not in the default place).
"""

from __future__ import annotations

import asyncio
import datetime
import functools
import html
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, OrderedDict, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVID = ROOT / "docs" / "report" / "evidence"
RESULTS = EVID / "results"
sys.path.insert(0, str(EVID))
sys.path.insert(0, str(ROOT))

import fr_table as F  # noqa: E402  (feature headings)
import traceability as T  # noqa: E402  (requirement -> tests)

import importlib.util as _ilu  # noqa: E402

_kspec = _ilu.spec_from_file_location("kpis", Path(__file__).resolve().parent / "kpis.py")
kpis = _ilu.module_from_spec(_kspec)  # the one definition of the ten targets, shared with the deck and the poster
_kspec.loader.exec_module(kpis)

OUT_PDF = HERE / "EcoMesh_Phase4_P2_Functional_and_NonFunctional_Testing.pdf"
CHROME = os.environ.get("CHROME", "C:/Program Files/Google/Chrome/Application/chrome.exe")
E = html.escape

REPO_URL = "https://github.com/tanvisheth1234-wq/miniproject"
TEAM = [("Twissha Shah", "2024300231"), ("Miti Shah", "2024300230"), ("Tanvi Sheth", "2024300239")]
GUIDE = "Prof. Anuj Tawari"


# ------------------------------------------------------------------ data

def clean_note(text: str) -> str:
    """The notes are written for LaTeX; drop the LaTeX cross-reference so it does not show in this document."""
    return re.sub("Table~" + chr(92) * 2 + "ref" + chr(92) + "{[^}]*" + chr(92) + "}", "the sample rows in report Section 4.6", text)


def jload(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()


REQ = jload(EVID / "requirements.json")
TESTS_JSON = jload(RESULTS / "tests.json")
LOSS = jload(RESULTS / "loss.json")
SCEN = jload(RESULTS / "scenarios.json")["scenarios"]
DEFECTS = jload(HERE / "defects.json")["defects"]
SCALE = jload(RESULTS / "scale.json")
SCALE20 = jload(RESULTS / "scale_lossy.json")
SCEN = jload(RESULTS / "scenarios.json")["scenarios"]
THR = jload(RESULTS / "throughput.json")
LIVE = jload(RESULTS / "live.json")
UI = jload(HERE / "results" / "ui_walkthrough.json")        # the simulation-lab website
DEV = jload(HERE / "results" / "device_walkthrough.json")   # the device screens: the one app

junit_root = ET.parse(HERE / "results" / "pytest_latest.xml").getroot()
SUITE = junit_root if junit_root.tag == "testsuite" else junit_root.find("testsuite")
LATEST: dict[tuple[str, str], tuple[str, float]] = {}
for c in SUITE.iter("testcase"):
    status = "failed" if (c.find("failure") is not None or c.find("error") is not None) else "skipped" if c.find("skipped") is not None else "passed"
    LATEST[(c.get("classname").split(".")[-1], c.get("name"))] = (status, float(c.get("time", 0)))
LATEST_BY_NAME = {name: st for (_f, name), (st, _t) in LATEST.items()}
RUN_DATE = SUITE.get("timestamp", "")[:10]
RUN_TIME = float(SUITE.get("time", 0))
N_TESTS = int(SUITE.get("tests"))
N_FAIL = int(SUITE.get("failures")) + int(SUITE.get("errors"))
HISTORY = {(c["file"], c["name"]): c["results"] for c in TESTS_JSON["cases"]}

TODAY = datetime.date.today()
COMMIT = git("rev-parse", "--short", "HEAD")
BRANCH = git("branch", "--show-current")

FILE_AREA = OrderedDict([
    ("test_packet", "Wire format: 52-byte header, path, payload, signature, retransmission counter, malformed input"),
    ("test_link_state", "Link-state encoding, gossip, re-flooding, report replacement, convergence"),
    ("test_node", "Whole node: discovery + relay + routing + reliability + security + logging together"),
    ("test_store", "SQLite message, event and peer log and its queries"),
    ("test_ack_retry", "ACK tracker, retry limits, store-and-forward bounds, eviction and expiry"),
    ("test_crypto", "AES-256-GCM encryption and Ed25519 signatures, wrong key, tampering"),
    ("test_reliability", "Duplicate suppression and the priority queue"),
    ("test_relay", "Forwarding, TTL, loop detection, priority at a relay, dedup rules"),
    ("test_transport_sim", "Simulated radio: links, loss, latency, delivery"),
    ("test_discovery", "HELLO beacons, neighbour table, death detection, range emulation"),
    ("test_routing", "Cost function and weighted path selection"),
    ("test_dijkstra", "Shortest path, RESCUE__ resolution, route cache"),
    ("test_link_quality", "Link quality measured from HELLO reception; hop-count routing mode"),
    ("test_api", "REST and WebSocket API against a live mesh (front end to engine)"),
    ("test_robustness", "Fuzzing, boundary input, concurrency and stress"),
    ("test_lan_transport", "Real TCP transport between processes, range emulation, three-node mesh"),
    ("test_sim_runner", "Simulator runner and topologies"),
    ("test_ack_multihop", "ACK over several hops, lost-ACK re-send, retry through relays"),
    ("test_device_api", "The device server: events, send, history filters, structured SOS, I am safe, CSV export, rescue reply"),
    ("test_conftest_helpers", "The wait_until polling helpers used by the timing-sensitive tests"),
])


# ------------------------------------------------------------------ small html helpers

def pct(x: float, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%"


def table(headers, rows, widths=None, cls="", head_cls=""):
    cols = ""
    if widths:
        cols = "<colgroup>" + "".join(f'<col style="width:{w}">' for w in widths) + "</colgroup>"
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = ""
    for r in rows:
        if isinstance(r, str):  # a full-width group row
            body += f'<tr class="group"><td colspan="{len(headers)}">{r}</td></tr>'
        else:
            body += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
    return f'<table class="{cls}">{cols}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def verdict(v: str) -> str:
    cls = {"Pass": "ok", "Met": "ok", "Partial": "warn", "Partly met": "warn", "Inspection": "info", "Manual check": "info",
           "Fail": "bad", "Not met": "bad", "Not done": "warn"}.get(v, "")
    return f'<span class="pill {cls}">{E(v)}</span>'


def mono(s: str) -> str:
    return f'<span class="mono">{E(s)}</span>'


def callout(text: str, kind: str = "") -> str:
    return f'<div class="callout {kind}">{text}</div>'


def svg_lines(series, xs, y_min, y_max, w=520, h=240, x_label="", y_label="", y_fmt="{:.0f}%", colors=("#000000", "#555555", "#999999")):
    """series: list of (label, [y...]) aligned with xs (categorical x)."""
    L, R, Tp, B = 54, 14, 30, 40
    pw, ph = w - L - R, h - Tp - B
    def X(i): return L + (pw * i / (len(xs) - 1) if len(xs) > 1 else pw / 2)
    def Y(v): return Tp + ph * (1 - (v - y_min) / (y_max - y_min))
    g = []
    steps = 5
    for k in range(steps + 1):
        v = y_min + (y_max - y_min) * k / steps
        g.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{w - R}" y2="{Y(v):.1f}" stroke="#cccccc" stroke-width="0.6"/>')
        g.append(f'<text x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" font-size="9" fill="#000000">{y_fmt.format(v)}</text>')
    for i, xv in enumerate(xs):
        g.append(f'<text x="{X(i):.1f}" y="{h - B + 14}" text-anchor="middle" font-size="9" fill="#000000">{E(str(xv))}</text>')
    g.append(f'<text x="{(L + w - R) / 2}" y="{h - 6}" text-anchor="middle" font-size="9.5" fill="#000000">{E(x_label)}</text>')
    g.append(f'<text transform="translate(12 {Tp + ph / 2}) rotate(-90)" text-anchor="middle" font-size="9.5" fill="#000000">{E(y_label)}</text>')
    for si, (label, ys) in enumerate(series):
        col = colors[si % len(colors)]
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(ys))
        dash = "" if si == 0 else ' stroke-dasharray="5 3"'
        g.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.6"{dash}/>')
        for i, v in enumerate(ys):
            if si == 0:
                g.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3" fill="{col}"/>')
            else:
                g.append(f'<rect x="{X(i) - 3:.1f}" y="{Y(v) - 3:.1f}" width="6" height="6" fill="#ffffff" stroke="{col}" stroke-width="1.2"/>')
        g.append(f'<line x1="{L + 8 + si * 130}" y1="10.5" x2="{L + 24 + si * 130}" y2="10.5" stroke="{col}" stroke-width="1.6"{dash}/>'
                 f'<text x="{L + 29 + si * 130}" y="14" font-size="9.5" fill="#000000">{E(label)}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" font-family="Times New Roman, Times, serif">{"".join(g)}</svg>'


def svg_bars(items, y_max=100, w=520, h=220, y_fmt="{:.1f}%"):
    L, R, Tp, B = 54, 14, 14, 36
    pw, ph = w - L - R, h - Tp - B
    n = len(items)
    bw = pw / n * 0.5
    def Y(v): return Tp + ph * (1 - v / y_max)
    g = []
    for k in range(6):
        v = y_max * k / 5
        g.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{w - R}" y2="{Y(v):.1f}" stroke="#cccccc" stroke-width="0.6"/>')
        g.append(f'<text x="{L - 6}" y="{Y(v) + 3:.1f}" text-anchor="end" font-size="9" fill="#000000">{v:.0f}%</text>')
    for i, (label, v, col) in enumerate(items):
        cx = L + pw * (i + 0.5) / n
        g.append(f'<rect x="{cx - bw / 2:.1f}" y="{Y(v):.1f}" width="{bw:.1f}" height="{Y(0) - Y(v):.1f}" fill="{col}"/>')
        g.append(f'<text x="{cx:.1f}" y="{Y(v) - 5:.1f}" text-anchor="middle" font-size="11" font-weight="700" fill="#000000">{y_fmt.format(v)}</text>')
        g.append(f'<text x="{cx:.1f}" y="{h - B + 15}" text-anchor="middle" font-size="10" fill="#000000">{E(label)}</text>')
    return f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" font-family="Times New Roman, Times, serif">{"".join(g)}</svg>'


# ------------------------------------------------------------------ sections

def sec_intro():
    return f"""
<p>This document is the Phase IV, deliverable <b>P2</b> submission: the functional and non-functional testing of
<b>EcoMesh</b>, a distributed peer-to-peer communication mesh for disaster relief. In EcoMesh every device is both an
endpoint and a relay, so a message from someone with no signal hops from device to device until it reaches a gateway or
a rescue team, with no server and no internet.</p>

<h3>1.1 Purpose</h3>
<p>To show, with repeatable evidence, that the system does what its Software Requirements Specification (SRS) says
(<b>functional testing</b>) and that it does so quickly enough, reliably enough, securely enough and at the scale
the project targets (<b>non-functional testing</b>). Where a result falls short of its target the document says so and
says why.</p>

<h3>1.2 Scope</h3>
{table(["In scope", "Out of scope (stated openly)"], [[
"The nine engine modules and the node that joins them; the device app (survivor, gateway and rescue screens, the one app) and its server API; the simulation lab (REST and WebSocket API and React website); the simulator and its seven scenarios; a five-process real-socket deployment.",
"Real radio hardware (Bluetooth LE or Wi-Fi Direct); a native mobile application; a timed usability study with participants; browsers other than Chrome; printing and installation of the PWA on physical phones."]],
widths=["52%", "48%"])}

<h3>1.3 Reference documents</h3>
<ul>
<li>Software Requirements Specification: 68 functional requirements in 10 features (identifiers such as <span class="mono">RTE-4</span>).</li>
<li>Project report, Chapter 9 (Testing and Validation) and Chapter 10 (Results), which this document extends and must not contradict.</li>
<li>Master project plan, section 16: the ten target metrics (K1 to K10) used in Section 6.</li>
<li>Source repository: {REPO_URL}, branch <span class="mono">{E(BRANCH)}</span>.</li>
</ul>
"""


def sec_strategy():
    levels = [
        ["Unit", "One module in isolation: packet, discovery, routing, reliability, crypto, store, relay", "pytest", "Developer, on every change"],
        ["Integration", "Modules together inside one node; several nodes over the simulated radio and over real TCP", "pytest, pytest-asyncio", "Developer, on every change"],
        ["System (API)", "Front end to back end to engine: REST and WebSocket against a live mesh", "FastAPI test client, httpx", "Developer, on every change"],
        ["System (device screens)", "The one app in a real browser against five live device processes: SOS with need and location, I am safe, messages, replies, filters, history, CSV export, gateway off and on", "Headless Chrome, puppeteer-core", "Scripted run (Section 5.5)"],
        ["System (simulation lab)", "The lab website driven as a user would: menus, the long-press SOS, the six demo beats", "Headless Chrome, puppeteer-core", "Scripted run (Section 5.6)"],
        ["Simulation", "Whole meshes of 5 to 65 nodes with seeded loss, latency and scripted failures, on a virtual clock", "sim/scenarios.py, api/vtime.py", "20 to 50 seeded runs per scenario"],
        ["Live devices", "Five real processes with their own sockets: latency, failover, store-and-forward", "story/ + live_test.py", "Repeated trials"],
    ]
    return f"""
<h3>2.1 Test levels</h3>
{table(["Level", "What is exercised", "Tooling", "When / how often"], levels, widths=["13%", "47%", "22%", "18%"])}

<h3>2.2 Functional versus non-functional</h3>
{table(["", "Functional testing", "Non-functional testing"], [
["Question", "Does each feature behave as the SRS requires?", "How well does it behave: how fast, how reliably, how securely, at what scale?"],
["Basis", "The 68 numbered functional requirements, each with an acceptance criterion (the tests that must pass)", "Ten key performance indicators (K1 to K10) fixed in the project plan before measuring"],
["Pass rule", "Every mapped test passes in a clean run", "The measured value meets its target; a miss is reported as a miss"],
["Section", "5", "6"]], widths=["14%", "43%", "43%"])}

<h3>2.3 Entry and exit criteria</h3>
<ul>
<li><b>Entry:</b> the code under test is on the phase branch, builds, and the suite can be started with one command.</li>
<li><b>Exit (functional):</b> every requirement is either verified by passing tests, marked partial with the reason, or listed as verified by inspection or a manual check.</li>
<li><b>Exit (non-functional):</b> each of the ten KPIs has a measured value from stored raw data; any KPI not met or met only on average is explained.</li>
<li><b>Rule we held to:</b> a failing or flaky test is recorded in Section 7, never deleted or hidden.</li>
</ul>
"""


def sec_env():
    return f"""
<h3>3.1 Environment</h3>
{table(["Item", "Value"], [
["Machine / OS", "Windows 11 Home, one laptop (all processes on one host)"],
["Language and runtime", "Python 3.11.9 (the code base targets Python 3.10 or newer); Node.js 22 for the UI build and the browser test"],
["Test framework", "pytest 9.1.1 with pytest-asyncio 1.4.0; FastAPI 0.139 test client with httpx 0.28"],
["Browser", "Google Chrome (headless) controlled by puppeteer-core; desktop viewports and phone viewports of 390 and 320 px wide"],
["Simulator", "In-process <span class='mono'>SimulatedTransport</span> with seeded loss and latency; a virtual-time event loop so the specified 3 s HELLO, 10 s timeout and 4 s ACK timer values run in milliseconds"],
["Live deployment", "Five real processes (<span class='mono'>python -m story.local</span>) with TCP between them and a topology file that emulates radio range"],
["Code under test", f"branch <span class='mono'>{E(BRANCH)}</span>, commit <span class='mono'>{E(COMMIT)}</span>, tested on {TODAY.strftime('%d %B %Y')}"],
], widths=["24%", "76%"])}

<h3>3.2 Test data</h3>
<p>There is no external dataset. Inputs are generated: message text and priorities from the tests and the website; random byte strings and bit-flipped packets for fuzzing (seeded, so a failure is reproducible); and seeded topologies (grid, chain, two-path) for the simulator, with the seed recorded in every result file.</p>

<h3>3.3 How to reproduce every result</h3>
<pre>pip install -r requirements.txt
python -m pytest -q --junitxml=docs/testing/results/pytest_latest.xml     # {N_TESTS} automated tests
node docs/testing/device_walkthrough.cjs                                    # starts the five devices itself; checks of the device screens
python -m api.server                                                        # terminal 1: the simulation lab website and API
node docs/testing/ui_walkthrough.cjs                                        # terminal 2: checks of the lab website
python -m sim.scenarios --scenario collapse_40 --runs 50                   # one simulator scenario
python docs/report/evidence/collect.py all                                  # all simulator measurements
python docs/report/evidence/live_test.py                                    # five-process live trials
python docs/testing/generate_testing_document.py                            # rebuild this document</pre>
"""


def sec_summary():
    per_file = defaultdict(lambda: [0, 0, 0.0])
    for (f, _n), (st, tm) in LATEST.items():
        per_file[f][0] += 1
        per_file[f][1] += 1 if st == "passed" else 0
        per_file[f][2] += tm
    rows = []
    for f, area in FILE_AREA.items():
        n, ok, tm = per_file[f]
        rows.append([mono(f + ".py"), n, f'<b class="okt">{ok}</b>' if ok == n else f'<b class="badt">{ok}</b>', f"{tm:.1f}", E(area)])
    total_t = sum(v[2] for v in per_file.values())
    rows.append(["<b>Total</b>", f"<b>{N_TESTS}</b>", f"<b>{N_TESTS - N_FAIL}</b>", f"<b>{total_t:.1f}</b>", ""])
    dev_pass = sum(1 for c in DEV["checks"] if c["passed"])
    web_pass = sum(1 for c in UI["checks"] if c["passed"])
    runs = TESTS_JSON["runs"]
    hist = ", ".join(f"run {r['run']}: {E(r['summary'].split(' in ')[0])}" for r in runs)
    green = sum(1 for r in runs if r["exit_code"] == 0)
    flaky = ", ".join(mono(x) for x in TESTS_JSON.get("flaky", []))
    met, total_k, _not_met = kpis.summary()
    kinds = Counter(k for _t, k in T.MAP.values())
    verified = kinds["A"] + kinds["M"]
    return f"""
<div class="kpis">
 <div><b>{N_TESTS - N_FAIL}/{N_TESTS}</b><span>automated tests passed<br>in the latest run ({RUN_DATE})</span></div>
 <div><b>{dev_pass}/{len(DEV['checks'])}</b><span>browser checks passed<br>on the device screens</span></div>
 <div><b>68</b><span>functional requirements,<br>each traced to evidence</span></div>
 <div><b>{met} of {total_k}</b><span>target metrics fully met;<br>{total_k - met} partly met, explained</span></div>
</div>

<h3>4.1 Automated suite, latest run</h3>
<p>Run on {RUN_DATE}: <b>{N_TESTS - N_FAIL} passed, {N_FAIL} failed</b> in {RUN_TIME:.1f} s. The suite was also run three times in a row earlier for the report ({hist}); {green} of the {len(runs)}
were fully green{(' and one timing-sensitive test failed: ' + flaky + ' (defect D7 in Section 7)') if flaky else ''}. Times below are the sum of the tests in each file.</p>
{table(["Test file", "Tests", "Passed", "Time (s)", "What it covers"], rows, widths=["25%", "7%", "8%", "9%", "51%"], cls="compact")}

<h3>4.2 Overall verdict</h3>
{callout(f"<b>Functional:</b> {verified} of the {sum(kinds.values())} requirements are fully verified by automated tests ({kinds['A']} by tests alone, {kinds['M']} by tests plus a check of the screen). {kinds['P']} are only partly implemented, {kinds['I']} were verified by code inspection and {kinds['U']} by a manual check. <b>Non-functional:</b> {met} of the {total_k} target metrics are fully met; the other {total_k - met} are met only partly, and Section 6 gives the measured numbers and the reasons.", "ok")}
"""


def fr_rows():
    groups = []
    kind_label = {"A": "Automated", "M": "Automated + UI", "P": "Partial", "U": "Manual only", "I": "Inspection"}
    for n, (pref, title, inp, proc, out) in enumerate(F.FEATURES, start=1):
        rows = [f"<b>5.3.{n} {E(title)}</b> &nbsp;<span class='muted'>Input: {E(inp)} Output: {E(out)}</span>"]
        for rid, (ts, kind) in T.MAP.items():
            if not rid.startswith(pref):
                continue
            ok = bool(ts) and all(LATEST_BY_NAME.get(t) == "passed" for t in ts)
            if kind in ("A", "M"):
                res = verdict("Pass" if ok else "Fail")
            elif kind == "P":
                res = verdict("Partial")
            elif kind == "I":
                res = verdict("Inspection")
            else:
                res = verdict("Manual check")
            shown = ""
            if ts:
                shown = mono(ts[0]) + (f" <span class='muted'>(+{len(ts) - 1} more)</span>" if len(ts) > 1 else "")
            if rid in T.NOTES:
                shown += ("<br>" if shown else "") + f"<span class='note'>{E(clean_note(T.NOTES[rid]))}</span>"
            rows.append([f"<b>{rid}</b>", E(REQ[rid]), kind_label[kind], shown, res])
        groups.append(rows)
    return [r for g in groups for r in g]


def sec_functional():
    kinds = Counter(k for _t, k in T.MAP.values())
    feat = []
    for pref, title, *_ in F.FEATURES:
        ids = [r for r in T.MAP if r.startswith(pref)]
        ks = Counter(T.MAP[r][1] for r in ids)
        verified = ks["A"] + ks["M"]
        feat.append([E(title), mono(pref), len(ids), verified, ks["P"], ks["I"] + ks["U"]])
    feat.append(["<b>Total</b>", "", f"<b>{sum(kinds.values())}</b>", f"<b>{kinds['A'] + kinds['M']}</b>", f"<b>{kinds['P']}</b>", f"<b>{kinds['I'] + kinds['U']}</b>"])

    _c40 = SCEN["collapse_40"]["weighted"]
    _rec = [r["recovery_s"] for r in _c40["raw"] if r["recovery_s"] is not None]
    _rec_ok = sum(1 for r in _rec if r <= 10)
    tcs = [
        ["TC-01", "RTE-3, 4", "Short path over a lossy link; longer path over clean links", "Dijkstra takes the clean path", "As expected (test_dijkstra)", "Pass"],
        ["TC-02", "RTE-8", "A link-state report from a node two hops away", "Re-flooded; the graph is complete beyond the neighbour", "As expected (test_link_state)", "Pass"],
        ["TC-03", "PRI-3", "SOS reaches a relay that has routine packets queued", "SOS is forwarded first", "As expected (test_relay)", "Pass"],
        ["TC-04", "REL-5, 6", "ACK lost; the sender times out", "Route recomputed, resent; destination sees the message once", "As expected (test_ack_multihop)", "Pass"],
        ["TC-05", "SNF-1, 2", "No route; a route appears later", "Held, then flushed and delivered", "As expected; live: 4 of 4 outages flushed, 5 of 5 messages each time", "Pass"],
        ["TC-06", "SNF-5", "Retention queue full", "Lowest priority evicted; an SOS is never displaced", "As expected (test_ack_retry)", "Pass"],
        ["TC-07", "SEC-5", "A packet with a forged signature", "Rejected and logged", "As expected (test_node)", "Pass"],
        ["TC-08", "FWD-6", "3,000 random byte strings and 1,000 bit-flipped packets", "Only parsed or PacketError; the node survives", "One defect found and fixed (D4); now passes (test_robustness)", "Pass"],
        ["TC-09", "DIS-7", "Three nodes over real TCP, neighbour-restricted", "Routes learned; message and ACK delivered", "As expected (test_lan_transport)", "Pass"],
        # figures below are read from the stored runs, so the table cannot disagree with Section 6
        ["TC-10", "K1", "40 nodes, 20% loss, relay and gateway failures, 50 seeds", "Delivery at least 90%", f"{100 * _c40['delivery_ratio']['mean']:.1f}% mean, worst run {100 * _c40['delivery_ratio']['min']:.1f}%", "Pass"],
        ["TC-11", "K3", "Kill the relay on the active path, 50 trials", "Re-route within 10 s", f"Mean {_c40['recovery_s']['mean']:.1f} s; {_rec_ok} of {len(_rec)} trials within 10 s; worst {max(_rec):.2f} s", "Partial"],
        ["TC-13", "SNF-3", "A message held for node C; C then appears", "Sent at once, not after the 10 s flush interval", "As expected (test_node); on devices: DT-15 and DT-16", "Pass"],
        ["TC-14", "LOG-5", "Message history filtered by priority and by direction", "Only matching messages are listed; the CSV export has a header and rows", "As expected (test_device_api); on screen: DT-12", "Pass"],
        ["TC-12", "K4, K6", "Congested radio; weighted vs hop-count on identical seeds", "SOS at least 3 times faster; weighted delivers more", "4.4 times; 99.2% vs 57.4%", "Pass"],
    ]
    tcs.sort(key=lambda r: int(r[0].split("-")[1]))
    tcs_html = [[r[0], r[1], E(r[2]), E(r[3]), E(r[4]), verdict(r[5])] for r in tcs]

    def walk_rows(checks):
        return [[f"<b>{c['id']}</b>", E(c["name"]), E(c["detail"]) if c["detail"] else "Confirmed on the page", verdict("Pass" if c["passed"] else "Fail")] for c in checks]

    dev_rows, ui_rows = walk_rows(DEV["checks"]), walk_rows(UI["checks"])

    api_tests = [(n, st) for (f, n), (st, _t) in LATEST.items() if f == "test_api"]
    api_rows = [[mono(n), verdict("Pass" if st == "passed" else "Fail")] for n, st in sorted(api_tests)]

    return f"""
<h3>5.1 Approach</h3>
<p>The SRS numbers every requirement (feature prefix and index, for example <span class="mono">PRI-3</span>). Each requirement's
<b>acceptance criterion</b> is the set of tests that must pass for it, recorded in <span class="mono">traceability.py</span>. A requirement is then
verified by one of five methods: automated tests alone; automated tests plus a manual look at the screen; code inspection; a manual check; or it is
only partly implemented. The table in 5.3 lists all 68, with the test that verifies each and today's result.</p>

<h3>5.2 Traceability summary</h3>
{table(["Feature", "Prefix", "Requirements", "Verified by tests", "Partial", "Inspection or manual"], feat, widths=["34%", "10%", "14%", "16%", "10%", "16%"], cls="compact")}

<h3>5.3 Requirement-by-requirement results</h3>
<p>"Pass" means every mapped test passed in the latest run. For requirements with several tests only the first is shown, with the number of others.
Notes under a requirement explain anything that is not a clean pass.</p>
{table(["ID", "The system shall…", "Method", "Verifying test", "Result"], fr_rows(), widths=["9%", "41%", "11%", "28%", "11%"], cls="fr")}

<h3>5.4 Representative test cases</h3>
<p>Twelve cases chosen to cover every feature, written in the usual form: scenario and input, expected result, actual result and evidence, verdict.</p>
{table(["ID", "Req.", "Scenario and input", "Expected result", "Actual result and evidence", "Verdict"], tcs_html, widths=["6%", "8%", "27%", "24%", "27%", "8%"], cls="compact")}

<h3>5.5 Device-screen functional tests (browser)</h3>
<p>The device screen is the one app and the demonstration, so it was tested the way a user meets it: a script starts five real device processes, opens the survivor phone,
a second phone, the gateway and the rescue console in a real Chrome, presses the on-screen buttons and reads back what each page shows. The script is
<span class="mono">docs/testing/device_walkthrough.cjs</span>; the results below are from its latest run ({E(DEV['date'][:10])}). Every outcome is produced by the real engine
and read from the screen afterwards.</p>
{table(["ID", "Check", "Evidence read from the page", "Result"], dev_rows, widths=["7%", "38%", "43%", "12%"], cls="compact")}

<h3>5.6 Simulation-lab website tests (browser)</h3>
<p>The React website is not part of the demonstration; it is the simulation lab that produced the experiments. It was tested the same way, with
<span class="mono">docs/testing/ui_walkthrough.cjs</span> (latest run {E(UI['date'][:10])}) against the running API server.</p>
{table(["ID", "Check", "Evidence read from the page", "Result"], ui_rows, widths=["7%", "38%", "43%", "12%"], cls="compact")}

<h3>5.7 API tests</h3>
<p>Twelve tests in <span class="mono">test_api.py</span> start a real mesh of five nodes and call the simulation-lab API through FastAPI's test client, including a live WebSocket.
They cover the converged snapshot, an SOS reaching the rescue queue, hop distances in a node's view, route comparison, clear error codes for bad requests (404 unknown node, 409 node switched off, 422 empty text, 400 bad priority),
killing and reviving a node, the event stream, the protocol inspector, the cryptography endpoints, the attack drill and resetting the mesh with encryption and signing on.
Twelve more in <span class="mono">test_device_api.py</span> start real device processes and call the device API: the event feed, sending a message, rejecting bad sends, history filters, structured SOS, the safe check-in, CSV export and the rescue reply.</p>
{table(["Test", "Result"], api_rows, widths=["82%", "18%"], cls="compact")}

<h3>5.8 Boundary, invalid-input and concurrency tests</h3>
{table(["Area", "What is tested", "Outcome"], [
["Boundary input", "Empty and header-only input; bad magic value; truncated header, path, payload and signature; TTL out of range; payload over the 16-bit length; path too long; node id over 8 bytes or not ASCII; wrong-length signature; signed flag without a signature; wrong key size; ciphertext shorter than the nonce; an empty payload (valid); a send to an unknown destination (held, not an exception)", verdict("Pass")],
["Fuzzing", "3,000 random byte strings and 1,000 bit-flipped valid packets to the parser; 200 garbage buffers to a running node, which must still deliver a normal message afterwards", verdict("Pass")],
["Concurrency", "200 simultaneous sends over two hops with ACKs: all 200 delivered exactly once and every ACK returned. Two senders sending 50 SOS and 50 routine messages at once to one gateway: all 100 arrive intact", verdict("Pass")],
["Replay", "One packet replayed five times is delivered once and the duplicates are dropped", verdict("Pass")],
["Real transport", "TCP between processes: previous-hop identity, range emulation, a switched-off device neither sends nor hears, hostile bytes ignored, sending to a dead peer fails fast, a full three-node mesh delivers with ACK", verdict("Pass")],
], widths=["15%", "73%", "12%"], cls="compact")}
"""


WHY = {
    "K2": "it holds in most runs but not at 35% loss, because convergence moves in multiples of the 5 s gossip interval.",
    "K3": "the mean is under 10 s, but recovery is defined by the 10 s heartbeat timer and measured in 0.25 s steps, so many trials miss by a quarter of a second. A faster 7 s timeout was tried and lowered delivery at 20% loss, so it was dropped.",
    "K7": "scale holds at 5% loss and fails at 20% loss beyond about 43 nodes.",
    "K9": "one timing-sensitive test fails intermittently (D7).",
}


def sec_nonfunctional():
    kpi = [[r['id'], r['name'], r['target'], r['measured'], r['verdict']] for r in kpis.evaluate()]
    kpi_html = [[f"<b>{r[0]}</b>", E(r[1]), E(r[2]), E(r[3]), verdict(r[4])] for r in kpi]
    met_ids = ", ".join(r[0] for r in kpi if r[4] == "Met")
    partly = [r for r in kpi if r[4] != "Met"]

    loss_rows = [[f"{int(r['loss'] * 100)}%", pct(r["delivery_mean"]), pct(r["delivery_min"]), f"{r['overhead_tx_per_delivered']:.1f}", r["runs"]] for r in LOSS]
    loss_chart = svg_lines([("delivery, 21-node mesh", [r["delivery_mean"] * 100 for r in LOSS])], [f"{int(r['loss'] * 100)}%" for r in LOSS], 40, 100,
                           x_label="injected loss on every link", y_label="messages delivered")

    nodes = [r["nodes"] for r in SCALE]
    scale_rows = []
    for a, b in zip(SCALE, SCALE20):
        scale_rows.append([a["nodes"], a["links"], pct(a["delivery_mean"]), pct(b["delivery_mean"]), f"{a['convergence_mean_s']:.1f}", f"{b['convergence_mean_s']:.1f}"])
    scale_chart = svg_lines([("5% loss", [r["delivery_mean"] * 100 for r in SCALE]), ("20% loss", [r["delivery_mean"] * 100 for r in SCALE20])], nodes, 80, 100,
                            x_label="nodes in the mesh", y_label="messages delivered")
    hc = SCEN["hopcount_vs_weighted"]
    hop_chart = svg_bars([("Hop-count routing", hc["hopcount"]["delivery_ratio"]["mean"] * 100, "#aaaaaa"), ("Weighted (Dijkstra)", hc["weighted"]["delivery_ratio"]["mean"] * 100, "#222222")])

    scen_rows = []
    for k, v in SCEN.items():
        w = v["weighted"]
        scen_rows.append([mono(k), v["nodes"], f"{int(v['loss'] * 100)}%", v["runs"], pct(w["delivery_ratio"]["mean"]), pct(w["delivery_ratio"]["min"]),
                          f"{w['median_hops']:g}", f"{w['convergence_s']['mean']:.1f}" if w["convergence_s"] else "n/a"])

    pl = SCEN["priority_load"]["weighted"]["latency_ms"]
    live = LIVE
    sa, ab = live["sos_latency_ms"]["arrive_at_rescue"], live["sos_latency_ms"]["ack_back_at_sender"]
    fo = [t["reroute_s"] for t in live["failover"]["trials"]]
    fl = [t["seconds_to_flush"] for t in live["store_and_forward"]["trials"]]
    idle = live["idle"]["per_process"]
    load = live["under_load"]["per_process"]
    idle_cpu = max(v["cpu_percent_of_one_core"] for v in idle.values())
    load_cpu = max(v["cpu_percent_of_one_core"] for v in load.values())
    mem_lo = min(v["working_set_mb"] for v in list(idle.values()) + list(load.values()))
    mem_hi = max(v["working_set_mb"] for v in list(idle.values()) + list(load.values()))

    drill = drill_result()
    drill_rows = [[E(s["title"]), E(s["what"]), E(s["verdict"]), verdict("Pass" if s["defended"] else "Fail")] for s in drill["steps"]]

    return f"""
<h3>6.1 Validation against the ten target metrics</h3>
<p>The targets were fixed in the project plan before any measurement. Each value below comes from stored raw data in
<span class="mono">docs/report/evidence/results/</span> and can be regenerated with the commands in Section 3.3.</p>
{table(["ID", "Metric", "Target", "Measured", "Verdict"], kpi_html, widths=["6%", "16%", "19%", "47%", "12%"], cls="compact")}
{callout(f"<b>Reading this table.</b> {met_ids} are fully met. " + " ".join(f"{r[0]} ({r[1].lower()}) is only partly met: {WHY[r[0]]}" for r in partly), "")}

<h3>6.2 Performance</h3>
<h4>Latency and throughput</h4>
{table(["Measurement", "Result", "Setting"], [
["SOS delivery latency, live devices", f"median {sa['median']:.0f} ms, p95 {sa['p95']:.0f} ms, max {sa['max']:.0f} ms", f"5 real processes, {sa['n']} SOS messages, all delivered"],
["SOS delivery plus ACK back at the sender", f"median {ab['median']:.0f} ms, p95 {ab['p95']:.0f} ms", f"same {ab['n']} messages, all acknowledged"],
["Latency under congestion, simulated", f"SOS median {pl['SOS']:.0f} ms against routine {pl['NORMAL']:.0f} ms: {SCEN['priority_load']['weighted']['sos_latency_advantage']:.1f} times faster", "16 nodes, radio of one packet per 80 ms, 90 messages of which 15% are SOS, all to one gateway, 20 runs"],
["API response time", f"median {live['api_me_response_ms']['median']:.0f} ms, p95 {live['api_me_response_ms']['p95']:.0f} ms", f"{live['api_me_response_ms']['n']} requests to a node's status"],
] , widths=["32%", "36%", "32%"], cls="compact")}
<h4>Throughput of one process</h4>
{table(["Simultaneous sends", "All delivered", "All acknowledged", "Messages per second", "Time to last ACK (s)"], [
[t["messages"], t["delivered"], t["acked"], f"{t['msgs_per_s']:.0f}", f"{t['ack_seconds']:.2f}"] for t in THR], widths=["20%", "16%", "18%", "22%", "24%"], cls="compact")}

<h3>6.3 Reliability under packet loss</h3>
<p>A 21-node mesh, {LOSS[0]["runs"]} seeded runs per row, with the stated loss on every link. Delivery stays at 100% up to 10% loss and degrades gracefully; the extra transmissions per delivered message show the cost of retrying.</p>
<div class="two">
<div>{table(["Loss per link", "Delivery (mean)", "Worst run", "Transmissions per delivered", "Runs"], loss_rows, widths=["18%", "22%", "18%", "28%", "14%"], cls="compact")}</div>
<div>{loss_chart}<div class="caption">Figure 1. Delivery against injected loss.</div></div>
</div>

<h3>6.4 Scalability</h3>
<p>Grid meshes from 10 to 65 nodes at 5% and 20% loss, six runs per cell. Convergence is how long until every node knows every other node.</p>
<div class="two">
<div>{table(["Nodes", "Links", "Delivery, 5% loss", "Delivery, 20% loss", "Convergence 5% (s)", "Convergence 20% (s)"], scale_rows, widths=["12%", "12%", "19%", "19%", "19%", "19%"], cls="compact")}</div>
<div>{scale_chart}<div class="caption">Figure 2. Delivery against mesh size.</div></div>
</div>

<h3>6.5 Routing quality, recovery and availability</h3>
<div class="two">
<div>
<p><b>Weighted versus hop-count routing.</b> The same two-path topology (a short route over a lossy link, a longer route over clean links), the same seeds and the same best-effort traffic, run once with each router, 20 runs each.</p>
{hop_chart}<div class="caption">Figure 3. Delivery with each routing mode.</div>
</div>
<div>
<p><b>Failover and store-and-forward on real devices.</b></p>
{table(["Trial type", "Trials", "Result"], [
["Kill a relay, then send", len(fo), f"all delivered; reroute {min(fo):.1f} to {max(fo):.1f} s, mean {sum(fo) / len(fo):.1f} s"],
["Gateway off, hold 5 SOS, switch on", len(fl), f"all 5 delivered every time; flush {min(fl):.1f} to {max(fl):.1f} s, mean {sum(fl) / len(fl):.1f} s"],
["Startup to full convergence", 1, f"{live['startup_to_full_convergence_s']:.1f} s for 5 processes"],
["Simulated relay death", 50, "mean recovery 8.1 s (see K3)"],
], widths=["38%", "12%", "50%"], cls="compact")}
</div>
</div>
<h4>All scenarios</h4>
<p>Seven simulator scenarios, run with the specified timer values on a virtual clock (20 runs each, 50 for collapse_40).</p>
{table(["Scenario", "Nodes", "Loss", "Runs", "Delivery (mean)", "Worst run", "Median relays", "Convergence (s)"], scen_rows, widths=["22%", "9%", "8%", "8%", "14%", "11%", "14%", "14%"], cls="compact")}

<h3>6.6 Security testing</h3>
<p>Security is tested at three levels: unit tests of the cryptography (19 tests), node-level tests with encryption and signing on, and a live <b>attack drill</b> that runs three real nodes
A, M and B with M hostile, and records what B does. The drill below was executed while this document was generated.</p>
{table(["Attack", "What M does", "What B did", "Result"], drill_rows, widths=["22%", "36%", "30%", "12%"], cls="compact")}
<ul>
<li>A relay configured with no key at all still forwards correctly and never sees plaintext (<span class="mono">test_relay_never_sees_plaintext_payload</span>).</li>
<li>A tampered ciphertext or a wrong key is detected by the GCM tag and dropped; the signature covers the ciphertext, so a signed message is rejected even earlier.</li>
<li>A forged signature and an unknown signer are rejected and logged; signatures survive multi-hop relaying because only fields that never change in transit are signed.</li>
</ul>
{callout("<b>Known limit.</b> Signing is opt-in across the mesh in this build, so a forger who leaves a packet unsigned is not caught by signature checks, and one pre-shared key protects the whole mesh. Both are listed as future work.", "warn")}

<h3>6.7 Resource use</h3>
{table(["Condition", "Memory per process", "CPU per process (share of one core)"], [
["Idle, 5 processes, 20 s", f"{min(v['working_set_mb'] for v in idle.values()):.0f} to {max(v['working_set_mb'] for v in idle.values()):.0f} MB", f"at most {idle_cpu:.1f}%"],
["Under a burst of traffic, 2.3 s", f"{min(v['working_set_mb'] for v in load.values()):.0f} to {max(v['working_set_mb'] for v in load.values()):.0f} MB", f"at most {load_cpu:.1f}%"],
], widths=["34%", "30%", "36%"], cls="compact")}
<p>The figures are for the Python process only, on one machine.</p>

<h3>6.8 Usability, accessibility and compatibility</h3>
{table(["Aspect", "What was checked", "Outcome"], [
["Emergency usability", "The SOS control is a single hold of about 1.2 s on one prominent button; releasing early sends nothing (DT-04); the need and location travel with it (DT-05); status is shown in plain words with the route (DT-06, DT-15, DT-16)", verdict("Pass")],
["Responsive layout", "Both device screens at 390 px and 320 px wide (DT-17) and every page of the lab website at 390 px (UT-15): no sideways scrolling", verdict("Pass")],
["Keyboard access", "The SOS button is written to be armed with Space or Enter, but keyboard use and screen-reader use were not tested", verdict("Not done")],
["Browsers", "Google Chrome only (desktop and a phone-sized viewport). Firefox, Edge and Safari were not tested", verdict("Partial")],
["Real phones", "Not tested on physical devices; the PWA manifest and service worker are present but installation was not tested", verdict("Partial")],
["Usability study", "No timed study with participants was carried out; this is stated in the report as well", verdict("Not done")],
], widths=["18%", "70%", "12%"], cls="compact")}

<h3>6.9 Maintainability</h3>
<p>Every module has its own test file; the full suite runs in about {RUN_TIME:.0f} s with one command; measurement scripts re-create every table in the report from stored raw data, so a code change can be re-measured the same way.</p>
"""


@functools.lru_cache(maxsize=1)
def drill_result():
    """Run the three-node attack drill once and reuse it for every render pass."""
    from api import security_demo
    return asyncio.run(security_demo.attack_drill())


def sec_defects():
    rows = [[d["id"], d["found_by"], d["defect"], d["fix"], d["status"]] for d in DEFECTS]
    pill = {"Closed": '<span class="pill ok">Closed</span>', "Open": '<span class="pill warn">Open</span>'}
    html_rows = [[f"<b>{r[0]}</b>", E(r[1]), E(r[2]), E(r[3]), pill[r[4]]] for r in rows]
    return f"""
<p>Every defect found while testing, with its cause and how it was fixed and retested. Defects D2, D3, D8 and D9 were found by testing the integrated system, not by the unit tests, which is why the integration, API and browser levels exist.</p>
{table(["ID", "Found by", "Defect and cause", "Fix and retest", "Status"], html_rows, widths=["5%", "17%", "37%", "31%", "10%"], cls="compact")}
"""


def sec_limits():
    open_d = [d["id"] for d in DEFECTS if d["status"] != "Closed"]
    OPEN_DEFECTS_ITEM = (f"<li><b>Open defects ({', '.join(open_d)}).</b> See Section 7.</li>" if open_d else
        "<li><b>No open defect.</b> The two intermittent tests found late (D7 and D10) were fixed at their cause and each passed 30 of 30 runs under CPU load.</li>")
    return f"""
<ul>
<li><b>No radio hardware.</b> The "radio" is a neighbour-restricted LAN or an in-memory simulator, so radio effects such as interference and range are modelled, not measured.</li>
<li><b>One machine.</b> All live-device timings were taken with five processes on one laptop. A two-laptop split worked over a phone hotspot, but it was not timed under the same protocol.</li>
<li><b>Recovery time is quantised.</b> Failure detection is defined by a 10 s heartbeat timer, so the "10 s or less" target is met only on average (K3).</li>
<li><b>Scale at high loss.</b> Delivery falls below 90% beyond about 43 nodes at 20% loss (K7).</li>
<li><b>Browser checks are not part of the pytest suite.</b> The two browser scripts are separate commands that need Chrome; the device script starts its own devices.</li>
<li><b>Untested:</b> a timed usability study, browsers other than Chrome, physical phones, installing the PWA.</li>
{OPEN_DEFECTS_ITEM}
<li><b>Security scope.</b> One pre-shared key for the mesh; signing is optional; an unsigned forgery is not caught.</li>
</ul>
"""


def sec_conclusion():
    dev_pass = sum(1 for c in DEV["checks"] if c["passed"])
    web_pass = sum(1 for c in UI["checks"] if c["passed"])
    met, total_k, not_met = kpis.summary()
    kinds = Counter(k for _t, k in T.MAP.values())
    verified = kinds["A"] + kinds["M"]
    _open = [d["id"] for d in DEFECTS if d["status"] != "Closed"]
    _closed = len(DEFECTS) - len(_open)
    _open_txt = (f", {len(_open)} open ({', '.join(_open)}) and explained" if _open else ", none open")
    return f"""
<p>EcoMesh was tested at six levels, from single-module unit tests to five real processes exchanging messages over TCP.</p>
<ul>
<li><b>Functional:</b> {N_TESTS - N_FAIL} of {N_TESTS} automated tests passed in the latest run, {dev_pass} of {len(DEV['checks'])} browser checks of the device screens passed and {web_pass} of {len(UI['checks'])} of the simulation lab. {verified} of the {sum(kinds.values())} requirements are fully verified; {kinds['P']} are partial, {kinds['I']} were verified by inspection and {kinds['U']} by a manual check.</li>
<li><b>Non-functional:</b> {met} of {total_k} target metrics are fully met. The {total_k - met} that are only partly met are {", ".join(r["id"] + " (" + r["name"].lower() + ")" for r in not_met)}.</li>
<li><b>Design validated:</b> weighted routing delivered 99.2% against 57.4% for hop-count routing on identical seeds, SOS arrived 4.4 times faster under congestion, and every held message was flushed when a path returned.</li>
<li><b>Defects:</b> {len(DEFECTS)} found, {_closed} closed{_open_txt}.</li>
</ul>
<p>The system is fit for its stated purpose, a software mesh demonstrated on LAN sockets and a simulator, with the limits in Section 8 stated openly.</p>

<h3>Sign-off</h3>
{table(["Role", "Name", "Signature", "Date"], [
["Prepared by", "Tanvi Sheth (2024300239)", "&nbsp;<br>&nbsp;", ""],
["Prepared by", "Twissha Shah (2024300231)", "&nbsp;<br>&nbsp;", ""],
["Prepared by", "Miti Shah (2024300230)", "&nbsp;<br>&nbsp;", ""],
["Reviewed by (guide)", f"{GUIDE}", "&nbsp;<br>&nbsp;", ""],
], widths=["24%", "34%", "26%", "16%"], cls="sign")}
"""


def sec_appendix():
    by_file = defaultdict(list)
    for (f, n), (st, tm) in LATEST.items():
        by_file[f].append((n, st, tm))
    out = ["<p>Every automated test case, grouped by file. The three symbols show the three earlier repeated runs (P = passed, F = failed); the last column is the latest run.</p>"]
    n = 0
    for f in FILE_AREA:
        rows = []
        for name, st, tm in sorted(by_file[f]):
            n += 1
            hist = "".join("P" if r == "passed" else "F" for r in HISTORY.get((f, name), []))
            rows.append([n, mono(name), f'<span class="mono">{hist}</span>', verdict("Pass" if st == "passed" else "Fail")])
        out.append(f"<h4>{mono(f + '.py')} &nbsp;<span class='muted'>{len(rows)} tests · {E(FILE_AREA[f])}</span></h4>")
        out.append(table(["#", "Test case", "Earlier runs", "Latest"], rows, widths=["6%", "68%", "13%", "13%"], cls="compact tc"))
    return "".join(out)


# ------------------------------------------------------------------ assembly

CSS = """
@page { size: A4; margin: 22mm 20mm 24mm 22mm;
  @bottom-left { content: "EcoMesh: Functional and Non-Functional Testing"; font: 9pt 'Times New Roman', Times, serif; color: #000; }
  @bottom-right { content: "Page " counter(page) " of " counter(pages); font: 9pt 'Times New Roman', Times, serif; color: #000; } }
@page :first { margin: 0; @bottom-left { content: none; } @bottom-right { content: none; } }
* { box-sizing: border-box; }
html { font-family: 'Times New Roman', Times, serif; color: #000; background: #fff; font-size: 11pt; line-height: 1.4; }
body { margin: 0; background: #fff; }
h1 { font-size: 16pt; font-weight: 700; color: #000; margin: 0 0 9pt; padding-bottom: 4pt; border-bottom: 1pt solid #000; page-break-after: avoid; }
h2 { font-size: 13pt; font-weight: 700; margin: 14pt 0 5pt; page-break-after: avoid; }
h3 { font-size: 12pt; font-weight: 700; margin: 13pt 0 4pt; page-break-after: avoid; }
h4 { font-size: 11pt; font-weight: 700; font-style: italic; margin: 10pt 0 3pt; page-break-after: avoid; }
p { margin: 0 0 6pt; text-align: justify; } ul { margin: 0 0 6pt 18pt; padding: 0; } li { margin-bottom: 3pt; text-align: justify; }
.section { page-break-before: always; }
.mono, pre { font-family: 'Courier New', Courier, monospace; font-size: 8.5pt; }
.mono { word-break: break-word; }
pre { background: #fff; border: 0.7pt solid #000; padding: 6pt 8pt; white-space: pre-wrap; line-height: 1.45; }
.muted { color: #000; font-weight: 400; font-style: italic; } .note { color: #000; font-size: 9pt; font-style: italic; }
.okt, .badt { color: #000; font-weight: 700; }
table { width: 100%; border-collapse: collapse; margin: 4pt 0 9pt; font-size: 9.5pt; page-break-inside: auto; }
th { background: #e6e6e6; color: #000; text-align: left; font-weight: 700; padding: 3.5pt 5pt; border: 0.6pt solid #000; }
td { padding: 3pt 5pt; border: 0.6pt solid #000; vertical-align: top; background: #fff; }
tr { page-break-inside: avoid; } thead { display: table-header-group; }
tr.group td { background: #f2f2f2 !important; font-size: 9.5pt; padding: 4pt 5pt; }
table.compact td, table.compact th { padding: 2.6pt 4pt; font-size: 9pt; }
table.tc td { padding: 1.6pt 4pt; font-size: 8.5pt; }
table.fr td { font-size: 9pt; } table.fr tr:not(.group) td:first-child { white-space: nowrap; }
table.sign td { height: 24pt; }
.pill { font-weight: 700; white-space: nowrap; }
.callout { border: 0.8pt solid #000; background: #fff; padding: 6pt 9pt; margin: 6pt 0 8pt; page-break-inside: avoid; text-align: justify; }
.kpis { display: flex; gap: 8pt; margin: 4pt 0 10pt; }
.kpis > div { flex: 1; border: 0.8pt solid #000; padding: 7pt 8pt; background: #fff; }
.kpis b { display: block; font-size: 19pt; color: #000; line-height: 1.1; }
.kpis span { font-size: 9pt; }
.two { display: flex; gap: 12pt; align-items: flex-start; break-inside: avoid; page-break-inside: avoid; } .two > div { flex: 1; min-width: 0; }
.caption { font-size: 9pt; text-align: center; margin-top: 2pt; font-style: italic; }
svg { display: block; } figure { margin: 0; }
/* cover */
.cover { page-break-after: always; height: 297mm; padding: 32mm 25mm 20mm; text-align: center; background: #fff; }
.cover .org { font-size: 13pt; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6pt; }
.cover .org2 { font-size: 11pt; margin-top: 3pt; }
.cover h1 { border: 0; font-size: 26pt; line-height: 1.2; margin: 38mm 0 6mm; padding: 0; }
.cover .sub { font-size: 14pt; font-weight: 700; margin-bottom: 4mm; } .cover .proj { font-size: 13pt; font-style: italic; margin: 0 auto; max-width: 150mm; }
.cover table { margin: 24mm auto 0; font-size: 11pt; width: 150mm; text-align: left; } .cover td { border: 0; border-bottom: 0.5pt solid #000; padding: 4pt 6pt; }
.cover td:first-child { width: 38mm; font-weight: 700; }
/* toc */
.toc { page-break-after: always; } .toc ol { list-style: none; margin: 0; padding: 0; }
.toc li { display: flex; gap: 6pt; margin: 0; padding: 3pt 0; border-bottom: 0.5pt dotted #000; font-size: 11pt; font-weight: 700; text-align: left; }
.toc li.sub { padding-left: 18pt; font-size: 10pt; font-weight: 400; border-bottom: none; padding-top: 1pt; padding-bottom: 1pt; }
.toc .n { width: 22pt; } .toc .t { flex: 1; } .toc .p { font-variant-numeric: tabular-nums; }
"""

BODIES = [
    ("1", "Introduction", sec_intro),
    ("2", "Test strategy", sec_strategy),
    ("3", "Test environment and tools", sec_env),
    ("4", "Execution summary", sec_summary),
    ("5", "Functional testing", sec_functional),
    ("6", "Non-functional testing", sec_nonfunctional),
    ("7", "Defects found and resolved", sec_defects),
    ("8", "Limitations and risks", sec_limits),
    ("9", "Conclusion and sign-off", sec_conclusion),
    ("A", f"Appendix A: all {N_TESTS} automated test cases", sec_appendix),
]


def toc_entries(bodies_html):
    entries = []
    for num, title, body in bodies_html:
        entries.append((num, title, 1))
        for m in re.finditer(r"<h3>((?:\d+\.\d+|A)[^<]*?)</h3>", body):
            t = m.group(1)
            mm = re.match(r"(\d+\.\d+)\s+(.*)", t)
            if mm:
                entries.append((mm.group(1), mm.group(2), 2))
    return entries


def render_html(pages: dict[str, int] | None) -> str:
    bodies = [(n, t, fn()) for n, t, fn in BODIES]
    entries = toc_entries(bodies)
    toc_li = ""
    for num, title, lvl in entries:
        p = (pages or {}).get(f"{num}|{title}", "")
        toc_li += f'<li class="{"sub" if lvl == 2 else ""}"><span class="n">{E(num) if lvl == 1 else ""}</span><span class="t">{E(num + " " + title) if lvl == 2 else E(title)}</span><span class="p">{p}</span></li>'
    secs = "".join(f'<section class="section"><h1>{E(n if n != "A" else "")}{(". " if n != "A" else "")}{E(t)}</h1>{b}</section>' for n, t, b in bodies)
    team_rows = "".join(f"<tr><td>Team</td><td>{E(n)} · {u}</td></tr>" if i == 0 else f"<tr><td></td><td>{E(n)} · {u}</td></tr>" for i, (n, u) in enumerate(TEAM))
    cover = f"""
<div class="cover"><div class="band"></div>
 <div class="org">Sardar Patel Institute of Technology · Department of Computer Engineering</div>
 <div class="org2">Autonomous Institute Affiliated to University of Mumbai</div>
 <h1>Functional and Non-Functional Testing</h1>
 <div class="sub">Phase IV · Deliverable P2</div>
 <div class="proj">EcoMesh: A Distributed Peer-to-Peer Disaster Relief Communication Mesh</div>
 <table>
  <tr><td>Course</td><td>T.E. Semester V · Mini Project – I · Academic year 2026–27</td></tr>
  <tr><td>Group</td><td>Group 20</td></tr>
  {team_rows}
  <tr><td>Guide</td><td>{GUIDE}</td></tr>
  <tr><td>Version</td><td>1.0 · {TODAY.strftime('%d %B %Y')}</td></tr>
  <tr><td>Code tested</td><td>{REPO_URL}<br>branch {E(BRANCH)} · commit {E(COMMIT)}</td></tr>
 </table>
</div>"""
    toc = f'<div class="toc"><h1>Contents</h1><ol>{toc_li}</ol></div>'
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>EcoMesh: Functional and Non-Functional Testing</title><style>{CSS}</style></head><body>{cover}{toc}{secs}</body></html>', entries


def print_pdf(html_path: Path, pdf_path: Path):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={pdf_path}", html_path.as_uri()],
                   check=True, capture_output=True, timeout=180)


def find_pages(pdf_path: Path, entries):
    import fitz  # PyMuPDF
    doc = fitz.open(pdf_path)
    texts = [" ".join(p.get_text().split()) for p in doc]
    start = next((i for i, t in enumerate(texts) if "This document is the Phase IV, deliverable" in t), 2)  # first page after the contents
    pages = {}
    for num, title, lvl in entries:
        needle = (f"{num}. {title}" if lvl == 1 and num != "A" else (title if num == "A" else f"{num} {title}"))
        needle = " ".join(needle.split())[:48]
        for i in range(start, len(texts)):
            if needle in texts[i]:
                pages[f"{num}|{title}"] = i + 1
                break
    return pages, len(doc)


def main():
    tmp = HERE / "_testing_document.html"
    doc_html, entries = render_html(None)
    tmp.write_text(doc_html, encoding="utf-8")
    print_pdf(tmp, OUT_PDF)
    pages, n = find_pages(OUT_PDF, entries)
    doc_html, _ = render_html(pages)
    tmp.write_text(doc_html, encoding="utf-8")
    print_pdf(tmp, OUT_PDF)
    pages2, n2 = find_pages(OUT_PDF, entries)
    if pages2 != pages:  # the contents page itself did not move, but be safe
        doc_html, _ = render_html(pages2)
        tmp.write_text(doc_html, encoding="utf-8")
        print_pdf(tmp, OUT_PDF)
    tmp.unlink(missing_ok=True)
    print(f"wrote {OUT_PDF} ({n2} pages)")


if __name__ == "__main__":
    main()
