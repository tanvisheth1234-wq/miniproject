import asyncio

import pytest

from mesh.core.transport import TransportError
from mesh.core.transport_sim import LinkConfig, SimulatedNetwork, SimulatedTransport


# --- LinkConfig validation ----------------------------------------------------

def test_link_config_rejects_loss_out_of_range():
    with pytest.raises(ValueError):
        LinkConfig(loss=1.5)
    with pytest.raises(ValueError):
        LinkConfig(loss=-0.1)


def test_link_config_rejects_invalid_latency_range():
    with pytest.raises(ValueError):
        LinkConfig(latency_ms=(-1, 5))
    with pytest.raises(ValueError):
        LinkConfig(latency_ms=(10, 5))


# --- link matrix ---------------------------------------------------------------

def test_set_link_is_bidirectional_by_default():
    net = SimulatedNetwork()
    net.set_link("A", "B", loss=0.1, latency_ms=(5, 10))
    assert net.linked("A", "B")
    assert net.linked("B", "A")


def test_set_link_can_be_unidirectional():
    net = SimulatedNetwork()
    net.set_link("A", "B", bidirectional=False)
    assert net.linked("A", "B")
    assert not net.linked("B", "A")


def test_remove_link():
    net = SimulatedNetwork()
    net.set_link("A", "B")
    net.remove_link("A", "B")
    assert not net.linked("A", "B")
    assert not net.linked("B", "A")


def test_neighbours_of_reflects_link_matrix():
    net = SimulatedNetwork()
    net.set_link("A", "B")
    net.set_link("A", "C")
    assert sorted(net.neighbours_of("A")) == ["B", "C"]
    assert net.neighbours_of("D") == []


# --- send() / delivery ----------------------------------------------------------

@pytest.mark.asyncio
async def test_send_without_link_raises_transport_error():
    net = SimulatedNetwork()
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    await a.start()
    await b.start()

    with pytest.raises(TransportError):
        await a.send("B", b"hi")


@pytest.mark.asyncio
async def test_send_delivers_with_zero_latency():
    net = SimulatedNetwork()
    net.set_link("A", "B")
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    await a.start()
    await b.start()

    received = []
    b.on_receive(lambda sender, data: received.append((sender, data)))

    await a.send("B", b"hello")
    await asyncio.sleep(0)  # let the scheduled delivery task run

    assert received == [("A", b"hello")]


@pytest.mark.asyncio
async def test_send_respects_latency_delay():
    net = SimulatedNetwork(seed=1)
    net.set_link("A", "B", latency_ms=(50, 50))
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    await a.start()
    await b.start()

    received = []
    b.on_receive(lambda sender, data: received.append((sender, data)))

    await a.send("B", b"hello")
    await asyncio.sleep(0.01)
    assert received == []  # 50ms hasn't elapsed yet

    await asyncio.sleep(0.06)
    assert received == [("A", b"hello")]


@pytest.mark.asyncio
async def test_loss_probability_one_always_drops():
    net = SimulatedNetwork(seed=42)
    net.set_link("A", "B", loss=1.0)
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    await a.start()
    await b.start()

    received = []
    b.on_receive(lambda sender, data: received.append((sender, data)))

    for _ in range(20):
        await a.send("B", b"hello")
    await asyncio.sleep(0)

    assert received == []


@pytest.mark.asyncio
async def test_loss_probability_zero_never_drops():
    net = SimulatedNetwork(seed=42)
    net.set_link("A", "B", loss=0.0)
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    await a.start()
    await b.start()

    received = []
    b.on_receive(lambda sender, data: received.append((sender, data)))

    for _ in range(20):
        await a.send("B", b"hello")
    await asyncio.sleep(0)

    assert len(received) == 20


@pytest.mark.asyncio
async def test_seeded_network_reproduces_same_loss_pattern():
    def run_with_seed(seed):
        async def _run():
            net = SimulatedNetwork(seed=seed)
            net.set_link("A", "B", loss=0.5)
            a = SimulatedTransport("A", net)
            b = SimulatedTransport("B", net)
            await a.start()
            await b.start()
            received = []
            b.on_receive(lambda sender, data: received.append(data))
            for i in range(30):
                await a.send("B", str(i).encode())
            await asyncio.sleep(0)
            return received
        return _run()

    first = await run_with_seed(7)
    second = await run_with_seed(7)
    assert first == second


# --- broadcast() ------------------------------------------------------------------

@pytest.mark.asyncio
async def test_broadcast_delivers_only_to_linked_neighbours():
    net = SimulatedNetwork()
    net.set_link("A", "B")
    net.set_link("A", "C")
    # D is not linked to A: out of range, per the visible_neighbours philosophy
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    c = SimulatedTransport("C", net)
    d = SimulatedTransport("D", net)
    for t in (a, b, c, d):
        await t.start()

    received_b, received_c, received_d = [], [], []
    b.on_receive(lambda sender, data: received_b.append(data))
    c.on_receive(lambda sender, data: received_c.append(data))
    d.on_receive(lambda sender, data: received_d.append(data))

    await a.broadcast(b"hello everyone in range")
    await asyncio.sleep(0)

    assert received_b == [b"hello everyone in range"]
    assert received_c == [b"hello everyone in range"]
    assert received_d == []


@pytest.mark.asyncio
async def test_broadcast_with_no_links_does_nothing():
    net = SimulatedNetwork()
    a = SimulatedTransport("A", net)
    await a.start()
    await a.broadcast(b"into the void")  # should not raise
    await asyncio.sleep(0)


# --- start()/stop() registration -------------------------------------------------

@pytest.mark.asyncio
async def test_stop_unregisters_from_network():
    net = SimulatedNetwork()
    net.set_link("A", "B")
    a = SimulatedTransport("A", net)
    b = SimulatedTransport("B", net)
    await a.start()
    await b.start()
    await b.stop()

    received = []
    b.on_receive(lambda sender, data: received.append(data))
    await a.send("B", b"still linked, but B unregistered")
    await asyncio.sleep(0)

    assert received == []  # network has no transport to deliver to anymore
