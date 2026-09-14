"""Live demo of node.py: discovery-driven auto-routing, no manual
--next-hop-id anywhere. Runs entirely over SimulatedTransport in one
process (see the honest-statement caveat in node.py's docstring: this
only works end-to-end in the simulator today, since SimulatedTransport
doesn't need a peer's real address the way UdpTcpTransport does).

Run directly:
    python -m mesh.core.demo_node_sim
"""

from __future__ import annotations

import asyncio

from .node import Node
from .packet import HEADER_FIELD_OFFSETS, HEADER_SIZE, Packet, PacketType, Priority, hexdump
from .transport_sim import SimulatedNetwork, SimulatedTransport


async def main() -> None:
    network = SimulatedNetwork(seed=1)
    network.set_link("A", "B", latency_ms=(5, 15))
    network.set_link("B", "C", latency_ms=(5, 15))
    # note: A and C are NOT linked -- C is only reachable via B

    nodes = {
        node_id: Node(node_id, SimulatedTransport(node_id, network), hello_interval=0.2, neighbour_timeout=1.0)
        for node_id in ("A", "B", "C")
    }

    nodes["B"].on_forward = lambda pkt, next_hop: print(
        f"[B] auto-relayed {pkt.msg_id} toward {pkt.dst!r} via {next_hop!r} "
        f"(route learned from discovery, nobody typed --next-hop-id)"
    )
    delivered = []
    nodes["C"].on_deliver = lambda pkt: delivered.append(pkt)

    for node in nodes.values():
        await node.start()

    print("waiting for discovery to converge...")
    await asyncio.sleep(0.6)

    for node_id, node in nodes.items():
        print(f"  {node_id} neighbours: {sorted(node.neighbours.ids())}  relay routes: {node.relay._next_hop}")

    print("\nA sends a message for C, addressed to first hop B (A never discovered C directly):")
    pkt = Packet(
        type=PacketType.DATA,
        priority=Priority.SOS,
        src="A",
        dst="C",
        path=["A"],
        payload=b"trapped, need help",
    )
    await nodes["A"].transport.send("B", pkt.pack())
    await asyncio.sleep(0.1)

    for node in nodes.values():
        await node.stop()

    print(f"\ndelivered at C: {len(delivered)} message(s)")
    if delivered:
        final = delivered[0]
        print(f"  path={final.path}  hop_count={final.hop_count}  ttl={final.ttl}")
        print(hexdump(final.pack()[:HEADER_SIZE], labels=HEADER_FIELD_OFFSETS))


if __name__ == "__main__":
    asyncio.run(main())
