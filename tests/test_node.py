import asyncio

import pytest

from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport


def make_node(node_id, network, **kwargs):
    kwargs.setdefault("hello_interval", 0.02)
    kwargs.setdefault("neighbour_timeout", 0.3)
    kwargs.setdefault("link_state_interval", 0.03)
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


@pytest.mark.asyncio
async def test_router_forwards_beyond_direct_neighbours_via_gossip():
    """A -> B -> C -> D: D is not B's direct neighbour, so B's static
    next-hop table has no entry for it. B can only forward this correctly
    once link-state gossip has told it C leads to D -- proving
    ``route_resolver`` (Router.next_hop) is actually doing the work, not
    just the direct-neighbour shortcut the other tests exercise."""
    net = SimulatedNetwork(seed=6)
    net.set_link("A", "B")
    net.set_link("B", "C")
    net.set_link("C", "D")
    a = make_node("A", net)
    b = make_node("B", net)
    c = make_node("C", net)
    d = make_node("D", net)

    delivered_at_d = []
    d.on_deliver = delivered_at_d.append

    await a.start()
    await b.start()
    await c.start()
    await d.start()
    await asyncio.sleep(0.2)  # discovery + at least one gossip round to converge

    # B never discovered D directly, so it has no static entry for it
    assert "D" not in b.relay._next_hop
    # but the graph gossip built it into knows a path exists
    assert b.router.next_hop("D") == "C"

    pkt = Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="A", dst="D", path=["A"], payload=b"go the distance")
    await a.transport.send("B", pkt.pack())
    await asyncio.sleep(0.05)

    await a.stop()
    await b.stop()
    await c.stop()
    await d.stop()

    assert len(delivered_at_d) == 1
    assert delivered_at_d[0].path == ["A", "B", "C"]
    assert delivered_at_d[0].hop_count == 2


@pytest.mark.asyncio
async def test_rescue_dst_routes_to_gateway_across_multiple_hops():
    net = SimulatedNetwork(seed=7)
    net.set_link("A", "B")
    net.set_link("B", "GW")
    a = make_node("A", net)
    b = make_node("B", net)
    gw = make_node("GW", net, role=NodeRole.GATEWAY)

    delivered_at_gw = []
    gw.on_deliver = delivered_at_gw.append

    await a.start()
    await b.start()
    await gw.start()
    await asyncio.sleep(0.2)

    assert a.router.next_hop("RESCUE__") == "B"

    from mesh.core.packet import RESCUE_DST
    pkt = Packet(type=PacketType.DATA, priority=Priority.SOS, src="A", dst=RESCUE_DST, payload=b"help")
    await a.transport.send("B", pkt.pack())
    await asyncio.sleep(0.05)

    await a.stop()
    await b.stop()
    await gw.stop()

    assert len(delivered_at_gw) == 1


# --- Node.send(): originating messages, ACK, store-and-forward ------------------

@pytest.mark.asyncio
async def test_send_without_route_queues_to_store_forward():
    net = SimulatedNetwork(seed=8)
    a = make_node("A", net)  # no links at all -- nobody to route through
    await a.start()

    pkt = await a.send("Z", b"help")

    assert pkt.msg_id in a.store_forward
    await a.stop()


@pytest.mark.asyncio
async def test_send_with_ack_delivers_and_gets_acknowledged():
    net = SimulatedNetwork(seed=9)
    net.set_link("A", "B")
    a = make_node("A", net)
    b = make_node("B", net)

    delivered_at_b = []
    b.on_deliver = delivered_at_b.append

    await a.start()
    await b.start()
    await asyncio.sleep(0.1)  # let discovery converge

    pkt = await a.send("B", b"hello", needs_ack=True)
    assert pkt.msg_id in a.ack_tracker  # registered on send

    await asyncio.sleep(0.05)  # B delivers, auto-ACKs, A processes the ACK

    assert len(delivered_at_b) == 1
    assert delivered_at_b[0].payload == b"hello"
    assert pkt.msg_id not in a.ack_tracker  # acknowledged, no longer pending

    await a.stop()
    await b.stop()


# --- store.py event/message logging -----------------------------------------------

@pytest.mark.asyncio
async def test_store_logs_sent_message_and_delivery_lifecycle():
    net = SimulatedNetwork(seed=20)
    net.set_link("A", "B")
    a = make_node("A", net)
    b = make_node("B", net)

    await a.start()
    await b.start()
    await asyncio.sleep(0.1)

    pkt = a_pkt = await a.send("B", b"hello store", needs_ack=True)
    await asyncio.sleep(0.05)

    # sender side: message recorded, moved to delivered once the ACK lands
    sent_row = a.store.get_message(str(pkt.msg_id))
    assert sent_row["direction"] == "sent"
    assert sent_row["status"] == "delivered"
    assert a.store.count_events("sent") == 1
    assert a.store.count_events("ack") == 1

    # receiver side: a separate row in B's own log, direction "received"
    recv_row = b.store.get_message(str(pkt.msg_id))
    assert recv_row["direction"] == "received"
    assert recv_row["status"] == "delivered"
    assert b.store.count_events("recv") == 1

    await a.stop()
    await b.stop()


@pytest.mark.asyncio
async def test_store_logs_forward_on_middle_node():
    net = SimulatedNetwork(seed=21)
    net.set_link("A", "B")
    net.set_link("B", "C")
    a = make_node("A", net)
    b = make_node("B", net)
    c = make_node("C", net)

    await a.start()
    await b.start()
    await c.start()
    await asyncio.sleep(0.15)

    pkt = await a.send("C", b"relay me")
    await asyncio.sleep(0.05)

    forwarded_row = b.store.get_message(str(pkt.msg_id))
    assert forwarded_row["direction"] == "forwarded"
    assert b.store.count_events("forward") == 1

    await a.stop()
    await b.stop()
    await c.stop()


@pytest.mark.asyncio
async def test_store_logs_peer_up_and_down():
    net = SimulatedNetwork(seed=22)
    net.set_link("A", "B")
    a = make_node("A", net, neighbour_timeout=0.08, prune_interval=0.02)
    b = make_node("B", net)

    await a.start()
    await b.start()
    await asyncio.sleep(0.06)
    assert a.store.get_peer("B")["role"] == NodeRole.NORMAL
    assert a.store.count_events("peer_up") == 1

    await b.stop()
    await asyncio.sleep(0.15)
    assert a.store.count_events("peer_down") == 1

    await a.stop()


@pytest.mark.asyncio
async def test_store_logs_drop_reason():
    net = SimulatedNetwork(seed=23)
    a = make_node("A", net)
    await a.start()

    # feed a stray DATA packet for an unknown destination straight into A's
    # own dispatcher, bypassing discovery -- guaranteed "no_route"
    stray = Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="X", dst="Z", payload=b"lost")
    a.transport._callback("X", stray.pack())
    await asyncio.sleep(0.02)

    assert a.store.count_events("drop_no_route") == 1

    await a.stop()


# --- crypto: payload encryption (section 10) -------------------------------------

@pytest.mark.asyncio
async def test_encrypted_payload_decrypts_correctly_at_destination():
    from mesh.core.crypto import generate_session_key

    key = generate_session_key()
    net = SimulatedNetwork(seed=30)
    net.set_link("A", "B")
    a = make_node("A", net, session_key=key)
    b = make_node("B", net, session_key=key)

    delivered = []
    b.on_deliver = delivered.append

    await a.start()
    await b.start()
    await asyncio.sleep(0.1)

    await a.send("B", b"four of us in room 302")
    await asyncio.sleep(0.05)

    assert len(delivered) == 1
    assert delivered[0].payload == b"four of us in room 302"  # plaintext to the app layer
    assert b.store.get_message(str(delivered[0].msg_id))["body"] == "four of us in room 302"

    await a.stop()
    await b.stop()


@pytest.mark.asyncio
async def test_relay_never_sees_plaintext_payload():
    """Section 10's threat model: a relay must not be able to read a
    message it forwards -- it only ever touches the ciphertext bytes."""
    from mesh.core.crypto import generate_session_key
    from mesh.core.packet import Packet as _Packet

    key = generate_session_key()
    net = SimulatedNetwork(seed=31)
    net.set_link("A", "B")
    net.set_link("B", "C")
    a = make_node("A", net, session_key=key)
    b = make_node("B", net)  # the relay -- deliberately has NO key
    c = make_node("C", net, session_key=key)

    forwarded_raw = []
    original_send = b.transport.send

    async def spy_send(node_id, data):
        # link-state gossip also flows through transport.send -- only
        # DATA packets are relevant to this test
        if _Packet.unpack(data).type == PacketType.DATA:
            forwarded_raw.append(data)
        await original_send(node_id, data)

    b.transport.send = spy_send

    await a.start()
    await b.start()
    await c.start()
    await asyncio.sleep(0.15)

    await a.send("C", b"trapped east stairwell")
    await asyncio.sleep(0.05)

    assert len(forwarded_raw) == 1
    forwarded_pkt = _Packet.unpack(forwarded_raw[0])
    assert b"trapped east stairwell" not in forwarded_pkt.payload
    # and B's own log never records a plaintext body for it either
    row = b.store.get_message(str(forwarded_pkt.msg_id))
    assert row["body"] is None

    await a.stop()
    await b.stop()
    await c.stop()


@pytest.mark.asyncio
async def test_wrong_session_key_is_rejected_not_delivered():
    from mesh.core.crypto import generate_session_key

    key_a = generate_session_key()
    key_b = generate_session_key()  # different key -- simulates a misconfigured node
    net = SimulatedNetwork(seed=32)
    net.set_link("A", "B")
    a = make_node("A", net, session_key=key_a)
    b = make_node("B", net, session_key=key_b)

    delivered = []
    b.on_deliver = delivered.append

    await a.start()
    await b.start()
    await asyncio.sleep(0.1)

    await a.send("B", b"secret")
    await asyncio.sleep(0.05)

    assert delivered == []
    assert b.store.count_events("drop_decrypt_failed") == 1

    await a.stop()
    await b.stop()


@pytest.mark.asyncio
async def test_no_key_configured_drops_encrypted_message():
    from mesh.core.crypto import generate_session_key

    key = generate_session_key()
    net = SimulatedNetwork(seed=33)
    net.set_link("A", "B")
    a = make_node("A", net, session_key=key)
    b = make_node("B", net)  # never configured with a key at all

    delivered = []
    b.on_deliver = delivered.append

    await a.start()
    await b.start()
    await asyncio.sleep(0.1)

    await a.send("B", b"secret")
    await asyncio.sleep(0.05)

    assert delivered == []
    assert b.store.count_events("drop_no_key") == 1

    await a.stop()
    await b.stop()


@pytest.mark.asyncio
async def test_ack_never_arriving_exhausts_retries_and_queues_for_store_forward():
    """A link exists (so the send itself succeeds and gets ack-tracked),
    but nothing at "Z" ever answers -- section 9's failure case: retries
    exhaust, and the message goes to store-and-forward instead of
    vanishing."""
    net = SimulatedNetwork(seed=10)
    net.set_link("A", "Z")  # a real link, but no Node ever registers as "Z"
    a = make_node("A", net, ack_timeout=0.03, max_retries=1, ack_poll_interval=0.02)
    a.graph.set_edge("A", "Z")  # seed a known route without a full discovery handshake
    await a.start()

    pkt = await a.send("Z", b"help", needs_ack=True)
    assert pkt.msg_id in a.ack_tracker

    await asyncio.sleep(0.15)  # well past ack_timeout with max_retries=1

    assert pkt.msg_id not in a.ack_tracker
    assert pkt.msg_id in a.store_forward

    await a.stop()


@pytest.mark.asyncio
async def test_store_forward_flushes_once_a_route_appears():
    net = SimulatedNetwork(seed=11)
    a = make_node("A", net, sf_retry_interval=0.03)
    b = make_node("B", net)

    delivered_at_b = []
    b.on_deliver = delivered_at_b.append

    await a.start()
    pkt = await a.send("B", b"queued for later")
    assert pkt.msg_id in a.store_forward  # no route yet

    net.set_link("A", "B")
    await b.start()
    await asyncio.sleep(0.15)  # discovery converges, then the flush loop fires

    assert pkt.msg_id not in a.store_forward
    assert len(delivered_at_b) == 1
    assert delivered_at_b[0].payload == b"queued for later"

    await a.stop()
    await b.stop()
