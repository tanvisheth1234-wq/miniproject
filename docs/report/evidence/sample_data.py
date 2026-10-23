"""Dump representative database rows from a real three-node run (A - B - C)
into docs/report/latex/generated/sample_rows.tex  (Table in Section 4.6).

    python docs/report/evidence/sample_data.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
GEN = ROOT / "docs" / "report" / "latex" / "generated"
BS = chr(92)

from mesh.core.discovery import NodeRole  # noqa: E402
from mesh.core.node import Node  # noqa: E402
from mesh.core.packet import Priority  # noqa: E402
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport  # noqa: E402


def esc(t) -> str:
    t = "" if t is None else str(t)
    for a, b in (("\\", BS + "textbackslash{}"), ("&", BS + "&"), ("%", BS + "%"), ("#", BS + "#"), ("_", BS + "_" + BS + "allowbreak{}")):
        t = t.replace(a, b)
    return t


def short(msg_id) -> str:
    return str(msg_id)[:8] + "..."


async def run():
    net = SimulatedNetwork(seed=4)
    net.set_link("A", "B")
    net.set_link("B", "C")
    kw = dict(hello_interval=0.05, neighbour_timeout=0.5, link_state_interval=0.1, ack_timeout=1.0)
    nodes = {"A": Node("A", SimulatedTransport("A", net), **kw), "B": Node("B", SimulatedTransport("B", net), **kw),
             "C": Node("C", SimulatedTransport("C", net), role=NodeRole.GATEWAY, **kw)}
    for n in nodes.values():
        await n.start()
    await asyncio.sleep(0.6)
    pkt = await nodes["A"].send("C", b"trapped on floor 3", priority=Priority.SOS, needs_ack=True)
    await asyncio.sleep(0.6)
    mid = str(pkt.msg_id)
    out = {"msg": {k: n.store.get_message(mid) for k, n in nodes.items()},
           "events": nodes["A"].store.events_for_message(mid), "peers": nodes["B"].store.all_peers()}
    for n in nodes.values():
        await n.stop()
    return out


def main() -> None:
    d = asyncio.run(run())
    rows = []
    for node in ("A", "B", "C"):
        m = d["msg"][node]
        if m is None:
            continue
        rows.append([f"{node}", short(m["msg_id"]), m["src"], m["dst"], str(m["priority"]), m["direction"], m["status"],
                     esc(m["body"]) if m["body"] else "NULL", "" if m["hop_count"] is None else str(m["hop_count"]), esc(m["path"]) if m["path"] else "NULL"])
    t1 = [BS + "begin{table}[H]", BS + "caption{Sample rows of " + BS + "texttt{messages} for one SOS from A to C in a real run: each node holds its own view of the same message id}",
          BS + "label{tab:samples}", BS + "footnotesize", BS + "setlength{" + BS + "tabcolsep}{3pt}",
          BS + "begin{tabular}{@{}llllllllll@{}}", BS + "toprule",
          " & ".join(BS + "textbf{" + h + "}" for h in ["DB", "msg\\_id", "src", "dst", "prio", "direction", "status", "body", "hops", "path"]) + " " + BS + BS + " " + BS + "midrule"]
    t1 += [" & ".join(r) + " " + BS + BS for r in rows]
    t1 += [BS + "bottomrule", BS + "end{tabular}", BS + "end{table}"]
    ev = d["events"]
    t2 = [BS + "begin{table}[H]", BS + "caption{Sample rows of " + BS + "texttt{events} on node A for the same message, and of " + BS + "texttt{peers} on node B}",
          BS + "label{tab:samples2}", BS + "footnotesize", BS + "begin{tabular}{@{}llll@{}}", BS + "toprule",
          " & ".join(BS + "textbf{" + h + "}" for h in ["id", "ts\\_ms (relative)", "kind", "peer"]) + " " + BS + BS + " " + BS + "midrule"]
    base = ev[0]["ts_ms"] if ev else 0
    t2 += [f"{e['id']} & +{e['ts_ms'] - base} & {esc(e['kind'])} & {esc(e['peer'])} " + BS + BS for e in ev]
    t2 += [BS + "midrule", " & ".join(BS + "textbf{" + h + "}" for h in ["node\\_id", "role", "link\\_quality", "public\\_key"]) + " " + BS + BS + " " + BS + "midrule"]
    t2 += [f"{esc(p['node_id'])} & {esc(p['role'])} & {'NULL' if p['link_quality'] is None else round(p['link_quality'], 2)} & {'NULL' if p['public_key'] is None else 'BLOB'} " + BS + BS
           for p in d["peers"]]
    t2 += [BS + "bottomrule", BS + "end{tabular}", BS + "end{table}"]
    GEN.mkdir(parents=True, exist_ok=True)
    (GEN / "sample_rows.tex").write_text(chr(10).join(t1) + chr(10), encoding="utf-8")
    print("wrote sample_rows.tex")
    print("\n".join(" | ".join(r) for r in rows))


if __name__ == "__main__":
    main()
