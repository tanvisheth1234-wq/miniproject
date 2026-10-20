"""Section 16's metrics, computed the way section 11 promises they are:
every number is a query against the nodes' ``messages`` and ``events``
tables. Works on any set of stores, so the live lab and the headless
simulator share one definition of "delivery ratio".

"Delivered" here means *the destination actually received it* (a
``received`` row exists somewhere), not "the sender was told so" -- the two
differ when an ACK is lost, and the ground truth is the stricter one. The
sender-side view is reported alongside as ``sender_confirmed``.
"""

from __future__ import annotations

import statistics
from collections import Counter
from typing import Mapping, Optional

from mesh.core.store import Store

PRIORITY_NAMES = {0: "SOS", 1: "NORMAL", 2: "STATUS"}

_DROP_KINDS = (
    "drop_ttl", "drop_dup", "drop_loop", "drop_no_route", "drop_send_failed",
    "drop_decrypt_failed", "drop_signature_invalid", "drop_unknown_signer", "drop_no_key",
)


def _median(values: list[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _mean(values: list[float]) -> Optional[float]:
    return statistics.fmean(values) if values else None


def receive_times(stores: Mapping[str, Store]) -> dict[str, int]:
    """msg_id -> the moment (ms) a destination handed it to the application."""
    out: dict[str, int] = {}
    for store in stores.values():
        for event in store.events_by_kind("recv"):
            if event["msg_id"] is not None:
                out.setdefault(event["msg_id"], event["ts_ms"])
    return out


def compute_metrics(stores: Mapping[str, Store]) -> dict:
    sent_rows: dict[str, dict] = {}
    received_rows: dict[str, dict] = {}
    for store in stores.values():
        for row in store.list_messages(direction="sent"):
            sent_rows[row["msg_id"]] = row
        for row in store.list_messages(direction="received"):
            received_rows.setdefault(row["msg_id"], row)

    arrived = {mid for mid in sent_rows if mid in received_rows}
    recv_ms = receive_times(stores)

    hops = [received_rows[mid]["hop_count"] for mid in arrived if received_rows[mid]["hop_count"] is not None]
    hop_histogram = dict(sorted(Counter(hops).items()))

    latency_by_priority: dict[str, list[float]] = {name: [] for name in PRIORITY_NAMES.values()}
    for mid in arrived:
        if mid in recv_ms:
            latency_by_priority[PRIORITY_NAMES.get(sent_rows[mid]["priority"], "NORMAL")].append(
                max(0, recv_ms[mid] - sent_rows[mid]["created_ms"])
            )

    per_priority = {}
    for pid, name in PRIORITY_NAMES.items():
        sent_p = [m for m, r in sent_rows.items() if r["priority"] == pid]
        got_p = [m for m in sent_p if m in received_rows]
        per_priority[name] = {
            "sent": len(sent_p),
            "delivered": len(got_p),
            "median_latency_ms": _median(latency_by_priority[name]),
            "mean_latency_ms": _mean(latency_by_priority[name]),
        }

    sos_median = per_priority["SOS"]["median_latency_ms"]
    normal_median = per_priority["NORMAL"]["median_latency_ms"]
    advantage = (normal_median / sos_median) if sos_median and normal_median else None

    status_counts = Counter(r["status"] for r in sent_rows.values())
    event_totals: Counter = Counter()
    for store in stores.values():
        for kind in ("sent", "recv", "forward", "ack", "retry", "sf_queue", "sf_flush", *_DROP_KINDS):
            event_totals[kind] += store.count_events(kind)

    dup_drops = event_totals["drop_dup"]
    packets_received = event_totals["recv"] + event_totals["forward"] + sum(event_totals[k] for k in _DROP_KINDS)

    return {
        "sent": len(sent_rows),
        "delivered": len(arrived),
        "delivery_ratio": (len(arrived) / len(sent_rows)) if sent_rows else None,
        "sender_confirmed": status_counts.get("delivered", 0),
        "sender_status": dict(status_counts),
        "mean_hops": _mean(hops),
        "median_hops": _median(hops),
        "hop_histogram": hop_histogram,
        "by_priority": per_priority,
        "sos_latency_advantage": advantage,
        "retries": event_totals["retry"],
        "store_forward_queued": event_totals["sf_queue"],
        "store_forward_flushed": event_totals["sf_flush"],
        "drops": {k.removeprefix("drop_"): event_totals[k] for k in _DROP_KINDS if event_totals[k]},
        "dedup_drop_ratio": (dup_drops / packets_received) if packets_received else None,
    }
