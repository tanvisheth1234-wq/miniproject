import uuid

import pytest

from mesh.core.packet import (
    DEFAULT_TTL,
    FLAG_ENCRYPTED,
    FLAG_NEEDS_ACK,
    FLAG_SIGNED,
    FLAG_STORE_FORWARD_OK,
    HEADER_SIZE,
    MAGIC,
    NODE_ID_SIZE,
    SIGNATURE_SIZE,
    VERSION,
    Packet,
    PacketError,
    PacketType,
    Priority,
)


def make_packet(**overrides):
    defaults = dict(
        type=PacketType.DATA,
        priority=Priority.NORMAL,
        src="A",
        dst="B",
        payload=b"hello mesh",
    )
    defaults.update(overrides)
    return Packet(**defaults)


# --- header size / round trip ------------------------------------------------

def test_header_is_52_bytes():
    pkt = make_packet(path=[])
    assert len(pkt.pack()) == HEADER_SIZE + len(pkt.payload)


def test_round_trip_no_path_no_payload():
    pkt = make_packet(payload=b"", path=[])
    data = pkt.pack()
    assert len(data) == HEADER_SIZE
    out = Packet.unpack(data)
    assert out.src == "A"
    assert out.dst == "B"
    assert out.type == PacketType.DATA
    assert out.priority == Priority.NORMAL
    assert out.payload == b""
    assert out.path == []
    assert out.msg_id == pkt.msg_id
    assert out.timestamp == pkt.timestamp
    assert out.version == VERSION
    assert out.ttl == DEFAULT_TTL


def test_round_trip_with_path_and_payload():
    pkt = make_packet(
        path=["A", "R1", "R2"],
        payload=b"trapped on floor 3",
        ttl=7,
        hop_count=3,
    )
    data = pkt.pack()
    expected_len = HEADER_SIZE + 3 * NODE_ID_SIZE + len(pkt.payload)
    assert len(data) == expected_len

    out = Packet.unpack(data)
    assert out.path == ["A", "R1", "R2"]
    assert out.payload == b"trapped on floor 3"
    assert out.ttl == 7
    assert out.hop_count == 3


def test_round_trip_all_message_types_and_priorities():
    for msg_type in (PacketType.HELLO, PacketType.LINK_STATE, PacketType.DATA, PacketType.ACK):
        for priority in (Priority.SOS, Priority.NORMAL, Priority.STATUS):
            pkt = make_packet(type=msg_type, priority=priority)
            out = Packet.unpack(pkt.pack())
            assert out.type == msg_type
            assert out.priority == priority


def test_round_trip_with_signature():
    signature = bytes(range(SIGNATURE_SIZE))
    pkt = make_packet(signature=signature)
    data = pkt.pack()
    assert len(data) == HEADER_SIZE + len(pkt.payload) + SIGNATURE_SIZE

    out = Packet.unpack(data)
    assert out.signature == signature
    assert out.flags & FLAG_SIGNED
    assert out.signed


# --- field-level correctness --------------------------------------------------

def test_magic_bytes_are_M_E():
    pkt = make_packet()
    data = pkt.pack()
    assert data[0:2] == b"ME"
    assert data[0:2] == MAGIC.to_bytes(2, "big")


def test_version_field():
    pkt = make_packet()
    data = pkt.pack()
    assert data[2] == VERSION


def test_msg_id_defaults_to_uuid4_and_round_trips():
    pkt = make_packet()
    assert isinstance(pkt.msg_id, uuid.UUID)
    out = Packet.unpack(pkt.pack())
    assert out.msg_id == pkt.msg_id


def test_msg_id_is_16_bytes_on_wire():
    pkt = make_packet()
    data = pkt.pack()
    assert data[8:24] == pkt.msg_id.bytes


def test_src_dst_null_padded_to_8_bytes():
    pkt = make_packet(src="A", dst="B")
    data = pkt.pack()
    assert data[24:32] == b"A\x00\x00\x00\x00\x00\x00\x00"
    assert data[32:40] == b"B\x00\x00\x00\x00\x00\x00\x00"


def test_src_dst_full_8_char_ids():
    pkt = make_packet(src="NODE0001", dst="RESCUE__")
    out = Packet.unpack(pkt.pack())
    assert out.src == "NODE0001"
    assert out.dst == "RESCUE__"


def test_node_id_longer_than_8_bytes_rejected():
    with pytest.raises(PacketError):
        make_packet(src="TOOLONGNODEID").pack()


def test_timestamp_is_uint64_milliseconds():
    pkt = make_packet(timestamp=1_734_000_000_000)
    out = Packet.unpack(pkt.pack())
    assert out.timestamp == 1_734_000_000_000


def test_payload_len_field_matches_payload():
    pkt = make_packet(payload=b"x" * 100)
    data = pkt.pack()
    payload_len = int.from_bytes(data[48:50], "big")
    assert payload_len == 100


def test_path_len_field_matches_path():
    pkt = make_packet(path=["A", "B", "C", "D"])
    data = pkt.pack()
    assert data[50] == 4


def test_reserved_byte_is_zero():
    pkt = make_packet()
    data = pkt.pack()
    assert data[51] == 0


# --- flags -------------------------------------------------------------------

def test_flag_bits_independent():
    pkt = make_packet(flags=FLAG_ENCRYPTED | FLAG_NEEDS_ACK | FLAG_STORE_FORWARD_OK)
    out = Packet.unpack(pkt.pack())
    assert out.encrypted
    assert out.needs_ack
    assert out.store_forward_ok
    assert not out.signed


def test_signature_present_implies_signed_flag_even_if_not_set_explicitly():
    pkt = make_packet(signature=bytes(SIGNATURE_SIZE))
    assert pkt.flags & FLAG_SIGNED == 0  # not set by caller
    data = pkt.pack()
    assert data[6] & FLAG_SIGNED  # pack() sets it on the wire
    out = Packet.unpack(data)
    assert out.signed


def test_signed_flag_without_signature_rejected():
    with pytest.raises(PacketError):
        make_packet(flags=FLAG_SIGNED, signature=None).pack()


def test_wrong_signature_length_rejected():
    with pytest.raises(PacketError):
        make_packet(signature=b"short").pack()


# --- validation / error handling ----------------------------------------------

def test_bad_magic_rejected():
    pkt = make_packet()
    data = bytearray(pkt.pack())
    data[0:2] = b"XX"
    with pytest.raises(PacketError):
        Packet.unpack(bytes(data))


def test_truncated_header_rejected():
    with pytest.raises(PacketError):
        Packet.unpack(b"\x00" * (HEADER_SIZE - 1))


def test_truncated_path_rejected():
    pkt = make_packet(path=["A", "B"])
    data = pkt.pack()
    # chop off half of the second path entry
    truncated = data[: HEADER_SIZE + NODE_ID_SIZE + 3]
    with pytest.raises(PacketError):
        Packet.unpack(truncated)


def test_truncated_payload_rejected():
    pkt = make_packet(payload=b"0123456789")
    data = pkt.pack()
    truncated = data[:-3]
    with pytest.raises(PacketError):
        Packet.unpack(truncated)


def test_truncated_signature_rejected():
    pkt = make_packet(signature=bytes(SIGNATURE_SIZE))
    data = pkt.pack()
    truncated = data[:-10]
    with pytest.raises(PacketError):
        Packet.unpack(truncated)


def test_payload_too_large_rejected():
    with pytest.raises(PacketError):
        make_packet(payload=b"x" * 70_000).pack()


def test_path_too_long_rejected():
    with pytest.raises(PacketError):
        make_packet(path=["N"] * 256).pack()


def test_ttl_out_of_range_rejected():
    with pytest.raises(PacketError):
        make_packet(ttl=256).pack()


# --- remaining_length (used by the TCP transport to frame a read) ------------

def test_remaining_length_matches_actual_body_size():
    pkt = make_packet(path=["A", "B"], payload=b"payload bytes here")
    data = pkt.pack()
    header, rest = data[:HEADER_SIZE], data[HEADER_SIZE:]
    assert Packet.remaining_length(header) == len(rest)


def test_remaining_length_includes_signature():
    pkt = make_packet(path=["A"], payload=b"p", signature=bytes(SIGNATURE_SIZE))
    data = pkt.pack()
    header, rest = data[:HEADER_SIZE], data[HEADER_SIZE:]
    assert Packet.remaining_length(header) == len(rest)


def test_remaining_length_rejects_wrong_size_input():
    with pytest.raises(PacketError):
        Packet.remaining_length(b"\x00" * 10)


def test_remaining_length_rejects_bad_magic():
    pkt = make_packet()
    header = bytearray(pkt.pack()[:HEADER_SIZE])
    header[0:2] = b"XX"
    with pytest.raises(PacketError):
        Packet.remaining_length(bytes(header))


# --- TTL / hop_count semantics (values only; decrement logic is reliability.py) --

def test_default_ttl_is_10():
    pkt = make_packet()
    assert pkt.ttl == DEFAULT_TTL


def test_hop_count_defaults_to_zero():
    pkt = make_packet()
    assert pkt.hop_count == 0
