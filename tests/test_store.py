import pytest

from mesh.core.store import Store


@pytest.fixture
def store():
    with Store(":memory:") as s:
        yield s


# --- messages ---------------------------------------------------------------

def test_record_and_get_message(store):
    store.record_message(
        msg_id="m1", src="A", dst="B", priority=0, direction="sent",
        status="pending", created_ms=1000,
    )
    msg = store.get_message("m1")
    assert msg["src"] == "A"
    assert msg["dst"] == "B"
    assert msg["priority"] == 0
    assert msg["status"] == "pending"
    assert msg["created_ms"] == 1000


def test_get_unknown_message_returns_none(store):
    assert store.get_message("nope") is None


def test_record_message_stores_path_as_comma_separated(store):
    store.record_message(
        msg_id="m1", src="A", dst="Z", priority=1, direction="sent",
        status="delivered", path=["A", "B", "C", "Z"],
    )
    msg = store.get_message("m1")
    assert msg["path"] == "A,B,C,Z"


def test_record_message_upserts_on_same_id(store):
    store.record_message(msg_id="m1", src="A", dst="B", priority=1, direction="sent", status="pending")
    store.record_message(msg_id="m1", src="A", dst="B", priority=1, direction="sent", status="delivered", hop_count=3)

    msg = store.get_message("m1")
    assert msg["status"] == "delivered"
    assert msg["hop_count"] == 3


def test_update_message_status(store):
    store.record_message(msg_id="m1", src="A", dst="B", priority=1, direction="sent", status="pending")
    updated = store.update_message_status("m1", "delivered", resolved_ms=5000)

    assert updated is True
    msg = store.get_message("m1")
    assert msg["status"] == "delivered"
    assert msg["resolved_ms"] == 5000


def test_update_status_of_unknown_message_returns_false(store):
    assert store.update_message_status("ghost", "delivered") is False


def test_messages_by_status(store):
    store.record_message(msg_id="m1", src="A", dst="B", priority=0, direction="sent", status="queued_sf")
    store.record_message(msg_id="m2", src="A", dst="C", priority=1, direction="sent", status="delivered")
    store.record_message(msg_id="m3", src="A", dst="D", priority=1, direction="sent", status="queued_sf")

    queued = store.messages_by_status("queued_sf")
    assert {m["msg_id"] for m in queued} == {"m1", "m3"}


# --- events -------------------------------------------------------------------

def test_record_event_and_query_by_message(store):
    store.record_event(kind="sent", msg_id="m1", ts_ms=100)
    store.record_event(kind="ack", msg_id="m1", ts_ms=200)
    store.record_event(kind="sent", msg_id="m2", ts_ms=50)

    events = store.events_for_message("m1")
    assert [e["kind"] for e in events] == ["sent", "ack"]


def test_events_for_message_ordered_by_time(store):
    store.record_event(kind="recv", msg_id="m1", ts_ms=300)
    store.record_event(kind="sent", msg_id="m1", ts_ms=100)
    store.record_event(kind="forward", msg_id="m1", ts_ms=200)

    events = store.events_for_message("m1")
    assert [e["ts_ms"] for e in events] == [100, 200, 300]


def test_events_by_kind(store):
    store.record_event(kind="drop_ttl", msg_id="m1")
    store.record_event(kind="drop_ttl", msg_id="m2")
    store.record_event(kind="sent", msg_id="m3")

    dropped = store.events_by_kind("drop_ttl")
    assert len(dropped) == 2


def test_count_events(store):
    store.record_event(kind="peer_up", peer="B")
    store.record_event(kind="peer_up", peer="C")
    store.record_event(kind="peer_down", peer="B")

    assert store.count_events("peer_up") == 2
    assert store.count_events("peer_down") == 1
    assert store.count_events("route_change") == 0


def test_record_event_returns_row_id(store):
    first = store.record_event(kind="sent", msg_id="m1")
    second = store.record_event(kind="sent", msg_id="m2")
    assert second > first


# --- peers ----------------------------------------------------------------------

def test_upsert_and_get_peer(store):
    store.upsert_peer("B", role="GATEWAY", last_seen_ms=1000, link_quality=0.9)
    peer = store.get_peer("B")
    assert peer["role"] == "GATEWAY"
    assert peer["last_seen_ms"] == 1000
    assert peer["link_quality"] == pytest.approx(0.9)


def test_upsert_peer_updates_role_and_last_seen(store):
    store.upsert_peer("B", role="NORMAL", last_seen_ms=1000)
    store.upsert_peer("B", role="GATEWAY", last_seen_ms=2000)

    peer = store.get_peer("B")
    assert peer["role"] == "GATEWAY"
    assert peer["last_seen_ms"] == 2000


def test_upsert_peer_preserves_link_quality_when_not_given(store):
    store.upsert_peer("B", role="NORMAL", last_seen_ms=1000, link_quality=0.8)
    store.upsert_peer("B", role="NORMAL", last_seen_ms=2000)  # no link_quality this time

    peer = store.get_peer("B")
    assert peer["link_quality"] == pytest.approx(0.8)


def test_get_unknown_peer_returns_none(store):
    assert store.get_peer("ghost") is None


def test_remove_peer(store):
    store.upsert_peer("B", role="NORMAL", last_seen_ms=1000)
    store.remove_peer("B")
    assert store.get_peer("B") is None


def test_all_peers(store):
    store.upsert_peer("B", role="NORMAL", last_seen_ms=1000)
    store.upsert_peer("C", role="RESCUE", last_seen_ms=2000)
    peers = store.all_peers()
    assert {p["node_id"] for p in peers} == {"B", "C"}


def test_public_key_round_trips_as_blob(store):
    key_bytes = bytes(range(32))
    store.upsert_peer("B", role="NORMAL", last_seen_ms=1000, public_key=key_bytes)
    peer = store.get_peer("B")
    assert peer["public_key"] == key_bytes


# --- lifecycle ------------------------------------------------------------------

def test_context_manager_closes_connection():
    with Store(":memory:") as s:
        s.record_message(msg_id="m1", src="A", dst="B", priority=1, direction="sent", status="pending")
    with pytest.raises(Exception):
        s.get_message("m1")  # connection is closed
