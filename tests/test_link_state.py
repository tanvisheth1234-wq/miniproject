import asyncio

import pytest

from mesh.core.discovery import NodeRole
from mesh.core.packet import Packet, PacketType
from mesh.core.routing import EdgeInfo, LinkStateGossip, MeshGraph, ReportEntry, decode_report, encode_report


# --- a minimal in-memory Transport supporting unicast send, for testing -------

class _Bus:
    def __init__(self):
        self._transports: dict[str, "_FakeTransport"] = {}

    def register(self, node_id: str, transport: "_FakeTransport") -> None:
        self._transports[node_id] = transport

    def deliver(self, sender_id: str, dst: str, data: bytes) -> None:
        transport = self._transports.get(dst)
        if transport is not None and transport.callback is not None:
            transport.callback(sender_id, data)


class _FakeTransport:
    def __init__(self, node_id: str, bus: _Bus):
        self.node_id = node_id
        self._bus = bus
        self.callback = None
        self.sent = []
        bus.register(node_id, self)

    def on_receive(self, callback):
        self.callback = callback

    async def start(self):
        pass

    async def stop(self):
        pass

    async def send(self, node_id, data):
        self.sent.append((node_id, data))
        self._bus.deliver(self.node_id, node_id, data)

    async def broadcast(self, data):
        pass


# --- encode/decode round trip --------------------------------------------------

def test_encode_decode_round_trip():
    entries = {
        "B": ReportEntry(link_quality=0.75, recent_failures=2, role=NodeRole.NORMAL),
        "C": ReportEntry(link_quality=1.0, recent_failures=0, role=NodeRole.GATEWAY),
    }
    payload = encode_report(entries)
    decoded = decode_report(payload)
    assert decoded["B"].recent_failures == 2
    assert decoded["C"].link_quality == pytest.approx(1.0)
    assert decoded["C"].role == NodeRole.GATEWAY


def test_decode_empty_payload():
    assert decode_report(b"") == {}


def test_decode_rejects_truncated_payload():
    with pytest.raises(ValueError):
        decode_report(b"short")


def test_role_round_trips_for_all_roles():
    for role in (NodeRole.NORMAL, NodeRole.GATEWAY, NodeRole.RESCUE):
        payload = encode_report({"B": ReportEntry(role=role)})
        assert decode_report(payload)["B"].role == role


def test_encode_caps_failures_at_255():
    payload = encode_report({"B": ReportEntry(link_quality=1.0, recent_failures=1000)})
    decoded = decode_report(payload)
    assert decoded["B"].recent_failures == 255


# --- LinkStateGossip: sending --------------------------------------------------

@pytest.mark.asyncio
async def test_send_report_reaches_each_neighbour():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    b = _FakeTransport("B", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: ["B"])

    await gossip_a.send_report()

    assert len(a.sent) == 1
    dst, data = a.sent[0]
    assert dst == "B"
    pkt = Packet.unpack(data)
    assert pkt.type == PacketType.LINK_STATE
    assert pkt.src == "A"
    assert pkt.ttl == 1


@pytest.mark.asyncio
async def test_send_report_syncs_own_direct_edges_into_graph():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: ["B", "C"])

    await gossip_a.send_report()

    assert graph_a.edge("A", "B") == EdgeInfo(link_quality=1.0, recent_failures=0)
    assert graph_a.edge("A", "C") == EdgeInfo(link_quality=1.0, recent_failures=0)


@pytest.mark.asyncio
async def test_send_report_uses_recorded_quality_and_failures():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: ["B"])
    gossip_a.record_link_quality("B", 0.4)
    gossip_a.record_failure("B")

    await gossip_a.send_report()

    edge = graph_a.edge("A", "B")
    assert edge.link_quality == pytest.approx(0.4)
    assert edge.recent_failures == 1


@pytest.mark.asyncio
async def test_stale_own_edge_removed_when_neighbour_drops_out():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    current = ["B"]
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: current)

    await gossip_a.send_report()
    assert graph_a.edge("A", "B") is not None

    current = []
    await gossip_a.send_report()
    assert graph_a.edge("A", "B") is None


# --- LinkStateGossip: receiving and merging -------------------------------------

def test_receiving_report_merges_reported_edges_into_graph():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: ["B"])

    payload = encode_report({"C": ReportEntry(link_quality=0.5, recent_failures=1)})
    report = Packet(type=PacketType.LINK_STATE, priority=1, src="B", dst="A", ttl=1, payload=payload)

    gossip_a._on_receive("B", report.pack())

    edge = graph_a.edge("B", "C")
    assert edge.link_quality == pytest.approx(0.5)
    assert edge.recent_failures == 1


def test_receiving_report_teaches_learned_role():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: [])
    learned = []
    gossip_a.on_role_learned = lambda node_id, role: learned.append((node_id, role))

    payload = encode_report({"GW": ReportEntry(role=NodeRole.GATEWAY)})
    report = Packet(type=PacketType.LINK_STATE, priority=1, src="B", dst="A", ttl=1, payload=payload)
    gossip_a._on_receive("B", report.pack())

    assert learned == [("GW", NodeRole.GATEWAY)]


def test_send_report_includes_role_from_role_provider():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip(
        "A", a, graph_a,
        neighbours_provider=lambda: ["B"],
        role_provider=lambda node_id: NodeRole.RESCUE if node_id == "B" else NodeRole.NORMAL,
    )

    asyncio.run(gossip_a.send_report())

    _, data = a.sent[0]
    pkt = Packet.unpack(data)
    decoded = decode_report(pkt.payload)
    assert decoded["B"].role == NodeRole.RESCUE


def test_on_topology_change_fires_when_graph_actually_changes():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: [])
    fired = []
    gossip_a.on_topology_change = lambda: fired.append(True)

    payload = encode_report({"C": ReportEntry(link_quality=1.0, recent_failures=0)})
    report = Packet(type=PacketType.LINK_STATE, priority=1, src="B", dst="A", ttl=1, payload=payload)
    gossip_a._on_receive("B", report.pack())
    assert len(fired) == 1

    # identical report again: no real change, should not re-fire
    gossip_a._on_receive("B", report.pack())
    assert len(fired) == 1


def test_non_link_state_packet_ignored():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: [])

    data_pkt = Packet(type=PacketType.DATA, priority=1, src="B", dst="A", payload=b"hi")
    gossip_a._on_receive("B", data_pkt.pack())

    assert len(graph_a) == 0


def test_forget_neighbour_removes_from_graph_and_own_report():
    bus = _Bus()
    a = _FakeTransport("A", bus)
    graph_a = MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: ["B"])
    fired = []
    gossip_a.on_topology_change = lambda: fired.append(True)

    asyncio.run(gossip_a.send_report())
    assert graph_a.edge("A", "B") is not None

    gossip_a.forget_neighbour("B")
    assert graph_a.edge("A", "B") is None
    assert "B" not in graph_a
    assert fired == [True]


@pytest.mark.asyncio
async def test_two_nodes_converge_on_each_others_graph_view():
    """A and B are neighbours; after one round of gossip each learns the
    other's report, matching section 8.1's "propagate to build a shared
    graph" behaviour end to end."""
    bus = _Bus()
    a = _FakeTransport("A", bus)
    b = _FakeTransport("B", bus)
    graph_a, graph_b = MeshGraph(), MeshGraph()
    gossip_a = LinkStateGossip("A", a, graph_a, neighbours_provider=lambda: ["B"])
    gossip_b = LinkStateGossip("B", b, graph_b, neighbours_provider=lambda: ["A"])
    a.on_receive(gossip_a._on_receive)
    b.on_receive(gossip_b._on_receive)

    await gossip_a.send_report()
    await gossip_b.send_report()

    assert graph_a.edge("A", "B") is not None  # own direct edge
    assert graph_a.edge("B", "A") is not None  # learned from B's report
    assert graph_b.edge("B", "A") is not None
    assert graph_b.edge("A", "B") is not None
