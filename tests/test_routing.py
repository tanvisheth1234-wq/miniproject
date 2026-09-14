import pytest

from mesh.core.routing import EdgeInfo, MeshGraph, edge_cost


def test_edge_cost_perfect_link_is_cheapest():
    assert edge_cost(link_quality=1.0, recent_failures=0) == 1.0


def test_edge_cost_penalises_weak_link():
    good = edge_cost(link_quality=1.0, recent_failures=0)
    weak = edge_cost(link_quality=0.2, recent_failures=0)
    assert weak > good


def test_edge_cost_penalises_recent_failures():
    stable = edge_cost(link_quality=1.0, recent_failures=0)
    flaky = edge_cost(link_quality=1.0, recent_failures=2)
    assert flaky > stable


def test_edge_cost_matches_section_8_2_formula():
    # cost = 1 + (1 - link_quality) * 5 + recent_failures * 3
    assert edge_cost(link_quality=0.6, recent_failures=1) == pytest.approx(1 + 0.4 * 5 + 1 * 3)


def test_edge_cost_rejects_out_of_range_quality():
    with pytest.raises(ValueError):
        edge_cost(link_quality=1.5, recent_failures=0)


def test_edge_cost_rejects_negative_failures():
    with pytest.raises(ValueError):
        edge_cost(link_quality=1.0, recent_failures=-1)


def test_add_node_creates_empty_entry():
    g = MeshGraph()
    g.add_node("A")
    assert "A" in g
    assert g.neighbours_of("A") == {}


def test_set_edge_creates_both_endpoints():
    g = MeshGraph()
    g.set_edge("A", "B", link_quality=0.9)
    assert "A" in g
    assert "B" in g
    assert g.neighbours_of("A") == {"B": EdgeInfo(link_quality=0.9, recent_failures=0)}


def test_set_edge_is_directed_not_automatically_reversed():
    g = MeshGraph()
    g.set_edge("A", "B")
    assert g.neighbours_of("B") == {}


def test_set_edge_overwrites_existing():
    g = MeshGraph()
    g.set_edge("A", "B", link_quality=1.0)
    g.set_edge("A", "B", link_quality=0.3)
    assert g.edge("A", "B").link_quality == 0.3


def test_remove_edge():
    g = MeshGraph()
    g.set_edge("A", "B")
    g.remove_edge("A", "B")
    assert g.edge("A", "B") is None
    assert "A" in g  # node itself stays


def test_remove_node_drops_incoming_and_outgoing_edges():
    g = MeshGraph()
    g.set_edge("A", "B")
    g.set_edge("B", "A")
    g.set_edge("B", "C")
    g.remove_node("B")
    assert "B" not in g
    assert g.edge("A", "B") is None
    assert g.neighbours_of("C") == {}


def test_nodes_lists_every_known_node():
    g = MeshGraph()
    g.set_edge("A", "B")
    g.add_node("C")
    assert sorted(g.nodes()) == ["A", "B", "C"]


def test_len_counts_nodes():
    g = MeshGraph()
    g.set_edge("A", "B")
    assert len(g) == 2
