import uuid

from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.reliability import DedupSet, MessagePriorityQueue


def _pkt(priority: int, timestamp: int, msg_id: uuid.UUID = None) -> Packet:
    return Packet(
        type=PacketType.DATA,
        priority=priority,
        src="A",
        dst="B",
        msg_id=msg_id or uuid.uuid4(),
        timestamp=timestamp,
    )


# --- DedupSet -----------------------------------------------------------------

def test_first_sighting_is_not_a_duplicate():
    dedup = DedupSet()
    msg_id = uuid.uuid4()
    assert dedup.seen_before(msg_id, now_ms=0) is False


def test_second_sighting_is_a_duplicate():
    dedup = DedupSet()
    msg_id = uuid.uuid4()
    dedup.seen_before(msg_id, now_ms=0)
    assert dedup.seen_before(msg_id, now_ms=100) is True


def test_different_messages_are_independent():
    dedup = DedupSet()
    a, b = uuid.uuid4(), uuid.uuid4()
    dedup.seen_before(a, now_ms=0)
    assert dedup.seen_before(b, now_ms=0) is False


def test_entry_expires_after_window():
    dedup = DedupSet(window_s=300)
    msg_id = uuid.uuid4()
    dedup.seen_before(msg_id, now_ms=0)
    # 301s later: window elapsed, treated as new again
    assert dedup.seen_before(msg_id, now_ms=301_000) is False


def test_entry_still_duplicate_just_inside_window():
    dedup = DedupSet(window_s=300)
    msg_id = uuid.uuid4()
    dedup.seen_before(msg_id, now_ms=0)
    assert dedup.seen_before(msg_id, now_ms=299_000) is True


def test_len_reflects_current_entries_after_prune():
    dedup = DedupSet(window_s=10)
    dedup.seen_before(uuid.uuid4(), now_ms=0)
    dedup.seen_before(uuid.uuid4(), now_ms=0)
    assert len(dedup) == 2
    # third call, long after window, prunes both stale entries first
    dedup.seen_before(uuid.uuid4(), now_ms=50_000)
    assert len(dedup) == 1


def test_contains():
    dedup = DedupSet()
    msg_id = uuid.uuid4()
    assert msg_id not in dedup
    dedup.seen_before(msg_id, now_ms=0)
    assert msg_id in dedup


# --- MessagePriorityQueue ------------------------------------------------------

def test_sos_pops_before_normal_regardless_of_insertion_order():
    q = MessagePriorityQueue()
    normal = _pkt(Priority.NORMAL, timestamp=100)
    sos = _pkt(Priority.SOS, timestamp=200)
    q.push(normal)
    q.push(sos)

    assert q.pop() is sos
    assert q.pop() is normal


def test_all_three_priorities_ordered_correctly():
    q = MessagePriorityQueue()
    status = _pkt(Priority.STATUS, timestamp=1)
    normal = _pkt(Priority.NORMAL, timestamp=1)
    sos = _pkt(Priority.SOS, timestamp=1)
    for pkt in (status, normal, sos):
        q.push(pkt)

    assert [q.pop(), q.pop(), q.pop()] == [sos, normal, status]


def test_ties_broken_by_oldest_timestamp_first():
    q = MessagePriorityQueue()
    older = _pkt(Priority.NORMAL, timestamp=100)
    newer = _pkt(Priority.NORMAL, timestamp=200)
    q.push(newer)
    q.push(older)

    assert q.pop() is older
    assert q.pop() is newer


def test_same_priority_and_timestamp_does_not_crash_on_packet_comparison():
    # regression guard: without the counter tiebreaker, heapq would try
    # to compare two Packet objects directly and blow up (dataclass isn't
    # orderable), since priority and timestamp are equal here.
    q = MessagePriorityQueue()
    q.push(_pkt(Priority.SOS, timestamp=5))
    q.push(_pkt(Priority.SOS, timestamp=5))
    assert len(q) == 2
    q.pop()
    q.pop()


def test_peek_does_not_remove():
    q = MessagePriorityQueue()
    pkt = _pkt(Priority.SOS, timestamp=1)
    q.push(pkt)
    assert q.peek() is pkt
    assert len(q) == 1


def test_peek_empty_queue_returns_none():
    q = MessagePriorityQueue()
    assert q.peek() is None


def test_len_and_bool():
    q = MessagePriorityQueue()
    assert len(q) == 0
    assert bool(q) is False
    q.push(_pkt(Priority.NORMAL, timestamp=1))
    assert len(q) == 1
    assert bool(q) is True


def test_push_with_item_returns_item_not_packet():
    """relay.py queues (next_hop, pkt) pairs so the sender loop knows
    where each packet is headed without a second lookup."""
    q = MessagePriorityQueue()
    pkt = _pkt(Priority.SOS, timestamp=1)
    q.push(pkt, item=("C", pkt))

    assert q.pop() == ("C", pkt)


def test_push_without_item_defaults_to_packet_itself():
    q = MessagePriorityQueue()
    pkt = _pkt(Priority.NORMAL, timestamp=1)
    q.push(pkt)

    assert q.pop() is pkt


def test_ordering_uses_packet_priority_even_with_custom_item():
    q = MessagePriorityQueue()
    normal_pkt = _pkt(Priority.NORMAL, timestamp=1)
    sos_pkt = _pkt(Priority.SOS, timestamp=2)
    q.push(normal_pkt, item=("X", normal_pkt))
    q.push(sos_pkt, item=("Y", sos_pkt))

    assert q.pop() == ("Y", sos_pkt)
    assert q.pop() == ("X", normal_pkt)


def test_sos_reapplied_mid_route_overtakes_already_queued_normal():
    """Section 9.1: the queue is re-applied at every hop, not only at the
    source -- so an SOS pushed after a NORMAL is already queued still
    overtakes it, simulating a relay hop where SOS traffic arrives later
    but must still jump the line."""
    q = MessagePriorityQueue()
    q.push(_pkt(Priority.NORMAL, timestamp=1))
    q.push(_pkt(Priority.NORMAL, timestamp=2))
    q.push(_pkt(Priority.SOS, timestamp=3))

    assert q.pop().priority == Priority.SOS
