"""Link quality (section 8.2) measured from HELLO reception, and the
hop-count routing mode used as the baseline for section 16's
"weighted vs hop-count" comparison."""

import pytest

from mesh.core import discovery as discovery_mod
from mesh.core.discovery import Discovery
from mesh.core.node import Node
from mesh.core.packet import BROADCAST_DST, Packet, PacketType, Priority
from mesh.core.routing import MeshGraph, Router
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch):
    fake = FakeClock()
    monkeypatch.setattr(discovery_mod.time, "monotonic", fake)
    return fake


def hello_from(src: str) -> bytes:
    return Packet(
        type=PacketType.HELLO, priority=Priority.STATUS, src=src,
        dst=BROADCAST_DST, ttl=1, payload=b"NORMAL",
    ).pack()


def make_discovery(hello_interval: float = 1.0) -> Discovery:
    net = SimulatedNetwork(seed=1)
    return Discovery("A", SimulatedTransport("A", net), hello_interval=hello_interval)


def test_unknown_neighbour_has_no_link_quality():
    assert make_discovery().link_quality("B") is None


def test_a_new_link_is_not_penalised_for_hellos_not_yet_due(clock):
    disc = make_discovery()
    disc._on_receive("B", hello_from("B"))
    assert disc.link_quality("B") == 1.0


def test_perfect_reception_scores_one(clock):
    disc = make_discovery()
    for _ in range(25):
        disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    assert disc.link_quality("B", clock.now) == pytest.approx(1.0, abs=0.06)


def test_losing_every_other_hello_scores_about_half(clock):
    disc = make_discovery()
    for i in range(40):
        if i % 2 == 0:
            disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    assert disc.link_quality("B", clock.now) == pytest.approx(0.5, abs=0.1)


def test_quality_change_is_reported_only_when_it_moves_enough(clock):
    disc = make_discovery()
    reported = []
    disc.on_link_quality = lambda peer, q: reported.append((peer, q))

    for _ in range(25):  # steady 100% -- nothing new to report
        disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    assert reported == []

    for i in range(40):  # degrades to ~50%
        if i % 2 == 0:
            disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    assert reported, "a real drop in reception should have been reported"
    assert all(peer == "B" and 0.0 <= q <= 1.0 for peer, q in reported)
    assert reported[-1][1] < 0.8


def test_forgetting_a_neighbour_resets_its_history(clock):
    disc = make_discovery()
    disc._on_receive("B", hello_from("B"))
    disc._forget_link_quality("B")
    assert disc.link_quality("B") is None


def two_path_graph() -> MeshGraph:
    """S -> M -> D is 2 hops over a flaky link; S -> X -> Y -> D is 3 hops
    over clean links."""
    graph = MeshGraph()
    graph.set_edge("S", "M", link_quality=0.4)
    graph.set_edge("M", "D", link_quality=1.0)
    graph.set_edge("S", "X", link_quality=1.0)
    graph.set_edge("X", "Y", link_quality=1.0)
    graph.set_edge("Y", "D", link_quality=1.0)
    return graph


def test_weighted_routing_avoids_the_flaky_short_path():
    router = Router("S", two_path_graph())
    assert router.shortest_path("D") == ["S", "X", "Y", "D"]


def test_hop_count_routing_takes_the_flaky_short_path():
    router = Router("S", two_path_graph(), cost_fn=lambda _edge: 1.0)
    assert router.shortest_path("D") == ["S", "M", "D"]


def test_node_exposes_the_hop_count_switch():
    net = SimulatedNetwork(seed=1)
    weighted = Node("A", SimulatedTransport("A", net))
    flat = Node("B", SimulatedTransport("B", net), hop_count_routing=True)
    assert weighted.hop_count_routing is False
    assert flat.hop_count_routing is True
    weighted.graph.set_edge("A", "X", link_quality=0.2)
    flat.graph.set_edge("B", "X", link_quality=0.2)
    assert weighted.graph.edge("A", "X").cost > 1.0
    assert flat.router._cost_fn(flat.graph.edge("B", "X")) == 1.0


def test_a_flapping_link_keeps_its_history_instead_of_resetting_to_perfect(clock):
    """A lossy link that gets declared dead and comes back must not look
    flawless again -- that would send traffic straight back down it."""
    disc = make_discovery()
    for i in range(30):
        if i % 2 == 0:
            disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    before = disc.link_quality("B", clock.now)
    assert before < 0.7

    clock.now += 5.0  # a short silence, well inside the 20-HELLO window
    disc._on_receive("B", hello_from("B"))
    assert disc.link_quality("B", clock.now) < 0.75


def test_a_long_silence_starts_the_estimate_afresh(clock):
    disc = make_discovery()
    for i in range(30):
        if i % 2 == 0:
            disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    clock.now += 100.0  # far longer than the whole window
    disc._on_receive("B", hello_from("B"))
    assert disc.link_quality("B", clock.now) == 1.0


def test_a_returning_lossy_neighbour_is_reported_even_if_it_was_already_reported_before(clock):
    disc = make_discovery()
    reported = []
    disc.on_link_quality = lambda peer, q: reported.append((peer, round(q, 2)))
    disc.on_peer_up = lambda peer, role: None
    for i in range(30):  # builds up a ~50% history and reports it
        if i % 2 == 0:
            disc._on_receive("B", hello_from("B"))
        clock.now += 1.0
    reported.clear()

    disc.neighbours.prune(timeout_s=0, now_ms=2**62)  # declared dead...
    clock.now += 3.0
    disc._on_receive("B", hello_from("B"))            # ...and back, still lossy
    assert reported and reported[-1][0] == "B" and reported[-1][1] < 0.8
