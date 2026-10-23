"""The real-socket transport (story/lan_transport.py) on the loopback
interface: previous-hop identity, range emulation, the power switch, hostile
input, and a full Node mesh running over actual TCP.
"""

import asyncio
import socket
import time

import pytest

from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.transport import TransportError
from story.lan_transport import LanTransport


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def make_pair():
    pa, pb = free_port(), free_port()
    peers_a = {"B": ("127.0.0.1", pb)}
    peers_b = {"A": ("127.0.0.1", pa)}
    return LanTransport("A", pa, peers_a, {"B"}, "127.0.0.1"), LanTransport("B", pb, peers_b, {"A"}, "127.0.0.1")


def packet(src="X", dst="B", payload=b"hello"):
    return Packet(type=PacketType.DATA, priority=Priority.NORMAL, src=src, dst=dst, payload=payload).pack()


@pytest.mark.asyncio
async def test_receiver_sees_the_previous_hop_not_the_packet_source():
    a, b = make_pair()
    got = []
    b.on_receive(lambda sender, data: got.append((sender, data)))
    await a.start()
    await b.start()
    wire = packet(src="X")  # originated elsewhere, relayed by A
    await a.send("B", wire)
    await asyncio.sleep(0.1)
    await a.stop()
    await b.stop()
    assert got == [("A", wire)]


@pytest.mark.asyncio
async def test_sending_to_a_non_neighbour_is_refused():
    a, b = make_pair()
    await a.start()
    with pytest.raises(TransportError):
        await a.send("Z", packet())
    await a.stop()


@pytest.mark.asyncio
async def test_switched_off_device_neither_sends_nor_hears():
    a, b = make_pair()
    got = []
    b.on_receive(lambda sender, data: got.append(data))
    await a.start()
    await b.start()

    b.enabled = False
    await a.send("B", packet())
    await asyncio.sleep(0.1)
    assert got == []

    a.enabled = False
    with pytest.raises(TransportError):
        await a.send("B", packet())
    await a.broadcast(packet())  # silent no-op, never raises

    b.enabled = True
    a.enabled = True
    await a.send("B", packet())
    await asyncio.sleep(0.1)
    await a.stop()
    await b.stop()
    assert len(got) == 1


@pytest.mark.asyncio
async def test_unknown_previous_hop_and_garbage_are_ignored_and_listener_survives():
    a, b = make_pair()
    got = []
    b.on_receive(lambda sender, data: got.append(sender))
    await a.start()
    await b.start()
    host, port = b.peers["A"][0], b.listen_port

    # a stranger that is not one of B's configured neighbours
    _, w = await asyncio.open_connection(host, port)
    w.write(bytes([1]) + b"Z" + packet())
    await w.drain(); w.close()
    # pure garbage, and a half-sent preamble
    for junk in (b"\x00", b"\xff" * 300, b"\x05AB"):
        _, w = await asyncio.open_connection(host, port)
        w.write(junk); await w.drain(); w.close()
    await asyncio.sleep(0.1)
    assert got == []

    await a.send("B", packet())  # the listener is still alive
    await asyncio.sleep(0.1)
    await a.stop()
    await b.stop()
    assert got == ["A"]


@pytest.mark.asyncio
async def test_sending_to_a_dead_peer_fails_fast_with_transport_error():
    a, _b = make_pair()  # B never started: nothing listens on its port
    await a.start()
    started = time.monotonic()
    with pytest.raises(TransportError):
        await a.send("B", packet())
    assert time.monotonic() - started < 2.5
    await a.stop()


@pytest.mark.asyncio
async def test_full_node_mesh_over_real_tcp_discovers_routes_and_delivers_with_ack():
    """A - B - C in a line, three real Node objects, real sockets, no simulator."""
    ports = {n: free_port() for n in "ABC"}
    links = {"A": {"B"}, "B": {"A", "C"}, "C": {"B"}}
    nodes = {}
    for n in "ABC":
        peers = {m: ("127.0.0.1", ports[m]) for m in "ABC" if m != n}
        transport = LanTransport(n, ports[n], peers, links[n], "127.0.0.1")
        nodes[n] = Node(n, transport, role=NodeRole.GATEWAY if n == "C" else NodeRole.NORMAL,
                        hello_interval=0.1, neighbour_timeout=0.8, prune_interval=0.1,
                        link_state_interval=0.2, ack_timeout=1.0, ack_poll_interval=0.1)
    delivered = []
    nodes["C"].on_deliver = delivered.append
    for node in nodes.values():
        await node.start()

    deadline = time.monotonic() + 6
    while time.monotonic() < deadline and nodes["A"].router.shortest_path("C") != ["A", "B", "C"]:
        await asyncio.sleep(0.1)
    assert nodes["A"].router.shortest_path("C") == ["A", "B", "C"]

    pkt = await nodes["A"].send("C", b"over real sockets", priority=Priority.SOS, needs_ack=True)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and nodes["A"].store.get_message(str(pkt.msg_id))["status"] != "delivered":
        await asyncio.sleep(0.1)
    status = nodes["A"].store.get_message(str(pkt.msg_id))["status"]
    for node in nodes.values():
        await node.stop()

    assert [p.payload for p in delivered] == [b"over real sockets"]
    assert status == "delivered"  # the ACK travelled back over TCP too
