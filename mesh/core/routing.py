"""Mesh-wide routing: link-state graph, weighted cost function, Dijkstra.

Spec: docs/project-plan.md section 8 (Routing). Each node gossips its own
neighbour list (section 8.1); this module merges those reports into a
``MeshGraph`` and computes the cheapest path to any destination over it
(section 8.3), using link quality rather than hop count as the cost
(section 8.2). This is what ``node.py`` plugs into ``relay.py`` in place
of the static next-hop table it uses today.
"""

from __future__ import annotations

from dataclasses import dataclass


# --- Section 8.2 cost function -----------------------------------------------

def edge_cost(link_quality: float, recent_failures: int) -> float:
    """Weight of one directed link, per section 8.2.

    ``link_quality`` is the fraction of the last 20 expected HELLOs that
    actually arrived, in [0, 1] -- 1.0 is a perfect link. ``recent_failures``
    is the count of ACK timeouts attributed to this link in the last 60s.
    Weak or failing links cost more, so Dijkstra prefers reliable links
    over merely short ones.
    """
    if not 0.0 <= link_quality <= 1.0:
        raise ValueError(f"link_quality must be in [0, 1], got {link_quality}")
    if recent_failures < 0:
        raise ValueError(f"recent_failures must be >= 0, got {recent_failures}")
    return 1.0 + (1.0 - link_quality) * 5.0 + recent_failures * 3.0


@dataclass
class EdgeInfo:
    link_quality: float = 1.0
    recent_failures: int = 0

    @property
    def cost(self) -> float:
        return edge_cost(self.link_quality, self.recent_failures)


class MeshGraph:
    """The mesh as a weighted directed graph: vertices are node IDs, edges
    are active links (section 8.1). Built up from link-state reports --
    this class only stores the graph, it doesn't gossip or pathfind."""

    def __init__(self) -> None:
        # adjacency[a][b] = EdgeInfo for the directed edge a -> b
        self._adjacency: dict[str, dict[str, EdgeInfo]] = {}

    def add_node(self, node_id: str) -> None:
        """Ensure ``node_id`` exists in the graph, even with no edges yet."""
        self._adjacency.setdefault(node_id, {})

    def set_edge(
        self,
        a: str,
        b: str,
        link_quality: float = 1.0,
        recent_failures: int = 0,
    ) -> None:
        """Add or update the directed edge a -> b. Link-state reports are
        per-direction (a node reports its own view of a link), so this does
        not automatically add the reverse edge b -> a."""
        self.add_node(a)
        self.add_node(b)
        self._adjacency[a][b] = EdgeInfo(link_quality=link_quality, recent_failures=recent_failures)

    def remove_edge(self, a: str, b: str) -> None:
        if a in self._adjacency:
            self._adjacency[a].pop(b, None)

    def remove_node(self, node_id: str) -> None:
        """Drop ``node_id`` and every edge touching it -- used when a peer
        is declared dead (section 9: heartbeat)."""
        self._adjacency.pop(node_id, None)
        for neighbours in self._adjacency.values():
            neighbours.pop(node_id, None)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._adjacency

    def nodes(self) -> list[str]:
        return list(self._adjacency.keys())

    def neighbours_of(self, node_id: str) -> dict[str, EdgeInfo]:
        """The outgoing edges from ``node_id``, as {neighbour_id: EdgeInfo}."""
        return dict(self._adjacency.get(node_id, {}))

    def edge(self, a: str, b: str) -> EdgeInfo | None:
        return self._adjacency.get(a, {}).get(b)

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._adjacency

    def __len__(self) -> int:
        return len(self._adjacency)
