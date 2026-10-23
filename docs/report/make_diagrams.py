"""All design diagrams of the report, drawn with Graphviz (automatic arrow
routing and label placement) and, for the sequence diagram, a fixed
lifeline layout in matplotlib.

    python docs/report/make_diagrams.py

Needs the Graphviz `dot` executable (set the DOT environment variable or put
it on PATH). Writes PDFs into docs/report/latex/figures/.

Labels use "~" as a line break so that no backslash appears inside an
f-string expression (Python 3.10).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent / "latex" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
DOT = os.environ.get("DOT") or shutil.which("dot") or r"C:\Users\Twissha\Miniconda3\envs\texenv\Library\bin\dot.exe"

FONT = "Arial"
NL = chr(92) + "n"
HEAD = f'''
  graph [fontname="{FONT}", fontsize=12, pad=0.15];
  node  [fontname="{FONT}", fontsize=12, penwidth=1.2, margin="0.12,0.06"];
  edge  [fontname="{FONT}", fontsize=10.5, penwidth=1.1, arrowsize=0.8];
'''
BLUE, GREEN, AMBER, ROSE, GREY, WHITE = "#dbe7fb", "#dff3e6", "#fdf0d8", "#fbe4e2", "#eef0f4", "#ffffff"


def lab(t: str) -> str:
    return t.replace("~", NL)


def render(name: str, body: str, rankdir: str = "TB", extra: str = "") -> None:
    body = lab(body)
    src = f"digraph G {{\n rankdir={rankdir};\n{HEAD}\n{extra}\n{body}\n}}\n"
    (OUT / f"{name}.dot").write_text(src, encoding="utf-8")
    subprocess.run([DOT, "-Tpdf", str(OUT / f"{name}.dot"), "-o", str(OUT / f"{name}.pdf")], check=True)
    (OUT / f"{name}.dot").unlink()
    print("wrote", name)


def box(n, t, fill=WHITE, shape="box"):
    style = "rounded,filled" if shape == "box" else "filled"
    return f'{n} [shape={shape}, style="{style}", fillcolor="{fill}", label="{lab(t)}"];'


def dec(n, t):
    return f'{n} [shape=diamond, style=filled, fillcolor="{AMBER}", label="{lab(t)}", margin="0.02,0.02"];'


def ent(n, t):
    return f'{n} [shape=box, style=filled, fillcolor="{BLUE}", label="{lab(t)}"];'


def proc(n, t):
    return f'{n} [shape=ellipse, style=filled, fillcolor="{GREEN}", label="{lab(t)}"];'


def store(n, label):
    """DFD data store: open-ended rectangle."""
    return (f'{n} [shape=none, label=<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="5" BGCOLOR="{AMBER}">'
            f'<TR><TD SIDES="TB" BORDER="1">{label}</TD></TR></TABLE>>];')


def cls(n, title, rows, fill=WHITE, stereotype=""):
    st = f'<TR><TD><FONT POINT-SIZE="10">&#171;{stereotype}&#187;</FONT></TD></TR>' if stereotype else ""
    body = "".join(f'<TR><TD ALIGN="LEFT">{r}</TD></TR>' for r in rows)
    return (f'{n} [shape=none, label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" BGCOLOR="{fill}">'
            f'{st}<TR><TD><B>{title}</B></TD></TR><HR/>{body}</TABLE>>];')


START = 'start [shape=circle, style=filled, fillcolor=black, label="", width=0.22];'
END = 'end [shape=doublecircle, style=filled, fillcolor=black, label="", width=0.2];'


# ====================================================================== architecture
def architecture() -> None:
    layers = ('<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="6" CELLPADDING="6" BGCOLOR="#ffffff">'
              f'<TR><TD BGCOLOR="{GREEN}">Discovery<BR/><FONT POINT-SIZE="10">HELLO, neighbour table,<BR/>link quality</FONT></TD>'
              f'<TD BGCOLOR="{GREEN}">Routing<BR/><FONT POINT-SIZE="10">link-state gossip,<BR/>graph, Dijkstra</FONT></TD>'
              f'<TD BGCOLOR="{GREEN}">Reliability<BR/><FONT POINT-SIZE="10">TTL, dedup, ACK,<BR/>priority, store-fwd</FONT></TD>'
              f'<TD BGCOLOR="{GREEN}">Crypto<BR/><FONT POINT-SIZE="10">AES-256-GCM,<BR/>Ed25519</FONT></TD>'
              f'<TD BGCOLOR="{GREEN}">Storage<BR/><FONT POINT-SIZE="10">SQLite (WAL):<BR/>messages, events, peers</FONT></TD></TR></TABLE>>')
    body = f'''
  subgraph cluster_node {{
    label="One EcoMesh node (one operating-system process, one event-loop thread)"; labeljust=l; style=rounded; penwidth=1.6; fontsize=13;
    {box("ui", "Web interface~survivor screen | rescue console | engine pages", BLUE)}
    {box("api", "API server (FastAPI)~REST + WebSocket", BLUE)}
    {box("nd", "node.py~wires the layers: send(), ACK/retry loop, store-and-forward flush", AMBER)}
    lay [shape=none, label={layers}];
    {box("tr", "Transport interface~send | broadcast | on_receive | start | stop", GREY)}
    ui -> api [dir=both]; api -> nd [dir=both]; nd -> lay [dir=both]; lay -> tr [dir=both];
  }}
  {box("sim", "SimulatedTransport~in-memory links with loss and latency", ROSE)}
  {box("lan", "LanTransport~TCP sockets + topology file", ROSE)}
  {box("udp", "UdpTcpTransport~UDP multicast + TCP", ROSE)}
  {box("net", "Neighbour nodes~(other processes or laptops)", GREY)}
  tr -> sim [style=dashed, label=" implements"]; tr -> lan [style=dashed]; tr -> udp [style=dashed];
  lan -> net [label=" TCP"]; udp -> net [label=" multicast / TCP"]; sim -> net [label=" simulated"];
  {{rank=same; sim; lan; udp}}
'''
    render("fig_architecture", body, extra="nodesep=0.5; ranksep=0.5;")


# ====================================================================== data flow diagrams
def dfd0() -> None:
    body = f"""
  {proc("P", "0~EcoMesh node~(discover, route, relay,~secure, log, serve screens)")}
  {ent("S", "Survivor")}
  {ent("A", "Administrator")}
  {ent("C", "Rescue coordinator")}
  {ent("N", "Neighbour nodes")}
  {store("D1", "D1  SQLite log (per node)")}
  {{rank=same; S; A}}
  {{rank=same; C; N; D1}}
  S -> P [dir=both, label="in: SOS or message~out: delivery status"];
  A -> P [label="topology file,~role, keys"];
  P -> C [label="SOS queue,~topology,~statistics"];
  P -> N [dir=both, label="HELLO, link-state,~DATA, ACK"];
  P -> D1 [dir=both, label="events, messages,~peers / history"];
"""
    render("fig_dfd0", body, rankdir="TB", extra="nodesep=0.9; ranksep=1.0;")


def dfd1() -> None:
    body = f"""
  {ent("N", "Neighbour nodes")}
  {ent("N2", "Neighbour nodes")}
  {ent("S", "Survivor")}
  {ent("S2", "Survivor")}
  {ent("C", "Rescue coordinator")}
  {proc("P1", "1~Discover~neighbours")}
  {proc("P2", "2~Build graph and~compute route")}
  {proc("P3", "3~Receive, dedup,~verify, decrypt")}
  {proc("P4", "4~Forward in~priority order")}
  {proc("P5", "5~Originate, ACK, retry,~store-and-forward")}
  {proc("P6", "6~Log and serve~API and screens")}
  {store("D1", "D1  neighbour table")}
  {store("D3", "D3  mesh graph")}
  {store("D2", "D2  dedup set")}
  {store("D4", "D4  pending ACKs,<BR/>retention queue")}
  {store("D5", "D5  SQLite log")}
  {{rank=same; N; S}}
  {{rank=same; P1; P2; P3}}
  {{rank=same; D1; D3; D2}}
  {{rank=same; P4; P5; D4}}
  {{rank=same; N2; P6; S2}}
  {{rank=same; C; D5}}
  N -> P1 [label="HELLO"];
  N -> P2 [label="LINK_STATE"];
  N -> P3 [label="DATA, ACK"];
  P1 -> D1 [label="neighbours"];
  P2 -> D3 [label="edges"];
  P3 -> D2 [dir=both, label="seen ids"];
  P3 -> P4 [label="packet to forward"];
  D3 -> P4 [label="next hop"];
  P3 -> P5 [label="ACK"];
  S -> P5 [label="SOS, message"];
  P5 -> D4 [dir=both, label="pending,~retained"];
  P4 -> N2 [label="forwarded packet"];
  P5 -> N2 [label="send, retry, flush"];
  P4 -> P6 [label="events"];
  P5 -> P6 [label="events"];
  P6 -> S2 [label="status, peers"];
  P6 -> D5 [label="writes"];
  P6 -> C [label="SOS queue,~statistics"];
"""
    render("fig_dfd1", body, rankdir="TB", extra="nodesep=0.6; ranksep=0.8;")


# ====================================================================== ER diagram
def er() -> None:
    def table(name, rows):
        body = "".join(f'<TR><TD ALIGN="LEFT">{k}</TD><TD ALIGN="LEFT">{n}</TD><TD ALIGN="LEFT"><FONT COLOR="#555555">{t}</FONT></TD></TR>' for k, n, t in rows)
        return (f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3">'
                f'<TR><TD COLSPAN="3" BGCOLOR="{BLUE}"><B>{name}</B></TD></TR><HR/>{body}</TABLE>>')
    msgs = [("PK", "msg_id", "TEXT"), ("", "src", "TEXT"), ("", "dst", "TEXT"), ("", "priority", "INTEGER"), ("", "direction", "TEXT"), ("IDX", "status", "TEXT"),
            ("", "body", "TEXT"), ("", "created_ms", "INTEGER"), ("", "resolved_ms", "INTEGER"), ("", "hop_count", "INTEGER"), ("", "path", "TEXT")]
    evs = [("PK", "id", "INTEGER"), ("IDX", "ts_ms", "INTEGER"), ("", "kind", "TEXT"), ("FK", "msg_id", "TEXT"), ("FK", "peer", "TEXT"), ("", "detail", "TEXT")]
    prs = [("PK", "node_id", "TEXT"), ("", "role", "TEXT"), ("", "last_seen_ms", "INTEGER"), ("", "link_quality", "REAL"), ("", "public_key", "BLOB")]
    body = f'''
  messages [shape=none, label={table("messages", msgs)}];
  events   [shape=none, label={table("events", evs)}];
  peers    [shape=none, label={table("peers", prs)}];
  messages -> events [dir=both, arrowtail=none, arrowhead=crowodot, taillabel="1", headlabel="N", labeldistance=2.5, labelfontsize=11];
  events -> peers    [dir=both, arrowtail=crowodot, arrowhead=none, taillabel="N", headlabel="0..1", labeldistance=2.5, labelfontsize=11];
'''
    render("fig_er", body, rankdir="LR", extra="nodesep=0.7; ranksep=1.3;")


# ====================================================================== UML
def usecase() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse, FancyBboxPatch, Rectangle

    fig, ax = plt.subplots(figsize=(10.2, 8.6))
    ax.set_xlim(0, 16.4)
    ax.set_ylim(-3.2, 12.8)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((5.2, -2.7), 10.8, 14.9, boxstyle="round,pad=0.02,rounding_size=0.3", fc="white", ec="#1d2433", lw=1.5))
    ax.text(10.6, 11.7, "EcoMesh system", ha="center", va="center", fontsize=13)

    def actor(y, text):
        ax.add_patch(Rectangle((0.4, y - 0.55), 3.4, 1.1, fc="#dbe7fb", ec="#1d2433", lw=1.3, zorder=3))
        ax.text(2.1, y, text, ha="center", va="center", fontsize=11, zorder=4)
        return (3.8, y)

    def uc(x, y, text, w=4.6, h=1.25):
        ax.add_patch(Ellipse((x, y), w, h, fc="white", ec="#1d2433", lw=1.3, zorder=3))
        ax.text(x, y, text, ha="center", va="center", fontsize=10.5, zorder=4)
        return (x - w / 2, y), (x + w / 2, y)

    X = 7.7
    ucs = {"u1": uc(X, 10.2, "Raise SOS"), "u2": uc(X, 8.4, "Send message"), "u3": uc(X, 6.6, "View delivery status"),
           "u4": uc(X, 4.8, "Relay messages"), "u6": uc(X, 3.0, "Act as exit point"), "u7": uc(X, 1.2, "View SOS queue"),
           "u8": uc(X, -0.6, "View mesh topology"), "u9": uc(X, -2.0, "Configure node")}
    ucs["u5"] = uc(12.6, 8.4, "Hold and flush\nundelivered messages", w=4.2, h=1.5)

    def link(a, key):
        ax.plot([a[0], ucs[key][0][0]], [a[1], ucs[key][0][1]], color="#1d2433", lw=1.2, zorder=1)

    trapped = actor(8.4, "Trapped user")
    relay = actor(5.6, "Relay user (passive)")
    gateway = actor(3.9, "Gateway node")
    coord = actor(0.3, "Rescue coordinator")
    admin = actor(-2.0, "Administrator")
    for k in ("u1", "u2", "u3"):
        link(trapped, k)
    link(relay, "u4"); link(gateway, "u4"); link(gateway, "u6")
    link(coord, "u7"); link(coord, "u8"); link(admin, "u9")

    def dashed(p, q, label, lx, ly):
        ax.annotate("", xy=q, xytext=p, arrowprops=dict(arrowstyle="-|>", ls="--", color="#1d2433", lw=1.3, mutation_scale=13), zorder=2)
        ax.text(lx, ly, label, ha="center", va="center", fontsize=10, zorder=5, bbox=dict(fc="white", ec="none", pad=1.5))

    dashed((X, 9.78), (X, 9.02), "\u00abinclude\u00bb", X + 1.0, 9.4)
    dashed(ucs["u5"][0], (X + 2.3, 8.4), "\u00abextend\u00bb", 10.45, 8.75)
    fig.savefig(OUT / "uml_usecase.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote uml_usecase")


def classdiagram() -> None:
    body = f"""
  {cls("NodeC", "Node", ["node_id, role, keys", "send(), start(), stop()"], AMBER)}
  {cls("Disc", "Discovery", ["HELLO, link quality"], GREEN)}
  {cls("Gossip", "LinkStateGossip", ["send_report()", "record_failure()"], GREEN)}
  {cls("Router", "Router", ["next_hop(dst)", "shortest_path(dst)"], GREEN)}
  {cls("Relay", "RelayNode", ["forward(), deliver()", "drop()"], GREEN)}
  {cls("Ack", "AckTracker", ["register()", "poll_timeouts()"], GREEN)}
  {cls("Sf", "StoreForwardQueue", ["enqueue(), expire()"], GREEN)}
  {cls("Store", "Store", ["record_message()", "record_event()"], BLUE)}
  {cls("Packet", "Packet", ["type, priority, ttl, flags", "src, dst, msg_id, path", "pack(), unpack()"])}
  {cls("Crypto", "crypto", ["encrypt / decrypt", "sign / verify"], BLUE, "module")}
  {cls("Transport", "Transport", ["send(), broadcast()", "on_receive(), start(), stop()"], GREY, "interface")}
  {cls("Table", "NeighbourTable", ["update(), prune()"], GREEN)}
  {cls("GraphC", "MeshGraph", ["set_edge(), edge()", "remove_node()"], GREEN)}
  {cls("Dedup", "DedupSet", ["seen_before(key)"], GREEN)}
  {cls("Pq", "MessagePriorityQueue", ["push(), pop()"], GREEN)}
  {cls("Sim", "SimulatedTransport", [""], ROSE)}
  {cls("Lan", "LanTransport", [""], ROSE)}
  {cls("Udp", "UdpTcpTransport", [""], ROSE)}
  NodeC -> Disc   [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Gossip [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Router [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Relay  [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Ack    [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Sf     [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Store  [dir=both, arrowtail=diamond, arrowhead=none];
  NodeC -> Packet [style=dashed, arrowhead=vee, label="builds"];
  NodeC -> Crypto [style=dashed, arrowhead=vee, label="uses"];
  NodeC -> Transport [style=dashed, arrowhead=vee, label="uses"];
  Disc -> Table   [dir=both, arrowtail=diamond, arrowhead=none];
  Router -> GraphC [dir=both, arrowtail=odiamond, arrowhead=none];
  Gossip -> GraphC [dir=both, arrowtail=odiamond, arrowhead=none];
  Relay -> Dedup  [dir=both, arrowtail=odiamond, arrowhead=none];
  Relay -> Pq     [dir=both, arrowtail=diamond, arrowhead=none];
  Transport -> Sim [dir=back, arrowtail=onormal, style=dashed];
  Transport -> Lan [dir=back, arrowtail=onormal, style=dashed];
  Transport -> Udp [dir=back, arrowtail=onormal, style=dashed];
"""
    render("uml_class", body, rankdir="LR", extra="nodesep=0.25; ranksep=0.9;")


def activity() -> None:
    body = f'''
  {START}
  {END}
  {box("rx", "Receive bytes from a neighbour link")}
  {dec("d1", "valid DATA or~ACK packet?")}
  {dec("d2", "already seen?")}
  {dec("d3", "addressed to~this node?")}
  {box("ver", "Verify signature~(if signed)")}
  {dec("d4", "signature and~tag valid?")}
  {box("dc", "Decrypt payload (if encrypted)")}
  {box("del", "Log, send ACK if requested,~deliver to the user", GREEN)}
  {dec("d5", "TTL left, no loop,~route known?")}
  {box("fwd", "ttl - 1, hop_count + 1,~append own id", GREEN)}
  {box("q", "Queue by priority~(SOS first)", GREEN)}
  {box("snd", "Send to the next hop", GREEN)}
  {box("drop", "Drop and log the reason", ROSE)}
  start -> rx -> d1;
  d1 -> d2 [label="yes"]; d1 -> drop [label="no"];
  d2 -> drop [label="yes (re-ACK~if for me)"]; d2 -> d3 [label="no"];
  d3 -> ver [label="yes"]; d3 -> d5 [label="no"];
  ver -> d4; d4 -> dc [label="yes"]; d4 -> drop [label="no"];
  dc -> del -> end;
  d5 -> fwd [label="yes"]; d5 -> drop [label="no"];
  fwd -> q -> snd -> end;
  drop -> end;
'''
    render("uml_activity", body, rankdir="TB", extra="nodesep=0.45; ranksep=0.42;")


def state() -> None:
    body = f'''
  init [shape=circle, style=filled, fillcolor=black, label="", width=0.2];
  {box("created", "Created~(logged as pending)")}
  {box("pending", "Pending~(sent, awaiting ACK)", BLUE)}
  {box("held", "Held~(queued in store-and-forward)", AMBER)}
  {box("delivered", "Delivered", GREEN)}
  {box("failed", "Failed", ROSE)}
  fin1 [shape=doublecircle, style=filled, fillcolor=black, label="", width=0.18];
  fin2 [shape=doublecircle, style=filled, fillcolor=black, label="", width=0.18];
  init -> created [label=" send()"];
  created -> pending [label=" route found, sent"];
  created -> held [label=" no route"];
  created -> delivered [label=" sent, no ACK requested"];
  pending -> delivered [label=" ACK received"];
  pending -> pending [label=" timeout, attempts < 3:~ record failure, new route, resend"];
  pending -> held [label=" attempts exhausted"];
  held -> pending [label=" route appears (flush)"];
  held -> failed [label=" evicted or older than 30 min"];
  delivered -> fin1; failed -> fin2;
'''
    render("uml_state", body, rankdir="TB", extra="nodesep=0.7; ranksep=0.7;")


def deployment() -> None:
    def dev(n, label):
        return (f'{n} [shape=box3d, style=filled, fillcolor="{WHITE}", label=<<B>{label}</B><BR/><FONT POINT-SIZE="10">engine + web screen<BR/>own SQLite file</FONT>>];')
    body = f"""
  subgraph cluster_a {{
    label="Laptop 1"; style="rounded,filled"; fillcolor="{BLUE}"; fontsize=13;
    {dev("L1", "L1  Trapped person")}
    {dev("L2", "L2  Phone 2 (relay)")}
    {dev("L3", "L3  Phone 3 (relay)")}
  }}
  subgraph cluster_b {{
    label="Laptop 2"; labelloc=b; style="rounded,filled"; fillcolor="{GREEN}"; fontsize=13;
    {dev("L4", "L4  Gateway")}
    {dev("L5", "L5  Rescue team")}
  }}
  L1 -> L2 [dir=both, label=" TCP"]; L1 -> L3 [dir=both, label=" TCP"];
  L2 -> L4 [dir=both, label=" TCP"]; L3 -> L4 [dir=both, label=" TCP"];
  L4 -> L5 [dir=both, label=" TCP"];
"""
    render("uml_deploy", body, rankdir="TB", extra="nodesep=0.9; ranksep=0.9;")


# ====================================================================== flowcharts
def flow_send() -> None:
    body = f'''
  {box("start", "send(dst, payload,~priority, needs_ack)", BLUE, "ellipse")}
  {box("enc", "Encrypt payload (if key)~Sign identity (if keypair)", GREEN)}
  {box("log", "Log message: pending")}
  {dec("route", "Route to dst~exists?")}
  {box("hold", "Retain in store-and-forward queue~(bounded; lowest priority evicted first)", AMBER)}
  {box("send", "Send to next hop (TCP)")}
  {dec("needack", "ACK~requested?")}
  {box("best", "Mark delivered~(best effort)")}
  {box("reg", "Register ACK timer~(attempt n)")}
  {dec("ack", "ACK before~timeout?")}
  {box("ok", "Mark delivered", GREEN)}
  {dec("tries", "attempts < 3?")}
  {box("retry", "Record failure on the link (cost +3)~Recompute route, resend", ROSE)}
  {box("flush", "Flush every 10 s:~route exists now?", AMBER)}
  {END}
  start -> enc -> log -> route;
  route -> send [label="yes"]; route -> hold [label="no"];
  send -> needack; needack -> best [label="no"]; needack -> reg [label="yes"];
  reg -> ack; ack -> ok [label="yes"]; ack -> tries [label="no"];
  tries -> retry [label="yes"]; retry -> reg [label="next attempt", constraint=false];
  tries -> hold [label="no"];
  hold -> flush; flush -> send [label="yes", constraint=false];
  best -> end; ok -> end;
'''
    render("fig_flow_send", body, rankdir="TB", extra="nodesep=0.5; ranksep=0.4;")


def flow_route() -> None:
    body = f'''
  {box("start", "next_hop(dst)", BLUE, "ellipse")}
  {dec("cache", "path to dst~cached?")}
  {box("dij", "Dijkstra from this node over the~weighted graph: cost = 1 + 5(1-q) + 3f", GREEN)}
  {dec("resc", "dst = RESCUE__ ?")}
  {box("term", "target = reachable node with role~GATEWAY or RESCUE and least distance")}
  {box("tgt", "target = dst")}
  {dec("found", "target reachable?")}
  {box("path", "Rebuild path from predecessors~Cache it for dst", GREEN)}
  {box("none", "No route:~retain in store-and-forward", ROSE)}
  {box("ret", "Return path[1] as the next hop", GREEN)}
  {END}
  start -> cache; cache -> ret [label="yes"]; cache -> dij [label="no"];
  dij -> resc; resc -> term [label="yes"]; resc -> tgt [label="no"];
  term -> found; tgt -> found;
  found -> path [label="yes"]; found -> none [label="no"];
  path -> ret; ret -> end; none -> end;
'''
    render("fig_flow_route", body, rankdir="TB", extra="nodesep=0.4; ranksep=0.4;")


# ====================================================================== sequence diagram
def sequence() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Rectangle

    parts = ["L1  Trapped person", "L2  Phone 2", "L4  Gateway", "L5  Rescue team"]
    xs = [1.9, 5.7, 9.5, 13.3]
    top, bottom = 12.9, 0.2
    fig, ax = plt.subplots(figsize=(11, 8.6))
    ax.set_xlim(0, 15.9)
    ax.set_ylim(bottom - 0.9, top + 1.1)
    ax.axis("off")
    for x, p in zip(xs, parts):
        ax.add_patch(FancyBboxPatch((x - 1.5, top + 0.1), 3.0, 0.8, boxstyle="round,pad=0.02,rounding_size=0.12", fc="#dbe7fb", ec="#1d2433", lw=1.3, zorder=3))
        ax.text(x, top + 0.5, p, ha="center", va="center", fontsize=11, fontweight="bold", zorder=4)
        ax.plot([x, x], [top + 0.1, bottom], color="#666666", lw=1.1, ls=(0, (5, 4)), zorder=1)

    def msg(i, j, y, text, dashed=False, color="#1d2433"):
        x1, x2 = xs[i], xs[j]
        s = 1 if x2 > x1 else -1
        ax.annotate("", xy=(x2 - 0.08 * s, y), xytext=(x1 + 0.08 * s, y),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5, ls="--" if dashed else "-", mutation_scale=14), zorder=2)
        ax.text((x1 + x2) / 2, y + 0.2, text, ha="center", va="bottom", fontsize=10, color=color, zorder=5,
                bbox=dict(fc="white", ec="none", pad=1.2))

    def note(i, y, text, w=3.4):
        ax.add_patch(Rectangle((xs[i] - w / 2, y - 0.34), w, 0.68, fc="#fdf0d8", ec="#a15c00", lw=1.1, zorder=3))
        ax.text(xs[i], y, text, ha="center", va="center", fontsize=9.5, zorder=4)

    y = top - 0.9
    note(0, y, "create SOS; encrypt, sign", 3.6)
    y -= 1.2; msg(0, 1, y, "1  DATA (SOS, needs_ack), ttl 10")
    y -= 1.2; note(1, y, "dedup; ttl - 1; append L2", 3.7)
    y -= 1.2; msg(1, 2, y, "2  forward DATA (SOS first)")
    y -= 1.2; note(2, y, "dedup; ttl - 1; append L4", 3.7)
    y -= 1.2; msg(2, 3, y, "3  forward DATA")
    y -= 1.2; note(3, y, "verify, decrypt; log, deliver", 3.8)
    y -= 1.2; msg(3, 2, y, "4  ACK (same msg_id)", dashed=True, color="#1f8a4c")
    y -= 0.9; msg(2, 1, y, "5  ACK", dashed=True, color="#1f8a4c")
    y -= 0.9; msg(1, 0, y, "6  ACK", dashed=True, color="#1f8a4c")
    y -= 1.1; note(0, y, "stop timer; delivered", 3.4)
    ax.text(0.2, bottom - 0.45, "Solid arrows: DATA packets. Dashed arrows: the ACK returning along the reverse path.\n"
            "If no ACK arrives within the timeout, L1 records a failure, recomputes the route and resends.", fontsize=9, color="#444444", va="top")
    fig.savefig(OUT / "uml_sequence.pdf", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote uml_sequence")


if __name__ == "__main__":
    architecture()
    dfd0()
    dfd1()
    er()
    usecase()
    classdiagram()
    activity()
    state()
    deployment()
    flow_send()
    flow_route()
    sequence()
