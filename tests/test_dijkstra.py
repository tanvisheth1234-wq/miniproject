from mesh.core.discovery import NodeRole
from mesh.core.packet import RESCUE_DST
from mesh.core.routing import MeshGraph, Router


def _bidirectional(graph: MeshGraph, a: str, b: str, link_quality: float = 1.0, recent_failures: int = 0) -> None:
    graph.set_edge(a, b, link_quality, recent_failures)
    graph.set_edge(b, a, link_quality, recent_failures)


# --- basic pathfinding ----------------------------------------------------------

def test_shortest_path_direct_neighbour():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    router = Router("A", g)

    assert router.shortest_path("B") == ["A", "B"]
    assert router.next_hop("B") == "B"


def test_shortest_path_multi_hop_chain():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    _bidirectional(g, "B", "C")
    router = Router("A", g)

    assert router.shortest_path("C") == ["A", "B", "C"]
    assert router.next_hop("C") == "B"


def test_unreachable_destination_returns_none():
    g = MeshGraph()
    g.add_node("A")
    g.add_node("Z")
    router = Router("A", g)

    assert router.shortest_path("Z") is None
    assert router.next_hop("Z") is None


def test_path_to_self_has_no_next_hop():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    router = Router("A", g)

    assert router.shortest_path("A") == ["A"]
    assert router.next_hop("A") is None


# --- section 8.2's central claim: weighted routing beats hop-count -------------

def test_weighted_routing_avoids_lossy_shortcut():
    """A 1-hop path through a bad link should lose to a 2-hop path through
    good links -- this is the empirical comparison section 8.2 and 16
    build the whole project's headline result around."""
    g = MeshGraph()
    # direct A-B is short but terrible
    _bidirectional(g, "A", "B", link_quality=0.1)
    # A-C-B is longer but both links are solid
    _bidirectional(g, "A", "C", link_quality=1.0)
    _bidirectional(g, "C", "B", link_quality=1.0)
    router = Router("A", g)

    assert router.shortest_path("B") == ["A", "C", "B"]


def test_recent_failures_also_penalise_a_link():
    g = MeshGraph()
    _bidirectional(g, "A", "B", link_quality=1.0, recent_failures=5)
    _bidirectional(g, "A", "C", link_quality=1.0)
    _bidirectional(g, "C", "B", link_quality=1.0)
    router = Router("A", g)

    assert router.shortest_path("B") == ["A", "C", "B"]


def test_equal_quality_prefers_fewer_hops():
    g = MeshGraph()
    _bidirectional(g, "A", "B", link_quality=1.0)
    _bidirectional(g, "A", "C", link_quality=1.0)
    _bidirectional(g, "C", "B", link_quality=1.0)
    router = Router("A", g)

    # direct A-B (cost 1) beats A-C-B (cost 2) when quality is identical
    assert router.shortest_path("B") == ["A", "B"]


# --- RESCUE__ / gateway handling (section 8.3) ----------------------------------

def test_rescue_dst_resolves_to_nearest_gateway():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    _bidirectional(g, "B", "GW")
    router = Router("A", g)
    router.set_role("GW", NodeRole.GATEWAY)

    assert router.shortest_path(RESCUE_DST) == ["A", "B", "GW"]


def test_rescue_dst_picks_cheapest_of_multiple_gateways():
    g = MeshGraph()
    _bidirectional(g, "A", "MID")
    _bidirectional(g, "MID", "GW_FAR")  # 2 hops from A
    _bidirectional(g, "A", "GW_NEAR")  # 1 hop from A
    router = Router("A", g)
    router.set_role("GW_FAR", NodeRole.GATEWAY)
    router.set_role("GW_NEAR", NodeRole.RESCUE)

    assert router.shortest_path(RESCUE_DST) == ["A", "GW_NEAR"]


def test_rescue_dst_none_when_no_gateway_reachable():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    router = Router("A", g)

    assert router.shortest_path(RESCUE_DST) is None


def test_normal_node_role_not_treated_as_terminal():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    router = Router("A", g)
    router.set_role("B", NodeRole.NORMAL)

    assert router.shortest_path(RESCUE_DST) is None


def test_self_as_gateway_resolves_trivially():
    g = MeshGraph()
    g.add_node("A")
    router = Router("A", g)
    router.set_role("A", NodeRole.GATEWAY)

    assert router.shortest_path(RESCUE_DST) == ["A"]
    assert router.next_hop(RESCUE_DST) is None


# --- caching / invalidation -----------------------------------------------------

def test_route_is_cached_until_invalidated():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    router = Router("A", g)

    assert router.shortest_path("B") == ["A", "B"]

    # graph changes but cache is stale until invalidate() is called
    g.remove_edge("A", "B")
    g.remove_edge("B", "A")
    assert router.shortest_path("B") == ["A", "B"]  # still cached

    router.invalidate()
    assert router.shortest_path("B") is None  # now recomputed


def test_set_role_invalidates_cache():
    g = MeshGraph()
    _bidirectional(g, "A", "B")
    router = Router("A", g)

    assert router.shortest_path(RESCUE_DST) is None

    router.set_role("B", NodeRole.GATEWAY)
    assert router.shortest_path(RESCUE_DST) == ["A", "B"]
