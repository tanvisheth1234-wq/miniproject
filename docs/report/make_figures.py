"""Structural figures for the report (architecture, DFDs, ER diagram, cost\nfunction). Writes PNGs into docs/report/latex/figures/.\n\n    python docs/report/make_figures.py\n"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Ellipse

OUT = Path(__file__).resolve().parent / "latex" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

INK, MUTED = "#1d2433", "#5d6677"
BLUE, GREEN, AMBER, RED, GREY = "#dbe7fb", "#dff3e6", "#fdf0d8", "#fbe4e2", "#eef0f4"


def box(ax, x, y, w, h, text, fc=GREY, ec=INK, fs=9, bold=False, style="round,pad=0.02,rounding_size=0.08", lw=1.2):
    p = FancyBboxPatch((x, y), w, h, boxstyle=style, fc=fc, ec=ec, lw=lw)
    ax.add_patch(p)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=INK,
            fontweight="bold" if bold else "normal", linespacing=1.25)


def arrow(ax, x1, y1, x2, y2, text="", color=INK, both=False, fs=7.5, off=(0, 0.12), ls="-"):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="<->" if both else "->", color=color, lw=1.2, ls=ls))
    if text:
        ax.text((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1], text, ha="center", va="center", fontsize=fs, color=MUTED,
                bbox=dict(fc="white", ec="none", pad=0.6))


def canvas(w, h, wi=9.5, hi=None):
    fig, ax = plt.subplots(figsize=(wi, hi or wi * h / w))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", name)


# ---------------------------------------------------------------- architecture
def architecture():
    fig, ax = canvas(12.6, 8.6)
    ax.add_patch(Rectangle((0.3, 1.9), 8.5, 6.4, fc="white", ec=INK, lw=1.6))
    ax.text(0.55, 8.1, "One EcoMesh node (one OS process, one event-loop thread)", fontsize=9.5, fontweight="bold", va="top")
    x0, w = 0.6, 7.9
    box(ax, x0, 6.9, w, 0.75, "Web interface:  survivor screen  |  rescue console  |  engine pages", BLUE, fs=8.5)
    box(ax, x0, 5.9, w, 0.7, "API server (FastAPI):  REST + WebSocket", BLUE, fs=8.5)
    box(ax, x0, 4.95, w, 0.7, "node.py:  wires the layers;  send(), ACK/retry, store-and-forward", AMBER, fs=8.5, bold=True)
    names = [("Discovery\nHELLO, neighbours,\nlink quality", GREEN), ("Routing\nlink-state gossip,\nDijkstra", GREEN),
             ("Reliability\nTTL, dedup, ACK,\npriority, S&F", GREEN), ("Crypto\nAES-256-GCM,\nEd25519", GREEN),
             ("Storage\nSQLite (WAL)\nmessages, events", GREEN)]
    bw, gap = 1.5, 0.1
    for i, (t, c) in enumerate(names):
        box(ax, x0 + i * (bw + gap), 3.35, bw, 1.35, t, c, fs=6.9)
    box(ax, x0, 2.1, w, 0.9, "Transport interface:  send | broadcast | on_receive | start | stop", GREY, fs=8.6, bold=True)
    for yy in (6.9, 5.9, 4.95, 3.35):
        ax.annotate("", xy=(x0 + w / 2, yy - 0.25), xytext=(x0 + w / 2, yy), arrowprops=dict(arrowstyle="<->", color=MUTED, lw=1))
    ix = 9.4
    box(ax, ix, 6.4, 2.9, 1.3, "SimulatedTransport\nin-memory links with\nloss and latency\n(simulator, tests)", RED, fs=8)
    box(ax, ix, 4.5, 2.9, 1.3, "LanTransport\nTCP sockets + topology\nfile (live multi-device,\nrange emulation)", RED, fs=8)
    box(ax, ix, 2.6, 2.9, 1.3, "UdpTcpTransport\nUDP multicast + TCP\n(original transport)", RED, fs=8)
    for yy in (7.05, 5.15, 3.25):
        arrow(ax, 8.5, 2.55, ix, yy, color=MUTED, ls="--")
    ax.text(ix + 1.45, 8.1, "Three interchangeable\nimplementations", ha="center", fontsize=8.5, fontweight="bold")
    box(ax, ix, 0.5, 2.9, 1.0, "Neighbour nodes\n(other processes / laptops)", GREY, fs=8.5)
    arrow(ax, ix + 1.45, 2.6, ix + 1.45, 1.5, "bytes over TCP", off=(0.85, 0))
    ax.text(0.3, 1.55, "Everything above the transport interface is identical in the simulator, on loopback\nsockets and on separate laptops.",
            fontsize=8.2, color=MUTED, va="top")
    save(fig, "fig_architecture.png")


# ---------------------------------------------------------------- DFD
def circle(ax, x, y, text, w=2.5, h=1.15, fc=GREEN, fs=8):
    ax.add_patch(Ellipse((x, y), w, h, fc=fc, ec=INK, lw=1.2))
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, linespacing=1.2)


def store(ax, x, y, w, h, text, fs=7.8):
    ax.plot([x, x + w], [y + h, y + h], color=INK, lw=1.4)
    ax.plot([x, x + w], [y, y], color=INK, lw=1.4)
    ax.plot([x, x], [y, y + h], color=INK, lw=1.4)
    ax.add_patch(Rectangle((x, y), w, h, fc=AMBER, ec="none", zorder=0))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)


def dfd0():
    fig, ax = canvas(12, 6.4)
    circle(ax, 6, 3.2, "0\nEcoMesh node\n(discover, route, relay,\nsecure, log, serve UI)", w=3.6, h=2.2, fs=9)
    box(ax, 0.3, 4.9, 2.4, 0.9, "Survivor\n(trapped user)", BLUE)
    box(ax, 9.3, 4.9, 2.4, 0.9, "Rescue coordinator", BLUE)
    box(ax, 0.3, 0.6, 2.4, 0.9, "Neighbour nodes\n(relays, gateway)", BLUE)
    box(ax, 9.3, 0.6, 2.4, 0.9, "Administrator", BLUE)
    store(ax, 4.6, 0.3, 2.8, 0.6, "D1  SQLite log (per node)")
    arrow(ax, 2.7, 5.2, 4.7, 3.9, "SOS / message, destination", off=(-0.3, 0.2))
    arrow(ax, 4.5, 3.4, 2.7, 4.9, "delivery state,\npeers, hop path", off=(0.3, -0.3), ls=":")
    arrow(ax, 7.4, 3.9, 9.3, 5.2, "SOS queue, topology,\nstatistics", off=(0.2, 0.3))
    arrow(ax, 2.7, 1.1, 4.5, 2.6, "HELLO, link-state, DATA,\nACK packets", off=(-0.2, -0.3), both=True)
    arrow(ax, 9.3, 1.1, 7.5, 2.4, "topology file, role,\nkeys", off=(0.3, -0.35))
    arrow(ax, 6, 2.1, 6, 0.9, "events, messages, peers", both=True, off=(1.1, 0))
    ax.text(6, 6.15, "Level-0 data flow diagram (context): the system boundary contains no server", ha="center", fontsize=9.5, fontweight="bold")
    save(fig, "fig_dfd0.png")


def dfd1():
    fig, ax = canvas(14, 8.8, wi=11)
    ax.text(7, 8.55, "Level-1 data flow diagram of one node", ha="center", fontsize=10.5, fontweight="bold")
    box(ax, 0.2, 7.3, 2.2, 0.8, "Neighbour nodes", BLUE, fs=8.5)
    box(ax, 0.2, 0.5, 2.2, 0.8, "Survivor", BLUE, fs=8.5)
    box(ax, 11.6, 0.5, 2.2, 0.8, "Rescue coordinator", BLUE, fs=8.5)
    circle(ax, 4.2, 7.5, "1\nDiscover\nneighbours", w=2.4)
    circle(ax, 8.0, 7.5, "2\nBuild graph &\ncompute route", w=2.6)
    circle(ax, 4.2, 4.6, "3\nReceive, dedup,\nverify, decrypt", w=2.6)
    circle(ax, 8.0, 4.6, "4\nForward in\npriority order", w=2.6)
    circle(ax, 11.8, 4.6, "5\nACK, retry,\nstore-and-forward", w=2.6)
    circle(ax, 6.0, 1.7, "6\nLog & serve\nAPI / UI", w=2.6)
    store(ax, 1.2, 5.5, 1.9, 0.55, "D2 dedup set", fs=7.5)
    store(ax, 5.3, 6.2, 1.6, 0.5, "D1 neighbours", fs=7.5)
    store(ax, 9.7, 7.3, 1.9, 0.5, "D3 mesh graph", fs=7.5)
    store(ax, 11.4, 5.9, 2.2, 0.55, "D4 pending ACKs +\nretention queue", fs=7.2)
    store(ax, 8.9, 0.25, 2.2, 0.6, "D5 SQLite log", fs=8)
    arrow(ax, 2.4, 7.7, 3.0, 7.6, "HELLO", off=(0, 0.2))
    arrow(ax, 5.4, 7.5, 6.7, 7.5, "neighbour list", off=(0, 0.2))
    arrow(ax, 2.0, 7.3, 3.2, 5.1, "DATA / ACK /\nLINK_STATE", off=(-0.7, 0), both=False)
    arrow(ax, 5.5, 4.6, 6.7, 4.6, "packet to\nforward", off=(0, 0.28))
    arrow(ax, 9.3, 4.6, 10.5, 4.6, "sent, awaiting ACK", off=(0, 0.28))
    arrow(ax, 8.0, 6.9, 8.0, 5.2, "next hop", off=(0.5, 0))
    arrow(ax, 4.2, 6.9, 5.6, 6.5, "", both=True, color=MUTED)      # 1 <-> D1
    arrow(ax, 9.3, 7.5, 9.7, 7.55, "", both=True, color=MUTED)     # 2 <-> D3
    arrow(ax, 3.0, 5.0, 3.1, 5.75, "", both=True, color=MUTED)     # 3 <-> D2
    arrow(ax, 12.2, 5.2, 12.5, 5.9, "", both=True, color=MUTED)    # 5 <-> D4
    arrow(ax, 4.2, 4.0, 5.2, 2.2, "delivered /\nforwarded events", off=(-0.9, 0))
    arrow(ax, 8.0, 4.0, 6.8, 2.2, "forward events", off=(0.85, -0.1))
    arrow(ax, 11.8, 4.0, 7.2, 1.9, "retry / queue events", off=(1.4, 0.0))
    arrow(ax, 7.3, 1.7, 8.9, 0.6, "writes", off=(0.15, -0.3))
    arrow(ax, 4.7, 1.5, 2.4, 0.9, "status, peers,\nroute", off=(-0.3, 0.45))
    arrow(ax, 2.4, 0.8, 4.7, 1.5, "SOS", off=(0, -0.3))
    arrow(ax, 7.3, 1.9, 11.6, 0.9, "SOS queue,\nstatistics", off=(0.3, 0.45))
    save(fig, "fig_dfd1.png")


# ---------------------------------------------------------------- ER diagram
def entity(ax, x, y, title, rows, w=4.3):
    h = 0.5 + 0.42 * len(rows)
    ax.add_patch(Rectangle((x, y), w, h, fc="white", ec=INK, lw=1.4))
    ax.add_patch(Rectangle((x, y + h - 0.5), w, 0.5, fc=BLUE, ec=INK, lw=1.4))
    ax.text(x + w / 2, y + h - 0.25, title, ha="center", va="center", fontsize=10, fontweight="bold")
    for i, (name, typ, tag) in enumerate(rows):
        yy = y + h - 0.5 - 0.42 * (i + 1) + 0.21
        ax.text(x + 0.15, yy, tag, fontsize=7.5, va="center", color="#b3261e", fontweight="bold")
        ax.text(x + 0.75, yy, name, fontsize=8.5, va="center")
        ax.text(x + w - 0.15, yy, typ, fontsize=8, va="center", ha="right", color=MUTED)
    return h


def er():
    fig, ax = canvas(15, 7.4, wi=11.5)
    entity(ax, 0.2, 0.9, "messages", [("msg_id", "TEXT", "PK"), ("src", "TEXT", ""), ("dst", "TEXT", ""), ("priority", "INTEGER", ""),
            ("direction", "TEXT", ""), ("status", "TEXT", "IDX"), ("body", "TEXT", ""), ("created_ms", "INTEGER", ""),
            ("resolved_ms", "INTEGER", ""), ("hop_count", "INTEGER", ""), ("path", "TEXT", "")])
    entity(ax, 5.4, 2.4, "events", [("id", "INTEGER", "PK"), ("ts_ms", "INTEGER", "IDX"), ("kind", "TEXT", ""), ("msg_id", "TEXT", "FK*"),
            ("peer", "TEXT", "FK*"), ("detail", "TEXT", "")])
    entity(ax, 10.6, 1.4, "peers", [("node_id", "TEXT", "PK"), ("role", "TEXT", ""), ("last_seen_ms", "INTEGER", ""),
            ("link_quality", "REAL", ""), ("public_key", "BLOB", "")])
    arrow(ax, 5.4, 3.9, 4.5, 3.9, "1 : N", off=(0, 0.3))
    arrow(ax, 9.7, 4.1, 10.6, 3.6, "N : 1", off=(0, 0.3))
    ax.text(0.2, 7.0, "Entity-relationship diagram of the per-node SQLite database", fontsize=10.5, fontweight="bold", va="center")
    ax.text(0.2, 0.35, "PK = primary key,  IDX = secondary index (idx_msg_status, idx_events_ts),  FK* = logical foreign key "
            "(events.msg_id $\\rightarrow$ messages.msg_id, events.peer $\\rightarrow$ peers.node_id);\nnot declared as an SQL constraint, because a node logs events for messages it only relays and for peers that may already have expired.",
            fontsize=7.8, color=MUTED, va="center")
    save(fig, "fig_er.png")


# ---------------------------------------------------------------- cost function
def cost():
    import numpy as np
    q = np.linspace(0, 1, 101)
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.6))
    for f, c in ((0, "#2a9d5c"), (1, "#e0a020"), (2, "#d62828")):
        a.plot(q, 1 + 5 * (1 - q) + 3 * f, color=c, lw=2, label=f"f = {f} recent failures")
    a.set_xlabel("link quality q (fraction of last 20 HELLOs received)")
    a.set_ylabel("edge cost")
    a.set_title("cost(q, f) = 1 + 5(1 - q) + 3f", fontsize=10)
    a.grid(alpha=.3)
    a.legend(fontsize=8)
    # example: 2 hops over strong links vs 1 hop over a weak link
    labels = ["Path A\n1 hop, q = 0.4", "Path B\n2 hops, q = 1.0 each"]
    costs = [1 + 5 * 0.6, 2 * 1.0]
    bars = b.bar(labels, costs, color=["#d62828", "#2a9d5c"], width=0.5)
    for r, v in zip(bars, costs):
        b.text(r.get_x() + r.get_width() / 2, v + 0.1, f"{v:.1f}", ha="center", fontsize=10, fontweight="bold")
    b.set_ylabel("total path cost")
    b.set_title("Why hop count is a poor proxy: Dijkstra picks B", fontsize=10)
    b.set_ylim(0, 5.2)
    b.grid(axis="y", alpha=.3)
    fig.tight_layout()
    save(fig, "fig_cost.png")


# ---------------------------------------------------------------- flowchart
def diamond(ax, x, y, w, h, text, fc=AMBER, fs=7.8):
    ax.add_patch(plt.Polygon([(x, y + h / 2), (x + w / 2, y + h), (x + w, y + h / 2), (x + w / 2, y)], fc=fc, ec=INK, lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, linespacing=1.2)


def flow_send():
    fig, ax = canvas(13, 9.2, wi=11)
    ax.text(6.5, 8.95, "Flowchart: originate a message, acknowledge, retry, retain", ha="center", fontsize=10.5, fontweight="bold")
    box(ax, 0.3, 7.8, 2.6, 0.7, "send(dst, payload,\npriority, needs_ack)", BLUE, fs=8)
    box(ax, 3.5, 7.8, 2.6, 0.7, "encrypt payload (if key)\nsign identity (if keypair)", GREEN, fs=7.8)
    box(ax, 6.7, 7.8, 2.6, 0.7, "log message: pending", GREY, fs=8)
    diamond(ax, 4.6, 5.9, 3.6, 1.4, "route to dst?\n(Dijkstra / RESCUE__)")
    box(ax, 9.7, 6.15, 3.0, 0.9, "RETAIN: store-and-forward\nqueue (bounded, evict lowest\npriority); status queued_sf", AMBER, fs=7.6)
    box(ax, 4.9, 4.55, 3.0, 0.75, "send to next hop\n(per-hop TCP)", GREEN, fs=8)
    diamond(ax, 4.6, 2.8, 3.6, 1.4, "needs ACK?")
    box(ax, 0.3, 3.0, 3.2, 1.0, "mark delivered\n(best effort: nothing\nleft to confirm)", GREY, fs=7.8)
    box(ax, 4.9, 1.6, 3.0, 0.75, "register in AckTracker\n(attempt 1, timer)", GREEN, fs=8)
    diamond(ax, 4.6, 0.2, 3.6, 1.3, "ACK before\n4 s timeout?")
    box(ax, 9.7, 0.35, 3.0, 1.0, "delivered:\nclear pending, log ack,\nstatus delivered", GREEN, fs=7.8)
    box(ax, 9.7, 2.1, 3.0, 1.25, "timeout: record failure on the\nlink (cost +3), RECOMPUTE\nroute, resend (<= 3 attempts)", RED, fs=7.4)
    box(ax, 0.3, 0.3, 3.4, 1.1, "attempts exhausted:\nhand to store-and-forward\n(never silently dropped)", AMBER, fs=7.8)
    arrow(ax, 2.9, 8.15, 3.5, 8.15)
    arrow(ax, 6.1, 8.15, 6.7, 8.15)
    arrow(ax, 8.0, 7.8, 6.4, 7.3)
    arrow(ax, 8.2, 6.6, 9.7, 6.6, "no", off=(0, 0.2))
    arrow(ax, 6.4, 5.9, 6.4, 5.3, "yes", off=(0.3, 0))
    arrow(ax, 6.4, 4.55, 6.4, 4.2)
    arrow(ax, 4.6, 3.5, 3.5, 3.5, "no", off=(0, 0.2))
    arrow(ax, 6.4, 2.8, 6.4, 2.35, "yes", off=(0.3, 0))
    arrow(ax, 6.4, 1.6, 6.4, 1.5)
    arrow(ax, 8.2, 0.85, 9.7, 0.85, "yes", off=(0, 0.2))
    arrow(ax, 8.2, 1.1, 9.7, 2.3, "no", off=(-0.15, 0.2))
    arrow(ax, 11.2, 3.35, 7.9, 4.8, "resend", off=(0.9, -0.1), ls="--")
    arrow(ax, 4.6, 0.85, 3.7, 0.85, "retries used up", off=(0, 0.25), ls="--")
    arrow(ax, 10.3, 6.15, 7.9, 5.1, "flush every 10 s: a route now exists", off=(1.1, 0.35), ls="--")
    save(fig, "fig_flow_send.png")


if __name__ == "__main__":
    flow_send()
    architecture()
    dfd0()
    dfd1()
    er()
    cost()
