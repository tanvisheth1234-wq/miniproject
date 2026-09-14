import asyncio

import pytest

from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport


def make_node(node_id, network, **kwargs):
    kwargs.setdefault("hello_interval", 0.02)
    kwargs.setdefault("neighbour_timeout", 0.3)
    transport = SimulatedTransport(node_id, network)
    return Node(node_id, transport, **kwargs)


@pytest.mark.asyncio
async def test_discovery_and_relay_both_work_on_the_same_node():
    """Regression test for the single-callback-slot bug: before the fix,
    only one of discovery/relay ever received packets, depending on
    start() ordering."""
    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B")
    a = make_node("A", net)
    b = make_node("B", net, role=NodeRole.GATEWAY)

    delivered_at_b = []
    b.on_deliver = delivered_at_b.append

    await a.start()
    await b.start()
    await asyncio.sleep(0.06)  # let discovery converge

    # discovery worked
    assert "B" in a.neighbours
    assert a.neighbours.get("B").role == NodeRole.GATEWAY
    assert "A" in b.neighbours

    # relay also worked, on the very same transport/callback
    pkt = Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="A", dst="B", payload=b"hi B")
    await a.transport.send("B", pkt.pack())
    await asyncio.sleep(0.02)

    await a.stop()
    await b.stop()

    assert len(delivered_at_b) == 1
    assert delivered_at_b[0].payload == b"hi B"


@pytest.mark.asyncio
async def test_message_to_discovered_neighbour_delivers_without_manual_next_hop():
    net = SimulatedNetwork(seed=2)
    net.set_link("A", "B")
    a = make_node("A", net)
    b = make_node("B", net)

    delivered = []
    b.on_deliver = delivered.append

    await a.start()
    await b.start()
    await asyncio.sleep(0.06)

    # no one ever called a.relay.set_next_hop("B", "B") -- discovery did it
    assert a.relay._next_hop == {"B": "B"}

    pkt = Packet(type=PacketType.DATA, priority=Priority.SOS, src="A", dst="B", payload=b"sos")
    await a.transport.send("B", pkt.pack())
    await asyncio.sleep(0.02)

    await a.stop()
    await b.stop()

    assert len(delivered) == 1


@pytest.mark.asyncio
async def test_middle_node_auto_relays_across_a_chain():
    """A -> B -> C: A still has to manually hand its packet to first-hop
    B (A never discovered C, so it has no way to know C exists), but B's
    forward to C is entirely discovery-driven -- nobody called
    set_next_hop("C", "C") on B by hand."""
    net = SimulatedNetwork(seed=3)
    net.set_link("A", "B")
    net.set_link("B", "C")
    a = make_node("A", net)
    b = make_node("B", net)
    c = make_node("C", net)

    delivered_at_c = []
    c.on_deliver = delivered_at_c.append

    await a.start()
    await b.start()
    await c.start()
    await asyncio.sleep(0.06)  # let B discover both A and C

    assert b.relay._next_hop == {"A": "A", "C": "C"}

    pkt = Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="A", dst="C", path=["A"], payload=b"relay me")
    await a.transport.send("B", pkt.pack())  # A manually addresses the first hop
    await asyncio.sleep(0.02)

    await a.stop()
    await b.stop()
    await c.stop()

    assert len(delivered_at_c) == 1
    assert delivered_at_c[0].path == ["A", "B"]
    assert delivered_at_c[0].hop_count == 1


@pytest.mark.asyncio
async def test_route_forgotten_when_neighbour_dies():
    net = SimulatedNetwork(seed=4)
    net.set_link("A", "B")
    a = make_node("A", net, neighbour_timeout=0.08, hello_interval=0.02, prune_interval=0.02)
    b = make_node("B", net, hello_interval=0.02)

    await a.start()
    await b.start()
    await asyncio.sleep(0.05)
    assert "B" in a.relay._next_hop

    await b.stop()  # B goes silent
    await asyncio.sleep(0.15)  # past A's neighbour_timeout

    assert "B" not in a.neighbours
    assert "B" not in a.relay._next_hop

    drops = []
    a.on_drop = lambda pkt, reason: drops.append(reason)
    stray = Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="X", dst="B", payload=b"too late")
    net_callback = a.transport._callback  # feed a packet as if it arrived from some third node
    net_callback("X", stray.pack())
    await asyncio.sleep(0)

    await a.stop()

    assert drops == ["no_route"]


@pytest.mark.asyncio
async def test_neighbours_property_matches_discovery_table():
    net = SimulatedNetwork(seed=5)
    net.set_link("A", "B")
    a = make_node("A", net)
    b = make_node("B", net)

    await a.start()
    await b.start()
    await asyncio.sleep(0.06)
    await a.stop()
    await b.stop()

    assert a.neighbours is a.discovery.neighbours
    assert "B" in a.neighbours
