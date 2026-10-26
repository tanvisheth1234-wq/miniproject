"""Functional-requirements table (Section 3.4): every requirement with its
identifier, text and acceptance criterion (the tests that verify it), grouped
by feature with the feature's input, processing and output.

    python docs/report/evidence/fr_table.py

Reads requirements.json (SRS text), traceability.MAP (requirement -> tests) and
results/tests.json (pass/fail from repeated runs).
"""

from __future__ import annotations

import json
from pathlib import Path

from traceability import KIND, MAP, NOTES, esc  # noqa: E402

HERE = Path(__file__).resolve().parent
GEN = HERE.parents[0] / "latex" / "generated"
BS = chr(92)

FEATURES = [
    ("DIS", "Peer discovery",
     "HELLO beacons (role, public key) from neighbours; silence from a known neighbour.",
     "Update the neighbour table; estimate link quality over a 20-HELLO window; prune after the timeout.",
     "Peer-up and peer-down events and link quality passed to routing."),
    ("MSG", "Message composition and transmission",
     "Text and destination, or the SOS control (sustained press).",
     "Build a packet with a unique id and timestamp; encrypt and sign; queue.",
     "DATA packet sent; delivery state shown to the user."),
    ("FWD", "Multi-hop forwarding",
     "DATA or ACK packet from a neighbour.",
     "Validate; drop duplicates; check hop allowance and loop; append own id; queue by priority.",
     "Packet forwarded, or dropped with a logged reason."),
    ("RTE", "Adaptive routing",
     "Link-state reports; a destination.",
     "Merge into the graph; Dijkstra over the weighted cost; resolve RESCUE__ to the nearest gateway or rescue node.",
     "Least-cost next hop; routes recomputed on topology change."),
    ("PRI", "Priority handling",
     "Packets of different priority queued together.",
     "Priority queue ordered by priority, then age, applied at every hop.",
     "SOS transmitted before routine traffic."),
    ("REL", "Reliability",
     "Delivered or unacknowledged packets; duplicates; missing beacons.",
     "ACK; timer; retry with a recomputed route; dedup set; failure detection.",
     "ACK returned; bounded retries; duplicates dropped; failed neighbours removed."),
    ("SNF", "Store-and-forward",
     "A message with no route; a new route or neighbour.",
     "Bounded retention by count and age; periodic flush; lowest priority evicted first.",
     "Message delivered when a path appears, or expired and logged."),
    ("SEC", "Message security",
     "Payload and packet identity fields.",
     "AES-256-GCM encryption; Ed25519 signature; verification and decryption on receipt.",
     "Tampered or forged packets rejected."),
    ("LOG", "Logging and history",
     "Every message and network event.",
     "Write to the node's SQLite database.",
     "History and delivery statistics available by query."),
    ("DSH", "Rescue dashboard",
     "Node state and events.",
     "Compute topology, SOS queue and statistics from the graph and the logs.",
     "Live graph; SOS queue by priority then age; statistics."),
]


def main() -> None:
    req = json.loads((HERE / "requirements.json").read_text(encoding="utf-8"))
    tests = json.loads((HERE / "results" / "tests.json").read_text(encoding="utf-8"))
    status: dict[str, list[str]] = {}
    for c in tests["cases"]:
        status.setdefault(c["name"], []).append(c["status"])
    code = {"A": "Auto", "M": "Auto+UI", "P": "Partial", "U": "Manual", "I": "Inspect"}

    def text(t: str) -> str:
        return t.replace("&", BS + "&").replace("%", BS + "%").replace("_", BS + "_")

    def tname(t: str) -> str:
        return BS + "texttt{" + esc(t).replace("::", "::" + BS + "allowbreak{}") + "}"

    L = [BS + "begingroup" + BS + "footnotesize" + BS + "renewcommand{" + BS + "arraystretch}{1.0}", BS + "setlength{" + BS + "tabcolsep}{3pt}",
         BS + "begin{longtable}{@{}p{1.25cm}p{6.3cm}p{1.65cm}p{6.95cm}@{}}",
         BS + "caption[Functional requirements and their acceptance tests]{Functional requirements by feature (identifiers as in the SRS). Check: Auto = verified by automated tests, Auto+UI = automated tests plus a manual check of the screen, "
         "Partial = only partly implemented, Inspect = code inspection, Manual = manual check only; * marks a mapped test that failed once in repeated runs. The first mapped test is named and (+n) counts the others.}" + BS + BS,
         BS + "label{tab:fr}" + BS + BS,
         BS + "toprule " + BS + "textbf{ID} & " + BS + "textbf{Requirement (the system shall " + BS + "ldots)} & " + BS + "textbf{Check} & " + BS + "textbf{Acceptance criterion: tests that must pass} " + BS + BS + " " + BS + "midrule " + BS + "endfirsthead",
         BS + "toprule " + BS + "textbf{ID} & " + BS + "textbf{Requirement} & " + BS + "textbf{Check} & " + BS + "textbf{Acceptance criterion} " + BS + BS + " " + BS + "midrule " + BS + "endhead"]
    for n, (pref, title, inp, proc, out) in enumerate(FEATURES, start=1):
        L.append(BS + "multicolumn{4}{@{}p{16.78cm}@{}}{" + BS + "rule{0pt}{7pt}" + BS + "textbf{3.4." + str(n) + " " + title + ".} "
                 + BS + "textit{Input:} " + text(inp) + " " + BS + "textit{Processing:} " + text(proc) + " " + BS + "textit{Output:} " + text(out) + "} " + BS + BS + " " + BS + "midrule")
        for rid, (ts, kind) in MAP.items():
            if not rid.startswith(pref):
                continue
            flaky = any(s != "passed" for t in ts for s in status[t])
            shown = ", ".join(tname(t) for t in ts[:1]) + (f" (+{len(ts) - 1})" if len(ts) > 1 else "")
            if rid in NOTES:
                shown = (shown + " " if shown else "") + BS + "textit{" + NOTES[rid] + "}"
            L.append(f"{rid} & {text(req[rid])} & {code[kind]}{'*' if flaky else ''} & {shown} " + BS + BS)
    L += [BS + "bottomrule", BS + "end{longtable}", BS + "endgroup"]
    (GEN / "fr_table.tex").write_text(chr(10).join(L) + chr(10), encoding="utf-8")
    print("wrote fr_table.tex with", len(MAP), "requirements")


if __name__ == "__main__":
    main()
