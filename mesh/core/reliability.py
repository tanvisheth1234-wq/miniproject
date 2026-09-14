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
    """Outgoing packets, ordered by priority rather than arrival order
    (section 9.1). Meant to be re-applied at *every* hop, not only at the
    source -- so an SOS doesn't just start first, it overtakes ordinary
    traffic repeatedly along the whole route. Ties broken by timestamp,
    oldest first. Lower ``Packet.priority`` sorts first: SOS=0, NORMAL=1,
    STATUS=2, matching packet.py's ``Priority`` values directly."""

    def __init__(self) -> None:
        self._heap: list[tuple[int, int, int, Packet]] = []
        self._counter = itertools.count()

    def push(self, pkt: Packet) -> None:
        # the counter breaks ties beyond (priority, timestamp) so heapq
        # never has to compare two Packet objects directly (they aren't
        # orderable, and priority+timestamp collisions are routine when
        # packets are generated in the same millisecond).
        heapq.heappush(self._heap, (pkt.priority, pkt.timestamp, next(self._counter), pkt))

    def pop(self) -> Packet:
        """Highest-priority (then oldest) packet. Raises ``IndexError`` if empty."""
        return heapq.heappop(self._heap)[-1]

    def peek(self) -> Optional[Packet]:
        return self._heap[0][-1] if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)
