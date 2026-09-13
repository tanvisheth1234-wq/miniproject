import asyncio

import pytest

from mesh.core.discovery import Discovery, NeighbourTable, NodeRole
from mesh.core.packet import Packet, PacketType, Priority


# --- a minimal in-memory Transport, for testing Discovery without sockets ---

class _Bus:
    def __init__(self):
        self._transports: list["_FakeTransport"] = []

    def register(self, transport: "_FakeTransport") -> None:
        self._transports.append(transport)

    def deliver(self, sender_id: str, data: bytes) -> None:
        for transport in self._transports:
            if transport.callback is not None:
                transport.callback(sender_id, data)


class _FakeTransport:
    def __init__(self, node_id: str, bus: _Bus):
        self.node_id = node_id
        self._bus = bus
        self.callback = None
        bus.register(self)

    def on_receive(self, callback):
        self.callback = callback

    async def start(self):
        pass

    async def stop(self):
        pass

    async def send(self, node_id, data):
        pass

    async def broadcast(self, data):
        self._bus.deliver(self.node_id, data)


# --- NeighbourTable -----------------------------------------------------------

def test_update_reports_new_neighbour_once():
    table = NeighbourTable()
    assert table.update("B", NodeRole.NORMAL, now_ms=0) is True
    assert table.update("B", NodeRole.NORMAL, now_ms=100) is False


def test_prune_removes_only_stale_neighbours():
    table = NeighbourTable()
    table.update("B", NodeRole.NORMAL, now_ms=0)
    table.update("C", NodeRole.NORMAL, now_ms=9_000)
    dead = table.prune(timeout_s=10, now_ms=10_500)
    assert dead == ["B"]
    assert "B" not in table
    assert "C" in table


def test_get_and_snapshot():
    table = NeighbourTable()
    table.update("B", NodeRole.GATEWAY, now_ms=0)
    info = table.get("B")
    assert info.node_id == "B"
    assert info.role == NodeRole.GATEWAY
    assert table.snapshot() == {"B": info}
    assert len(table) == 1


# --- Discovery: HELLO broadcast and neighbour tracking ------------------------

@pytest.mark.asyncio
async def test_hello_is_broadcast_on_start():
    bus = _Bus()
    transport = _FakeTransport("A", bus)
    disc = Discovery("A", transport, hello_interval=0.05)
    sent = []
    orig_broadcast = transport.broadcast

    async def spy_broadcast(data):
        sent.append(data)
        await orig_broadcast(data)

    transport.broadcast = spy_broadcast

    await disc.start()
    await asyncio.sleep(0.12)
    await disc.stop()

    assert len(sent) >= 2
    pkt = Packet.unpack(sent[0])
    assert pkt.type == PacketType.HELLO
    assert pkt.priority == Priority.STATUS
    assert pkt.src == "A"
    assert pkt.ttl == 1


@pytest.mark.asyncio
async def test_neighbour_added_on_hello_received():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    b = _FakeTransport("B", bus)

    disc_a = Discovery("A", a, hello_interval=0.05)
    disc_b = Discovery("B", b, hello_interval=0.05, role=NodeRole.GATEWAY)

    await disc_a.start()
    await disc_b.start()
    await asyncio.sleep(0.12)
    await disc_a.stop()
    await disc_b.stop()

    assert "B" in disc_a.neighbours
    assert disc_a.neighbours.get("B").role == NodeRole.GATEWAY
    assert "A" in disc_b.neighbours


@pytest.mark.asyncio
async def test_own_hello_not_added_as_neighbour():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    disc_a = Discovery("A", a, hello_interval=0.05)

    await disc_a.start()
    await asyncio.sleep(0.12)
    await disc_a.stop()

    assert "A" not in disc_a.neighbours
    assert len(disc_a.neighbours) == 0


@pytest.mark.asyncio
async def test_non_hello_packet_ignored():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    disc_a = Discovery("A", a, hello_interval=10)  # won't fire during the test
    await disc_a.start()

    data_pkt = Packet(type=PacketType.DATA, priority=Priority.NORMAL, src="B", dst="A", payload=b"hi")
    bus.deliver("B", data_pkt.pack())

    await disc_a.stop()
    assert "B" not in disc_a.neighbours


@pytest.mark.asyncio
async def test_on_peer_up_fires_once_for_new_neighbour():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    b = _FakeTransport("B", bus)
    disc_a = Discovery("A", a, hello_interval=0.05)
    disc_b = Discovery("B", b, hello_interval=0.05)

    seen = []
    disc_a.on_peer_up = lambda node_id, role: seen.append((node_id, role))

    await disc_a.start()
    await disc_b.start()
    await asyncio.sleep(0.16)
    await disc_a.stop()
    await disc_b.stop()

    assert seen == [("B", NodeRole.NORMAL)]


@pytest.mark.asyncio
async def test_neighbour_marked_dead_after_timeout():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    disc_a = Discovery("A", a, hello_interval=10, neighbour_timeout=0.1, prune_interval=0.03)
    await disc_a.start()

    hello = Packet(type=PacketType.HELLO, priority=Priority.STATUS, src="B", dst="BCAST___", ttl=1, payload=b"NORMAL")
    bus.deliver("B", hello.pack())
    assert "B" in disc_a.neighbours

    down_events = []
    disc_a.on_peer_down = lambda node_id: down_events.append(node_id)

    await asyncio.sleep(0.2)
    await disc_a.stop()

    assert "B" not in disc_a.neighbours
    assert down_events == ["B"]


@pytest.mark.asyncio
async def test_visible_neighbours_filters_unlisted_senders():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    disc_a = Discovery("A", a, hello_interval=10, visible_neighbours=["B"])
    await disc_a.start()

    hello_from_b = Packet(type=PacketType.HELLO, priority=Priority.STATUS, src="B", dst="BCAST___", ttl=1, payload=b"NORMAL")
    hello_from_c = Packet(type=PacketType.HELLO, priority=Priority.STATUS, src="C", dst="BCAST___", ttl=1, payload=b"NORMAL")
    bus.deliver("B", hello_from_b.pack())
    bus.deliver("C", hello_from_c.pack())

    await disc_a.stop()

    assert "B" in disc_a.neighbours
    assert "C" not in disc_a.neighbours


@pytest.mark.asyncio
async def test_stop_cancels_background_tasks():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    disc_a = Discovery("A", a, hello_interval=0.02, prune_interval=0.02)
    await disc_a.start()
    await asyncio.sleep(0.05)
    await disc_a.stop()

    assert disc_a._hello_task is None
    assert disc_a._prune_task is None
