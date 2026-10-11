import uuid

from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.reliability import AckTracker, StoreForwardQueue


def _pkt(msg_id: uuid.UUID = None, priority: int = Priority.NORMAL) -> Packet:
    return Packet(type=PacketType.DATA, priority=priority, src="A", dst="C", msg_id=msg_id or uuid.uuid4())


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


# --- count bound (SNF-4/SNF-5) ----------------------------------------------------

def test_enqueue_under_the_bound_evicts_nothing():
    q = StoreForwardQueue(max_count=3)
    for _ in range(3):
        assert q.enqueue(_pkt()) is None
    assert len(q) == 3


def test_enqueue_over_the_bound_evicts_lowest_priority():
    q = StoreForwardQueue(max_count=2)
    sos = _pkt(priority=Priority.SOS, msg_id=uuid.uuid4())
    normal = _pkt(priority=Priority.NORMAL, msg_id=uuid.uuid4())
    status = _pkt(priority=Priority.STATUS, msg_id=uuid.uuid4())  # lowest urgency = evicted

    assert q.enqueue(sos, now_ms=0) is None
    assert q.enqueue(normal, now_ms=0) is None
    evicted = q.enqueue(status, now_ms=0)

    assert evicted is status
    assert status.msg_id not in q
    assert sos.msg_id in q
    assert normal.msg_id in q
    assert len(q) == 2


def test_eviction_never_displaces_sos_for_routine_traffic():
    """SNF-5: an emergency message is never displaced by routine traffic --
    even if the SOS was the oldest entry, it must survive while a NORMAL
    message gets evicted instead."""
    q = StoreForwardQueue(max_count=1)
    sos = _pkt(priority=Priority.SOS, msg_id=uuid.uuid4())
    q.enqueue(sos, now_ms=0)

    normal = _pkt(priority=Priority.NORMAL, msg_id=uuid.uuid4())
    evicted = q.enqueue(normal, now_ms=1000)

    assert evicted is normal  # the newly-added NORMAL is evicted, not the existing SOS
    assert sos.msg_id in q
    assert normal.msg_id not in q


def test_eviction_ties_broken_by_oldest_first():
    q = StoreForwardQueue(max_count=2)
    older = _pkt(priority=Priority.NORMAL, msg_id=uuid.uuid4())
    newer = _pkt(priority=Priority.NORMAL, msg_id=uuid.uuid4())
    q.enqueue(older, now_ms=0)
    q.enqueue(newer, now_ms=1000)

    extra = _pkt(priority=Priority.NORMAL, msg_id=uuid.uuid4())
    evicted = q.enqueue(extra, now_ms=2000)

    assert evicted is older  # same priority as the others -- oldest goes first


def test_default_max_count_matches_design_of_algorithms_c_max():
    from mesh.core.reliability import SF_MAX_COUNT
    assert SF_MAX_COUNT == 500


# --- age bound / expiry (the EXPIRE procedure) ------------------------------------

def test_expire_removes_messages_older_than_max_age():
    q = StoreForwardQueue(max_age_s=10)
    old = _pkt()
    fresh = _pkt()
    q.enqueue(old, now_ms=0)
    q.enqueue(fresh, now_ms=9_000)

    expired = q.expire(now_ms=11_000)  # old is 11s held (>10s), fresh is 2s held

    assert expired == [old]
    assert old.msg_id not in q
    assert fresh.msg_id in q


def test_expire_returns_empty_when_nothing_is_stale():
    q = StoreForwardQueue(max_age_s=10)
    q.enqueue(_pkt(), now_ms=0)
    assert q.expire(now_ms=5_000) == []
    assert len(q) == 1


def test_expire_applies_regardless_of_priority():
    """Unlike count-based eviction, age-based expiry doesn't protect SOS --
    a message that's simply too old is no longer useful regardless of
    urgency (Algorithm 8's EXPIRE has no priority check)."""
    q = StoreForwardQueue(max_age_s=10)
    sos = _pkt(priority=Priority.SOS)
    q.enqueue(sos, now_ms=0)
    assert q.expire(now_ms=11_000) == [sos]


def test_default_max_age_matches_design_of_algorithms_t_hold():
    from mesh.core.reliability import SF_MAX_AGE
    assert SF_MAX_AGE == 1800.0
