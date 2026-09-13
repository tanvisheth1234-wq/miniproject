"""Simulator runner skeleton: wires N nodes to ``SimulatedTransport`` over
a chosen link topology and runs discovery, no sockets involved.

Spec: docs/project-plan.md section 15. This is deliberately a skeleton --
the full ``Scenario`` model (named topologies, scripted kill/revive
events, injected traffic, the six required scenarios) belongs in
sim/scenarios.py once routing and reliability exist to generate traffic
against. What's here proves the shape works: N ``Node``-equivalents in one
process, each wired to a ``SimulatedTransport``, sharing one
``SimulatedNetwork``.

Run directly:
    python -m sim.runner --nodes 5 --topology chain --loss 0.1 --duration 2
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from mesh.core.discovery import Discovery
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport


def build_chain_topology(
    network: SimulatedNetwork,
    node_ids: list[str],
    loss: float = 0.0,
    latency_ms: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Link each node only to its immediate neighbour in the list:
    N1-N2-N3-...-Nn. Forces multi-hop behaviour -- N1 can't hear N3."""
    for a, b in zip(node_ids, node_ids[1:]):
        network.set_link(a, b, loss=loss, latency_ms=latency_ms)


def build_full_mesh_topology(
    network: SimulatedNetwork,
    node_ids: list[str],
    loss: float = 0.0,
    latency_ms: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Link every node to every other node: everyone hears everyone."""
    for i, a in enumerate(node_ids):
        for b in node_ids[i + 1 :]:
            network.set_link(a, b, loss=loss, latency_ms=latency_ms)


TOPOLOGIES = {
    "chain": build_chain_topology,
    "full_mesh": build_full_mesh_topology,
}


async def run_discovery_sim(
    node_ids: list[str],
    network: SimulatedNetwork,
    hello_interval: float = 0.3,
    neighbour_timeout: float = 1.0,
    duration: float = 2.0,
    visible_neighbours_map: Optional[dict[str, list[str]]] = None,
) -> dict[str, Discovery]:
    """Start a ``Discovery`` per node over the given (pre-linked) network,
    let HELLOs circulate for ``duration`` seconds, then stop everything
    and hand back each node's ``Discovery`` so callers can inspect its
    neighbour table."""
    transports: dict[str, SimulatedTransport] = {}
    discoveries: dict[str, Discovery] = {}

    for node_id in node_ids:
        transport = SimulatedTransport(node_id, network)
        visible = (visible_neighbours_map or {}).get(node_id)
        discoveries[node_id] = Discovery(
            node_id,
            transport,
            hello_interval=hello_interval,
            neighbour_timeout=neighbour_timeout,
            visible_neighbours=visible,
        )
        transports[node_id] = transport

    for transport in transports.values():
        await transport.start()
    for discovery in discoveries.values():
        await discovery.start()

    await asyncio.sleep(duration)

    for discovery in discoveries.values():
        await discovery.stop()
    for transport in transports.values():
        await transport.stop()

    return discoveries


def summarize(discoveries: dict[str, Discovery]) -> dict[str, list[str]]:
    """Node ID -> sorted list of node IDs it discovered as a neighbour."""
    return {node_id: sorted(disc.neighbours.ids()) for node_id, disc in discoveries.items()}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Simulator runner skeleton: run N nodes over SimulatedTransport, report neighbour discovery."
    )
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--topology", choices=sorted(TOPOLOGIES), default="chain")
    parser.add_argument("--loss", type=float, default=0.0, help="per-link drop probability, 0..1")
    parser.add_argument("--latency-ms", type=float, nargs=2, default=(0.0, 0.0), metavar=("MIN", "MAX"))
    parser.add_argument("--duration", type=float, default=2.0, help="seconds to run discovery for")
    parser.add_argument("--hello-interval", type=float, default=0.3)
    parser.add_argument("--neighbour-timeout", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=None, help="RNG seed, for reproducible loss/latency")
    args = parser.parse_args()

    node_ids = [f"N{i}" for i in range(1, args.nodes + 1)]
    network = SimulatedNetwork(seed=args.seed)
    TOPOLOGIES[args.topology](network, node_ids, loss=args.loss, latency_ms=tuple(args.latency_ms))

    discoveries = asyncio.run(
        run_discovery_sim(
            node_ids,
            network,
            hello_interval=args.hello_interval,
            neighbour_timeout=args.neighbour_timeout,
            duration=args.duration,
        )
    )

    print(
        f"topology={args.topology} nodes={args.nodes} loss={args.loss} "
        f"latency_ms={tuple(args.latency_ms)} duration={args.duration}s"
    )
    for node_id, neighbours in summarize(discoveries).items():
        print(f"  {node_id}: neighbours={neighbours}")


if __name__ == "__main__":
    main()
