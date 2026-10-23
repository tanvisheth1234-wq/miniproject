"""Result charts for Chapters 8-10, drawn from docs/report/evidence/results/*.json.

    python docs/report/make_charts.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
RES = HERE / "evidence" / "results"
OUT = HERE / "latex" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
GREEN, RED, BLUE, AMBER, GREY = "#2a9d5c", "#d62828", "#2557a7", "#e0a020", "#8b95a8"


def load(name):
    p = RES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=200, facecolor="white")
    plt.close(fig)
    print("wrote", name)


def loss_chart():
    d = load("loss")
    if not d:
        return
    x = [100 * r["loss"] for r in d]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(x, [100 * r["delivery_mean"] for r in d], "o-", color=BLUE, lw=2, label="mean delivery")
    ax.plot(x, [100 * r["delivery_min"] for r in d], "s--", color=GREY, lw=1.3, label="worst run")
    ax.axhline(90, color=RED, ls=":", lw=1.4, label="90 % target")
    ax.set_xlabel("per-link packet loss (%)")
    ax.set_ylabel("messages delivered (%)")
    ax.set_title(f"Delivery under loss ({d[0]['nodes']}-node grid, ACK + retry + re-route)", fontsize=10)
    ax.set_ylim(0, 105)
    ax.grid(alpha=.3)
    ax.legend(fontsize=8, loc="lower left")
    save(fig, "fig_loss.png")


def hopcount_chart():
    d = load("scenarios")
    if not d:
        return
    h = d["scenarios"]["hopcount_vs_weighted"]
    w = [100 * r["delivery"] for r in h["weighted"]["raw"]]
    c = [100 * r["delivery"] for r in h["hopcount"]["raw"]]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    bp = ax.boxplot([w, c], tick_labels=["Weighted\n(link-quality cost)", "Hop count"], widths=0.5, patch_artist=True,
                    medianprops=dict(color="black", lw=2))
    for patch, col in zip(bp["boxes"], (GREEN, RED)):
        patch.set_facecolor(col)
        patch.set_alpha(.55)
    for i, vals in enumerate((w, c), start=1):
        ax.scatter([i + 0.0 + 0.03 * ((k % 5) - 2) for k in range(len(vals))], vals, s=14, color="black", alpha=.55, zorder=3)
        ax.text(i, 3, f"mean {statistics.fmean(vals):.1f} %", ha="center", fontsize=9, fontweight="bold")
    ax.set_ylabel("messages delivered (%)")
    ax.set_ylim(0, 105)
    ax.set_title(f"Same topology, same seeds, {len(w)} runs each (shortcut link has 45 % loss)", fontsize=10)
    ax.grid(axis="y", alpha=.3)
    save(fig, "fig_hopcount.png")


def scale_chart():
    a, b = load("scale"), load("scale_lossy")
    if not a:
        return
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.6))
    for data, label, col in ((a, "5 % loss", GREEN), (b, "20 % loss", AMBER)):
        if not data:
            continue
        ax1.plot([r["nodes"] for r in data], [100 * r["delivery_mean"] for r in data], "o-", color=col, lw=2, label=label)
        ax2.plot([r["nodes"] for r in data], [r["overhead_tx_per_delivered"] for r in data], "o-", color=col, lw=2, label=label)
    ax1.axhline(90, color=RED, ls=":", lw=1.3)
    ax1.set_xlabel("nodes in the mesh")
    ax1.set_ylabel("messages delivered (%)")
    ax1.set_title("Delivery as the mesh grows", fontsize=10)
    ax1.set_ylim(70, 102)
    ax2.set_xlabel("nodes in the mesh")
    ax2.set_ylabel("data transmissions per delivered message")
    ax2.set_title("Message overhead as the mesh grows", fontsize=10)
    for ax in (ax1, ax2):
        ax.grid(alpha=.3)
        ax.legend(fontsize=8)
    save(fig, "fig_scale.png")


def priority_chart():
    d = load("scenarios")
    if not d:
        return
    raw = d["scenarios"]["priority_load"]["weighted"]["raw"]
    def pool(name, key):
        return statistics.fmean(r["by_priority"][name][key] for r in raw if r["by_priority"][name][key] is not None)
    labels, med = ["SOS", "NORMAL"], [pool(n, "median_latency_ms") for n in ("SOS", "NORMAL")]
    p95 = [pool(n, "p95_latency_ms") for n in ("SOS", "NORMAL")]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    xs = range(2)
    ax.bar([i - 0.18 for i in xs], med, width=0.34, color=[RED, BLUE], label="median")
    ax.bar([i + 0.18 for i in xs], p95, width=0.34, color=[RED, BLUE], alpha=.45, label="95th percentile")
    for i, (m, q) in enumerate(zip(med, p95)):
        ax.text(i - 0.18, m + 40, f"{m:.0f}", ha="center", fontsize=9, fontweight="bold")
        ax.text(i + 0.18, q + 40, f"{q:.0f}", ha="center", fontsize=9)
    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels)
    ax.set_ylabel("end-to-end latency (ms)")
    adv = d["scenarios"]["priority_load"]["weighted"]["sos_latency_advantage"]
    ax.set_title(f"SOS under load: {adv:.1f}x lower median latency (16 nodes, slow radio)", fontsize=10)
    ax.grid(axis="y", alpha=.3)
    ax.legend(fontsize=8)
    save(fig, "fig_priority.png")


def recovery_chart():
    d = load("scenarios")
    if not d:
        return
    raw = d["scenarios"]["collapse_40"]["weighted"]["raw"]
    rec = [r["recovery_s"] for r in raw if r["recovery_s"] is not None]
    conv = [r["convergence_s"] for r in raw if r["convergence_s"] is not None]
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 3.4))
    a.hist(rec, bins=[i * 0.5 for i in range(0, 24)], color=BLUE, alpha=.8, edgecolor="white")
    a.axvline(10, color=RED, ls=":", lw=1.6, label="10 s target")
    a.set_xlabel("seconds from relay death to a route that avoids it")
    a.set_ylabel(f"trials (n = {len(rec)})")
    a.set_title("Recovery time", fontsize=10)
    a.legend(fontsize=8)
    b.hist(conv, bins=[i * 1.0 for i in range(3, 19)], color=GREEN, alpha=.8, edgecolor="white")
    b.axvline(15, color=RED, ls=":", lw=1.6, label="15 s target")
    b.set_xlabel("seconds until every node knows every node")
    b.set_ylabel(f"runs (n = {len(conv)})")
    b.set_title("Convergence time (40-node mesh, 20 % loss)", fontsize=10)
    b.legend(fontsize=8)
    for ax in (a, b):
        ax.grid(alpha=.3)
    save(fig, "fig_recovery.png")


def results_grid():
    """Four panels in one figure: loss, weighted vs hop count, scale, recovery."""
    loss, sc, a, b = load("loss"), load("scenarios"), load("scale"), load("scale_lossy")
    if not (loss and sc and a):
        return
    fig, ax = plt.subplots(2, 2, figsize=(10, 6.6))
    p = ax[0][0]
    x = [100 * r["loss"] for r in loss]
    p.plot(x, [100 * r["delivery_mean"] for r in loss], "o-", color=BLUE, lw=2, label="mean")
    p.plot(x, [100 * r["delivery_min"] for r in loss], "s--", color=GREY, lw=1.2, label="worst run")
    p.axhline(90, color=RED, ls=":", lw=1.3)
    p.set_title("(a) Delivery vs per-link loss (21 nodes)", fontsize=10)
    p.set_xlabel("per-link loss (%)")
    p.set_ylabel("delivered (%)")
    p.set_ylim(0, 105)
    p.legend(fontsize=8, loc="lower left")
    h = sc["scenarios"]["hopcount_vs_weighted"]
    w, c = [100 * r["delivery"] for r in h["weighted"]["raw"]], [100 * r["delivery"] for r in h["hopcount"]["raw"]]
    p = ax[0][1]
    bp = p.boxplot([w, c], tick_labels=["Weighted", "Hop count"], widths=0.5, patch_artist=True, medianprops=dict(color="black", lw=2))
    for patch, col in zip(bp["boxes"], (GREEN, RED)):
        patch.set_facecolor(col)
        patch.set_alpha(.55)
    for i, vals in enumerate((w, c), start=1):
        p.text(i, 4, f"mean {statistics.fmean(vals):.1f} %", ha="center", fontsize=9, fontweight="bold")
    p.set_title(f"(b) Same topology and seeds, {len(w)} runs", fontsize=10)
    p.set_ylabel("delivered (%)")
    p.set_ylim(0, 105)
    p = ax[1][0]
    for data, label, col in ((a, "5 % loss", GREEN), (b, "20 % loss", AMBER)):
        if data:
            p.plot([r["nodes"] for r in data], [100 * r["delivery_mean"] for r in data], "o-", color=col, lw=2, label=label)
    p.axhline(90, color=RED, ls=":", lw=1.3)
    p.set_title("(c) Delivery as the mesh grows", fontsize=10)
    p.set_xlabel("nodes")
    p.set_ylabel("delivered (%)")
    p.set_ylim(70, 102)
    p.legend(fontsize=8, loc="lower left")
    raw = sc["scenarios"]["collapse_40"]["weighted"]["raw"]
    rec = [r["recovery_s"] for r in raw if r["recovery_s"] is not None]
    p = ax[1][1]
    p.hist(rec, bins=[i * 0.5 for i in range(0, 24)], color=BLUE, alpha=.85, edgecolor="white")
    p.axvline(10, color=RED, ls=":", lw=1.6, label="10 s target")
    p.set_title(f"(d) Recovery after a relay dies ({len(rec)} trials)", fontsize=10)
    p.set_xlabel("seconds until a route avoiding the dead relay")
    p.set_ylabel("trials")
    p.legend(fontsize=8)
    for row in ax:
        for q in row:
            q.grid(alpha=.3)
    save(fig, "fig_results.png")


if __name__ == "__main__":
    results_grid()
    loss_chart()
    hopcount_chart()
    scale_chart()
    priority_chart()
    recovery_chart()
