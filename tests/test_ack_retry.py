import uuid

from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.reliability import AckTracker, StoreForwardQueue


def _pkt(msg_id: uuid.UUID = None) -> Packet:
    return Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="A", dst="C", msg_id=msg_id or uuid.uuid4())


# --- AckTracker -----------------------------------------------------------------

def test_acknowledge_before_timeout_clears_pending():
    tracker = AckTracker(timeout_s=4)
    pkt = _pkt()
    tracker.register(pkt, next_hop="B", now_ms=0)

    assert tracker.acknowledge(pkt.msg_id) is True
    assert pkt.msg_id not in tracker
    assert len(tracker) == 0


def test_acknowledge_unknown_msg_id_returns_false():
    tracker = AckTracker()
    assert tracker.acknowledge(uuid.uuid4()) is False


def test_no_timeout_before_deadline():
    tracker = AckTracker(timeout_s=4)
    pkt = _pkt()
    tracker.register(pkt, next_hop="B", now_ms=0)

    to_retry, failed = tracker.poll_timeouts(now_ms=3_000)
    assert to_retry == []
    assert failed == []
    assert pkt.msg_id in tracker


def test_timeout_triggers_retry_and_resets_timer():
    tracker = AckTracker(timeout_s=4, max_retries=3)
    pkt = _pkt()
    tracker.register(pkt, next_hop="B", now_ms=0)

    to_retry, failed = tracker.poll_timeouts(now_ms=4_000)
    assert failed == []
    assert len(to_retry) == 1
    assert to_retry[0].attempts == 2
    assert to_retry[0].next_hop == "B"

    # timer was reset at 4000ms -- polling again immediately shouldn't refire
    to_retry_2, failed_2 = tracker.poll_timeouts(now_ms=4_500)
    assert to_retry_2 == []
    assert failed_2 == []


def test_exhausting_max_retries_reports_failed_and_stops_tracking():
    tracker = AckTracker(timeout_s=4, max_retries=3)
    pkt = _pkt()
    tracker.register(pkt, next_hop="B", now_ms=0)

    tracker.poll_timeouts(now_ms=4_000)   # attempt 2
    tracker.poll_timeouts(now_ms=8_000)   # attempt 3
    to_retry, failed = tracker.poll_timeouts(now_ms=12_000)  # exhausted

    assert to_retry == []
    assert len(failed) == 1
    assert failed[0].pkt.msg_id == pkt.msg_id
    assert failed[0].attempts == 3
    assert pkt.msg_id not in tracker


def test_multiple_pending_sends_tracked_independently():
    tracker = AckTracker(timeout_s=4)
    a, b = _pkt(), _pkt()
    tracker.register(a, next_hop="X", now_ms=0)
    tracker.register(b, next_hop="Y", now_ms=1_000)

    to_retry, failed = tracker.poll_timeouts(now_ms=4_500)
    assert {entry.pkt.msg_id for entry in to_retry} == {a.msg_id}

    to_retry_2, _ = tracker.poll_timeouts(now_ms=5_500)
    assert {entry.pkt.msg_id for entry in to_retry_2} == {b.msg_id}


# --- StoreForwardQueue ------------------------------------------------------------

def test_enqueue_and_all():
    q = StoreForwardQueue()
    pkt = _pkt()
    q.enqueue(pkt)
    assert len(q) == 1
    assert pkt.msg_id in q
    assert q.all() == [pkt]


def test_remove_clears_entry():
    q = StoreForwardQueue()
    pkt = _pkt()
    q.enqueue(pkt)
    q.remove(pkt.msg_id)
    assert len(q) == 0
    assert pkt.msg_id not in q


def test_remove_unknown_id_is_a_no_op():
    q = StoreForwardQueue()
    q.remove(uuid.uuid4())  # should not raise
    assert len(q) == 0


def test_enqueue_same_msg_id_twice_does_not_duplicate():
    q = StoreForwardQueue()
    pkt = _pkt()
    q.enqueue(pkt)
    q.enqueue(pkt)
    assert len(q) == 1


def test_multiple_queued_messages_independent():
    q = StoreForwardQueue()
    a, b = _pkt(), _pkt()
    q.enqueue(a)
    q.enqueue(b)
    assert len(q) == 2
    q.remove(a.msg_id)
    assert len(q) == 1
    assert q.all() == [b]
