import asyncio

import pytest

from mesh.core.packet import Packet, PacketType, Priority
from mesh.core.relay import RelayNode
from mesh.core.transport import TransportError


class _FakeTransport:
    """Records send() calls instead of touching a socket. ``fail_for`` is a
    set of peer IDs whose send() raises TransportError, to test the
    send_failed drop path."""

    def __init__(self, fail_for=None):
        self.callback = None
        self.sent: list[tuple[str, bytes]] = []
        self._fail_for = fail_for or set()

    def on_receive(self, callback):
        self.callback = callback

    async def send(self, node_id, data):
        if node_id in self._fail_for:
            raise TransportError(f"no route to {node_id!r}")
        self.sent.append((node_id, data))

    async def broadcast(self, data):
        pass

    async def start(self):
        pass

    async def stop(self):
        pass


def make_data_packet(**overrides):
    defaults = dict(type=PacketType.DATA, priority=Priority.NORMAL, src="A", dst="C", payload=b"hi")
    defaults.update(overrides)
    return Packet(**defaults)


async def _settle():
    # let any asyncio.create_task() scheduled by the relay actually run
    await asyncio.sleep(0)
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_delivers_packet_addressed_to_self():
    transport = _FakeTransport()
    relay = RelayNode("C", transport)
    relay.register()

    delivered = []
    relay.on_deliver = delivered.append

    pkt = make_data_packet(dst="C")
    transport.callback("A", pkt.pack())
    await _settle()

    assert len(delivered) == 1
    assert delivered[0].payload == b"hi"
    assert transport.sent == []


@pytest.mark.asyncio
async def test_forwards_to_configured_next_hop():
    transport = _FakeTransport()
    relay = RelayNode("B", transport)
    relay.set_next_hop("C", "C")  # single-hop: B can reach C directly
    relay.register()

    pkt = make_data_packet(src="A", dst="C", ttl=5, hop_count=0, path=["A"])
    transport.callback("A", pkt.pack())
    await _settle()

    assert len(transport.sent) == 1
    next_hop_id, data = transport.sent[0]
    assert next_hop_id == "C"
    forwarded = Packet.unpack(data)
    assert forwarded.ttl == 4
    assert forwarded.hop_count == 1
    assert forwarded.path == ["A", "B"]


@pytest.mark.asyncio
async def test_on_forward_hook_called_with_next_hop():
    transport = _FakeTransport()
    relay = RelayNode("B", transport)
    relay.set_next_hop("C", "C")
    relay.register()

    seen = []
    relay.on_forward = lambda pkt, next_hop: seen.append((pkt.dst, next_hop))

    transport.callback("A", make_data_packet(dst="C").pack())
    await _settle()

    assert seen == [("C", "C")]


@pytest.mark.asyncio
async def test_drops_when_no_route_configured():
    transport = _FakeTransport()
    relay = RelayNode("B", transport)
    relay.register()

    drops = []
    relay.on_drop = lambda pkt, reason: drops.append(reason)

    transport.callback("A", make_data_packet(dst="C").pack())
    await _settle()

    assert drops == ["no_route"]
    assert transport.sent == []


@pytest.mark.asyncio
async def test_drops_when_ttl_expired():
    transport = _FakeTransport()
    relay = RelayNode("B", transport)
    relay.set_next_hop("C", "C")
    relay.register()

    drops = []
    relay.on_drop = lambda pkt, reason: drops.append(reason)

    transport.callback("A", make_data_packet(dst="C", ttl=0).pack())
    await _settle()

    assert drops == ["ttl_expired"]
    assert transport.sent == []


@pytest.mark.asyncio
async def test_drops_on_loop_detected():
    transport = _FakeTransport()
    relay = RelayNode("B", transport)
    relay.set_next_hop("C", "C")
    relay.register()

    drops = []
    relay.on_drop = lambda pkt, reason: drops.append(reason)

    # B already appears in the path: this packet already passed through B once
    transport.callback("A", make_data_packet(dst="C", path=["A", "B"]).pack())
    await _settle()

    assert drops == ["loop_detected"]
    assert transport.sent == []


@pytest.mark.asyncio
async def test_drops_on_send_failure():
    transport = _FakeTransport(fail_for={"C"})
    relay = RelayNode("B", transport)
    relay.set_next_hop("C", "C")
    relay.register()

    drops = []
    relay.on_drop = lambda pkt, reason: drops.append(reason)

    transport.callback("A", make_data_packet(dst="C").pack())
    await _settle()

    assert drops == ["send_failed"]


@pytest.mark.asyncio
async def test_ignores_hello_packets():
    transport = _FakeTransport()
    relay = RelayNode("B", transport)
    relay.register()

    delivered = []
    relay.on_deliver = delivered.append

    hello = Packet(type=PacketType.HELLO, priority=Priority.STATUS, src="A", dst="BCAST___", payload=b"NORMAL")
    transport.callback("A", hello.pack())
    await _settle()

    assert delivered == []
    assert transport.sent == []


@pytest.mark.asyncio
async def test_two_hop_relay_a_to_b_to_c():
    """End-to-end shape of the week-2 milestone: A -> B -> C, no sockets."""
    transport_b = _FakeTransport()
    relay_b = RelayNode("B", transport_b)
    relay_b.set_next_hop("C", "C")
    relay_b.register()

    transport_c = _FakeTransport()
    relay_c = RelayNode("C", transport_c)
    relay_c.register()

    delivered_at_c = []
    relay_c.on_deliver = delivered_at_c.append

    # A hands its packet to B's transport (as if A sent it over the wire)
    pkt_from_a = make_data_packet(src="A", dst="C", path=["A"])
    transport_b.callback("A", pkt_from_a.pack())
    await _settle()

    assert len(transport_b.sent) == 1
    next_hop_id, data = transport_b.sent[0]
    assert next_hop_id == "C"

    # simulate that packet arriving at C's transport
    transport_c.callback("B", data)
    await _settle()

    assert len(delivered_at_c) == 1
    assert delivered_at_c[0].path == ["A", "B"]
    assert delivered_at_c[0].hop_count == 1
