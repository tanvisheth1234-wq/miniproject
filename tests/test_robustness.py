"""Boundary, invalid-input, replay and concurrency tests.

These back Chapter 9.6 / 9.7 of the project report: what the engine does
with malformed bytes, out-of-range fields, replayed packets and many
simultaneous sends. Everything runs on the in-memory simulated transport.
"""

import asyncio
import random

import pytest

from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import HEADER_SIZE, Packet, PacketError, PacketType, Priority
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport


def make_node(node_id, network, **kwargs):
    kwargs.setdefault("hello_interval", 0.02)
    kwargs.setdefault("neighbour_timeout", 0.3)
    kwargs.setdefault("link_state_interval", 0.03)
    kwargs.setdefault("ack_timeout", 0.5)
    return Node(node_id, SimulatedTransport(node_id, network), **kwargs)


def valid_packet(**overrides):
    fields = dict(type=PacketType.DATA, priority=Priority.NORMAL, src="A", dst="B", payload=b"hello", path=["A"])
    fields.update(overrides)
    return Packet(**fields)


# --- invalid and malformed input -------------------------------------------------

def test_random_bytes_never_crash_the_parser():
    """Any byte string either parses or raises PacketError -- never anything else."""
    rng = random.Random(2026)
    for _ in range(3000):
        blob = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 200)))
        try:
            Packet.unpack(blob)
        except PacketError:
            pass


def test_bit_flipped_valid_packets_never_crash_the_parser():
    rng = random.Random(7)
    good = valid_packet(payload=b"x" * 40).pack()
    for _ in range(1000):
        mutated = bytearray(good)
        for _ in range(rng.randrange(1, 4)):
            mutated[rng.randrange(len(mutated))] ^= 1 << rng.randrange(8)
        try:
            Packet.unpack(bytes(mutated))
        except PacketError:
            pass


def test_payload_over_the_length_field_is_rejected():
    with pytest.raises(PacketError):
        valid_packet(payload=b"x" * 70_000).pack()


def test_node_id_longer_than_eight_bytes_is_rejected():
    with pytest.raises(PacketError):
        valid_packet(src="NINE-CHARS").pack()


def test_header_only_input_and_empty_input_are_rejected():
    with pytest.raises(PacketError):
        Packet.unpack(b"")
    with pytest.raises(PacketError):
        Packet.unpack(valid_packet(payload=b"abc").pack()[:HEADER_SIZE])


@pytest.mark.asyncio
async def test_node_survives_garbage_arriving_on_the_wire():
    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B")
    a, b = make_node("A", net), make_node("B", net)
    delivered = []
    b.on_deliver = delivered.append
    await a.start()
    await b.start()
    await asyncio.sleep(0.08)

    rng = random.Random(3)
    for _ in range(200):
        b._on_receive("A", bytes(rng.randrange(256) for _ in range(rng.randrange(0, 150))))

    await a.send("B", b"still works", priority=Priority.NORMAL)
    await asyncio.sleep(0.1)
    await a.stop()
    await b.stop()
    assert [p.payload for p in delivered] == [b"still works"]


@pytest.mark.asyncio
async def test_empty_payload_is_a_valid_message():
    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B")
    a, b = make_node("A", net), make_node("B", net)
    delivered = []
    b.on_deliver = delivered.append
    await a.start()
    await b.start()
    await asyncio.sleep(0.08)
    await a.send("B", b"", priority=Priority.NORMAL)
    await asyncio.sleep(0.1)
    await a.stop()
    await b.stop()
    assert len(delivered) == 1 and delivered[0].payload == b""


@pytest.mark.asyncio
async def test_send_to_an_unknown_destination_is_held_not_raised():
    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B")
    a, b = make_node("A", net), make_node("B", net)
    await a.start()
    await b.start()
    await asyncio.sleep(0.08)
    pkt = await a.send("NOBODY", b"hello?", priority=Priority.SOS)
    await a.stop()
    await b.stop()
    assert pkt.msg_id in a.store_forward


# --- replay ---------------------------------------------------------------------

@pytest.mark.asyncio
async def test_replayed_packet_is_delivered_only_once():
    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B")
    a, b = make_node("A", net), make_node("B", net)
    delivered, dropped = [], []
    b.on_deliver = delivered.append
    b.on_drop = lambda pkt, reason: dropped.append(reason)
    await a.start()
    await b.start()
    await asyncio.sleep(0.08)

    wire = valid_packet(src="A", dst="B", payload=b"once only").pack()
    for _ in range(5):
        await a.transport.send("B", wire)
    await asyncio.sleep(0.1)
    await a.stop()
    await b.stop()

    assert len(delivered) == 1
    assert dropped.count("duplicate") == 4


# --- concurrency and stress ----------------------------------------------------------

@pytest.mark.asyncio
async def test_two_hundred_simultaneous_sends_across_two_hops_all_arrive_exactly_once():
    net = SimulatedNetwork(seed=5)
    net.set_link("A", "B")
    net.set_link("B", "C")
    a, b, c = make_node("A", net), make_node("B", net), make_node("C", net, role=NodeRole.GATEWAY)
    delivered = []
    c.on_deliver = delivered.append
    for n in (a, b, c):
        await n.start()
    await asyncio.sleep(0.2)

    sent = await asyncio.gather(*(a.send("C", f"m{i}".encode(), priority=Priority.NORMAL, needs_ack=True) for i in range(200)))
    await asyncio.sleep(1.5)
    for n in (a, b, c):
        await n.stop()

    got = [p.msg_id for p in delivered]
    assert len(got) == 200
    assert len(set(got)) == 200
    assert set(got) == {p.msg_id for p in sent}
    assert len(a.ack_tracker) == 0  # every ACK came back


@pytest.mark.asyncio
async def test_sos_burst_and_routine_burst_from_two_senders_do_not_corrupt_each_other():
    net = SimulatedNetwork(seed=9)
    net.set_link("A", "G")
    net.set_link("B", "G")
    a, b = make_node("A", net), make_node("B", net)
    g = make_node("G", net, role=NodeRole.GATEWAY)
    delivered = []
    g.on_deliver = delivered.append
    for n in (a, b, g):
        await n.start()
    await asyncio.sleep(0.2)

    await asyncio.gather(
        *(a.send("RESCUE__", f"sos{i}".encode(), priority=Priority.SOS) for i in range(50)),
        *(b.send("RESCUE__", f"norm{i}".encode(), priority=Priority.NORMAL) for i in range(50)),
    )
    await asyncio.sleep(1.0)
    for n in (a, b, g):
        await n.stop()

    bodies = sorted(p.payload.decode() for p in delivered)
    assert bodies == sorted([f"sos{i}" for i in range(50)] + [f"norm{i}" for i in range(50)])
