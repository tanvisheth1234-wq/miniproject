"""Ready-made mesh layouts for the lab. Positions are only hints for the UI
(0..1 on both axes); the engine itself never sees them -- who can hear whom
comes from the links alone."""

from __future__ import annotations

from dataclasses import dataclass, field

from mesh.core.discovery import NodeRole

LATENCY_MS = (50.0, 120.0)  # per hop; slow enough that a packet's journey is watchable


@dataclass
class NodeSpec:
    node_id: str
    role: str = NodeRole.NORMAL
    label: str = ""
    x: float = 0.5
    y: float = 0.5

    def to_dict(self) -> dict:
        return {"id": self.node_id, "role": self.role, "label": self.label or self.node_id, "x": self.x, "y": self.y}


@dataclass
class LinkSpec:
    a: str
    b: str
    loss: float = 0.0
    latency_ms: tuple[float, float] = LATENCY_MS

    @property
    def key(self) -> tuple[str, str]:
        return (self.a, self.b) if self.a <= self.b else (self.b, self.a)

    def to_dict(self) -> dict:
        return {"a": self.a, "b": self.b, "loss": self.loss, "latency_ms": list(self.latency_ms)}


@dataclass
class Preset:
    id: str
    title: str
    summary: str
    nodes: list[NodeSpec] = field(default_factory=list)
    links: list[LinkSpec] = field(default_factory=list)
    sender: str = ""  # who the guided demo treats as the trapped person

    def meta(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "nodes": len(self.nodes),
            "links": len(self.links),
            "sender": self.sender,
        }


def demo5() -> Preset:
    """Section 18's five-machine demo. L1 can't see the gateway; L2 and L3
    are two independent ways across; L5 is only reachable through L4, so
    when L4 dies the rescue team really is cut off."""
    nodes = [
        NodeSpec("L1", NodeRole.NORMAL, "Trapped sender", 0.08, 0.50),
        NodeSpec("L2", NodeRole.NORMAL, "Relay", 0.38, 0.20),
        NodeSpec("L3", NodeRole.NORMAL, "Relay", 0.38, 0.80),
        NodeSpec("L4", NodeRole.GATEWAY, "Gateway", 0.68, 0.50),
        NodeSpec("L5", NodeRole.RESCUE, "Rescue command", 0.94, 0.50),
    ]
    links = [LinkSpec("L1", "L2"), LinkSpec("L1", "L3"), LinkSpec("L2", "L4"),
             LinkSpec("L3", "L4"), LinkSpec("L4", "L5")]
    return Preset("demo5", "Five-node demo", "The panel demo from the project plan: a trapped sender, two relays, "
                  "a gateway that starts the story and a rescue command post.", nodes, links, sender="L1")


def _grid(rows: int, cols: int, loss: float, gateway_at: tuple[int, int]) -> tuple[list[NodeSpec], list[LinkSpec], str]:
    nodes: list[NodeSpec] = []
    ids: dict[tuple[int, int], str] = {}
    counter = 1
    for r in range(rows):
        for c in range(cols):
            x = 0.06 + 0.78 * (c / max(1, cols - 1))
            y = 0.10 + 0.80 * (r / max(1, rows - 1))
            if (r, c) == gateway_at:
                node_id, role, label = "G1", NodeRole.GATEWAY, "Gateway"
            else:
                node_id, role, label = f"N{counter}", NodeRole.NORMAL, "Survivor"
                counter += 1
            ids[(r, c)] = node_id
            nodes.append(NodeSpec(node_id, role, label, x, y))
    links = []
    for r in range(rows):
        for c in range(cols):
            if c + 1 < cols:
                links.append(LinkSpec(ids[(r, c)], ids[(r, c + 1)], loss=loss))
            if r + 1 < rows:
                links.append(LinkSpec(ids[(r, c)], ids[(r + 1, c)], loss=loss))
    gateway = next(n for n in nodes if n.node_id == "G1")
    nodes.append(NodeSpec("R1", NodeRole.RESCUE, "Rescue command", 0.97, gateway.y))
    links.append(LinkSpec("G1", "R1", loss=0.0))
    return nodes, links, ids[(0, 0)]


def building12() -> Preset:
    nodes, links, sender = _grid(3, 4, 0.05, (2, 3))
    return Preset("building12", "Collapsed building", "Twelve survivors on a 3x4 grid with a little packet loss on every "
                  "link, one gateway in the far corner and a rescue post outside.", nodes, links, sender=sender)


def collapse20() -> Preset:
    nodes, links, sender = _grid(4, 5, 0.12, (3, 4))
    return Preset("collapse20", "Large collapse", "Twenty survivors on a 4x5 grid with 12% loss per link: plenty of "
                  "redundant paths for the router to choose between.", nodes, links, sender=sender)


def chain6() -> Preset:
    nodes = [NodeSpec(f"C{i}", NodeRole.NORMAL, "Relay", 0.06 + 0.78 * (i - 1) / 5, 0.5) for i in range(1, 7)]
    nodes[-1] = NodeSpec("C6", NodeRole.GATEWAY, "Gateway", 0.84, 0.5)
    links = [LinkSpec(f"C{i}", f"C{i + 1}") for i in range(1, 6)]
    return Preset("chain6", "Six-node chain", "Each node can only hear its immediate neighbours, so a message from "
                  "C1 needs five hops to reach the gateway.", nodes, links, sender="C1")


def blank() -> Preset:
    return Preset("blank", "Blank canvas", "Start empty and add nodes and links yourself.", [], [], sender="")


PRESETS = {p.id: p for p in (demo5(), building12(), collapse20(), chain6(), blank())}


def build_preset(preset_id: str) -> Preset:
    """A fresh copy -- the lab mutates specs (add node, change a link), so
    never hand out the shared instance."""
    factories = {"demo5": demo5, "building12": building12, "collapse20": collapse20, "chain6": chain6, "blank": blank}
    if preset_id not in factories:
        raise KeyError(preset_id)
    return factories[preset_id]()
