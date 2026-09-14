"""Reliability mechanisms: TTL, dedup, ACK + retry, priority queue,
store-and-forward. Spec: docs/project-plan.md section 9. Each mechanism
exists to prevent exactly one failure mode -- see the pairs table there.
This module is transport-agnostic and testable on its own; node.py wires
it to ``routing.py`` (for next-hop resolution and route recompute on
retry) and to the actual send path in a later step.
"""

from __future__ import annotations

import heapq
import itertools
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from .packet import Packet

# --- section 7.3 constants relevant to reliability ---------------------------

DEDUP_WINDOW = 300.0     # seconds
ACK_TIMEOUT = 4.0        # seconds
MAX_RETRIES = 3
SF_RETRY_INTERVAL = 10.0  # seconds


def _now_ms() -> int:
    return int(time.time() * 1000)


# --- dedup set ----------------------------------------------------------------

class DedupSet:
    """``msg_id -> first-seen time``, expiring after ``window_s`` (section
    9's "Dedup set"). Prevents one message multiplying into thousands of
    forwarded copies (a broadcast storm) when the mesh has cycles."""

    def __init__(self, window_s: float = DEDUP_WINDOW) -> None:
        self._window_ms = int(window_s * 1000)
        self._seen: dict[uuid.UUID, int] = {}

    def seen_before(self, msg_id: uuid.UUID, now_ms: Optional[int] = None) -> bool:
        """Record ``msg_id`` if this is the first time it's been seen
        (within the window), and report whether it was already known.
        Call this once per received packet, before acting on it."""
        now_ms = _now_ms() if now_ms is None else now_ms
        self._prune(now_ms)
        if msg_id in self._seen:
            return True
        self._seen[msg_id] = now_ms
        return False

    def _prune(self, now_ms: int) -> None:
        expired = [mid for mid, seen_ms in self._seen.items() if now_ms - seen_ms > self._window_ms]
        for mid in expired:
            del self._seen[mid]

    def __contains__(self, msg_id: uuid.UUID) -> bool:
        return msg_id in self._seen

    def __len__(self) -> int:
        return len(self._seen)


# --- priority queue -------------------------------------------------------------

class MessagePriorityQueue:
    """Items ordered by a packet's priority rather than arrival order
    (section 9.1). Meant to be re-applied at *every* hop, not only at the
    source -- so an SOS doesn't just start first, it overtakes ordinary
    traffic repeatedly along the whole route. Ties broken by timestamp,
    oldest first. Lower ``Packet.priority`` sorts first: SOS=0, NORMAL=1,
    STATUS=2, matching packet.py's ``Priority`` values directly.

    Ordering is always taken from ``pkt``, but what actually comes back
    out of ``pop``/``peek`` is ``item`` (defaulting to ``pkt`` itself) --
    e.g. relay.py queues ``(next_hop, pkt)`` pairs so the sender loop
    knows where each packet is headed without a second lookup."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int, object]] = []
        self._counter = itertools.count()

    def push(self, pkt: Packet, item: object = None) -> None:
        # the counter breaks ties beyond (priority, timestamp) so heapq
        # never has to compare two items directly (Packet isn't orderable,
        # and priority+timestamp collisions are routine when packets are
        # generated in the same millisecond).
        heapq.heappush(self._heap, (pkt.priority, pkt.timestamp, next(self._counter), item if item is not None else pkt))

    def pop(self) -> object:
        """Highest-priority (then oldest) item. Raises ``IndexError`` if empty."""
        return heapq.heappop(self._heap)[-1]

    def peek(self) -> Optional[object]:
        return self._heap[0][-1] if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)


# --- ACK + retry ----------------------------------------------------------------

@dataclass
class PendingSend:
    pkt: Packet
    next_hop: str
    attempts: int
    sent_at_ms: int


class AckTracker:
    """Tracks messages awaiting an ACK (section 9's "ACK + retry"): the
    sender retries up to ``max_retries`` times, timing out after
    ``timeout_s`` each time. This class only owns the timing/attempt
    bookkeeping -- recomputing the route and actually resending is the
    caller's job (node.py, wired to ``routing.Router`` later), since
    retrying "down a path that has since died" is exactly the failure
    this mechanism exists to prevent (section 9's pairs table).
    """

    def __init__(self, timeout_s: float = ACK_TIMEOUT, max_retries: int = MAX_RETRIES) -> None:
        self._timeout_ms = int(timeout_s * 1000)
        self._max_retries = max_retries
        self._pending: dict[uuid.UUID, PendingSend] = {}

    def register(self, pkt: Packet, next_hop: str, now_ms: Optional[int] = None) -> None:
        """Call right after sending a packet with ``needs_ack`` set."""
        now_ms = _now_ms() if now_ms is None else now_ms
        self._pending[pkt.msg_id] = PendingSend(pkt=pkt, next_hop=next_hop, attempts=1, sent_at_ms=now_ms)

    def acknowledge(self, msg_id: uuid.UUID) -> bool:
        """Call when an ACK for ``msg_id`` arrives. Returns True if it
        matched something we were actually waiting on."""
        return self._pending.pop(msg_id, None) is not None

    def poll_timeouts(self, now_ms: Optional[int] = None) -> tuple[list[PendingSend], list[PendingSend]]:
        """Check every pending send against the timeout.

        Returns ``(to_retry, failed)``:
        - ``to_retry``: still under ``max_retries`` attempts -- attempt
          count bumped and the timer reset here, but the caller must
          still recompute the route (it may have changed) and resend.
        - ``failed``: already used every attempt -- removed from
          tracking; the caller should hand the packet to
          ``StoreForwardQueue`` rather than drop it (section 9).
        """
        now_ms = _now_ms() if now_ms is None else now_ms
        to_retry: list[PendingSend] = []
        failed: list[PendingSend] = []

        for msg_id, entry in list(self._pending.items()):
            if now_ms - entry.sent_at_ms < self._timeout_ms:
                continue
            if entry.attempts >= self._max_retries:
                failed.append(entry)
                del self._pending[msg_id]
            else:
                entry.attempts += 1
                entry.sent_at_ms = now_ms
                to_retry.append(entry)

        return to_retry, failed

    def __len__(self) -> int:
        return len(self._pending)

    def __contains__(self, msg_id: uuid.UUID) -> bool:
        return msg_id in self._pending


# --- store-and-forward ------------------------------------------------------------

class StoreForwardQueue:
    """Holds messages that have no known route right now, instead of
    dropping them (section 9's "Store-and-forward"). A periodic flush
    (every ``SF_RETRY_INTERVAL``, driven by node.py) attempts each queued
    message again -- if a route has since appeared (a node walked out,
    a gateway came back), it sends and clears the queue entry."""

    def __init__(self) -> None:
        self._queue: dict[uuid.UUID, Packet] = {}

    def enqueue(self, pkt: Packet) -> None:
        self._queue[pkt.msg_id] = pkt

    def remove(self, msg_id: uuid.UUID) -> None:
        self._queue.pop(msg_id, None)

    def all(self) -> list[Packet]:
        """Every currently-queued packet, oldest insertion order first."""
        return list(self._queue.values())

    def __len__(self) -> int:
        return len(self._queue)

    def __contains__(self, msg_id: uuid.UUID) -> bool:
        return msg_id in self._queue
