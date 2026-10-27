"""Regression tests for the ACK path over several hops. Before the relay's
dedup key included the packet type and the retransmission counter, an ACK
returning along the path its DATA had taken was dropped as a "duplicate" at
the first shared relay, and a retry was swallowed by the first relay that
had seen the original -- so multi-hop ACK + retry simply did not work."""

import asyncio

import pytest

from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import PacketType, Priority
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport
from conftest import async_wait_until


def make_node(node_id, network, **kwargs):
    kwargs.setdefault("hello_interval", 0.02)
    kwargs.setdefault("neighbour_timeout", 0.5)
    kwargs.setdefault("link_state_interval", 0.03)
    kwargs.setdefault("ack_timeout", 0.15)
    kwargs.setdefault("ack_poll_interval", 0.02)
    return Node(node_id, SimulatedTransport(node_id, network), **kwargs)


async def chain(*ids, roles=None):
    net = SimulatedNetwork(seed=1)
    for a, b in zip(ids, ids[1:]):
        net.set_link(a, b)
    nodes = {i: make_node(i, net, role=(roles or {}).get(i, NodeRole.NORMAL)) for i in ids}
    for node in nodes.values():
        await node.start()
    # discovery + link-state have converged once the first node routes to the last
    await async_wait_until(lambda: nodes[ids[0]].router.shortest_path(ids[-1]) == list(ids))
    return nodes


async def stop(nodes):
    for node in nodes.values():
        await node.stop()


@pytest.mark.asyncio
async def test_ack_returns_over_the_path_the_data_took():
    nodes = await chain("A", "B", "C", "D")
    try:
        pkt = await nodes["A"].send("D", b"hello", Priority.SOS, needs_ack=True)
        row = await async_wait_until(
            lambda: (r := nodes["A"].store.get_message(str(pkt.msg_id)))["status"] == "delivered" and r)

        assert row["status"] == "delivered"
        assert row["hop_count"] == 2          # the sender learns the route from the ACK
        assert row["path"] == "B,C"
        assert nodes["A"].store.count_events("retry") == 0
    finally:
        await stop(nodes)


@pytest.mark.asyncio
async def test_a_lost_ack_is_re_sent_when_the_sender_retries():
    nodes = await chain("A", "B", "C", "D")
    try:
        delivered = []
        nodes["D"].on_deliver = lambda p: delivered.append(p.payload)

        real_send = nodes["D"].transport.send
        dropped = []

        async def lose_first_ack(node_id, data):
            from mesh.core.packet import Packet

            if Packet.unpack(data).type == PacketType.ACK and not dropped:
                dropped.append(data)
                return  # the ACK vanishes on the air
            await real_send(node_id, data)

        nodes["D"].transport.send = lose_first_ack

        pkt = await nodes["A"].send("D", b"are you there", Priority.SOS, needs_ack=True)
        await asyncio.sleep(0.6)

        assert dropped, "the test should have swallowed one ACK"
        assert nodes["A"].store.get_message(str(pkt.msg_id))["status"] == "delivered"
        assert nodes["A"].store.count_events("retry") >= 1
        assert delivered == [b"are you there"]           # the app on D saw it exactly once
        assert nodes["D"].store.count_events("drop_dup") >= 1
    finally:
        await stop(nodes)


@pytest.mark.asyncio
async def test_a_retry_crosses_relays_that_already_forwarded_the_original():
    nodes = await chain("A", "B", "C", "D")
    try:
        real_send = nodes["C"].transport.send
        swallowed = []

        async def lose_first_data_to_d(node_id, data):
            from mesh.core.packet import Packet

            pkt = Packet.unpack(data)
            if pkt.type == PacketType.DATA and node_id == "D" and not swallowed:
                swallowed.append(pkt)  # lost on the C -> D hop, after B and C both forwarded it
                return
            await real_send(node_id, data)

        nodes["C"].transport.send = lose_first_data_to_d

        pkt = await nodes["A"].send("D", b"second try", Priority.NORMAL, needs_ack=True)
        await asyncio.sleep(0.6)

        assert swallowed
        assert nodes["A"].store.get_message(str(pkt.msg_id))["status"] == "delivered"
        assert nodes["B"].store.count_events("forward") >= 2   # original + the retry
    finally:
        await stop(nodes)
