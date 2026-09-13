"""Live discovery demo: run in two (or more) terminals to watch real UDP
multicast HELLO exchange, neighbour table updates, and death detection --
using the real ``UdpTcpTransport``, not the fake transport the pytest
suite uses. See docs/project-plan.md section 6.3 (discovery task) and
section 14.1 (visible_neighbours range emulation).

Terminal 1:
    python -m mesh.core.demo_discovery --id A --port 9101

Terminal 2:
    python -m mesh.core.demo_discovery --id B --port 9102

Both processes join the same UDP multicast group (default
239.10.10.1:9999) so they hear each other's HELLOs even though each
binds its own TCP port. Stop one with Ctrl+C and watch the other mark it
dead after --neighbour-timeout seconds of silence.

Add --visible to restrict which node IDs a process listens to (section
14.1) -- e.g. a third node C started with --visible B only ever sees B,
never A, even though A's HELLOs physically reach it over the same LAN.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from .discovery import Discovery, NodeRole
from .transport_udp import UdpTcpTransport


def _ts() -> str:
    return time.strftime("%H:%M:%S")


async def run(args: argparse.Namespace) -> None:
    transport = UdpTcpTransport(node_id=args.id, host="0.0.0.0", tcp_port=args.port)
    discovery = Discovery(
        args.id,
        transport,
        role=args.role,
        visible_neighbours=args.visible,
        hello_interval=args.hello_interval,
        neighbour_timeout=args.neighbour_timeout,
    )

    discovery.on_peer_up = lambda node_id, role: print(
        f"[{_ts()}] [{args.id}] neighbour UP   : {node_id} ({role})"
    )
    discovery.on_peer_down = lambda node_id: print(
        f"[{_ts()}] [{args.id}] neighbour DOWN : {node_id}"
    )

    await transport.start()
    await discovery.start()

    visible_note = f", only listening to {args.visible}" if args.visible else ""
    print(
        f"[{args.id}] role={args.role} broadcasting HELLO every {args.hello_interval}s, "
        f"timeout {args.neighbour_timeout}s{visible_note} -- Ctrl+C to stop"
    )

    try:
        while True:
            await asyncio.sleep(2)
            ids = sorted(discovery.neighbours.ids())
            print(f"[{_ts()}] [{args.id}] current neighbours: {ids}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await discovery.stop()
        await transport.stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Live discovery demo over real UDP multicast (section 6.3).")
    parser.add_argument("--id", required=True, help="this node's ID (<=8 ASCII chars)")
    parser.add_argument(
        "--port", type=int, required=True,
        help="TCP port this node binds (discovery itself only uses multicast, but UdpTcpTransport always opens one)",
    )
    parser.add_argument("--role", default=NodeRole.NORMAL, choices=NodeRole.ALL, help="advertised role")
    parser.add_argument("--hello-interval", type=float, default=3.0)
    parser.add_argument("--neighbour-timeout", type=float, default=10.0)
    parser.add_argument(
        "--visible", nargs="*", default=None,
        help="if set, only listen to HELLOs from these node IDs (section 14.1 range emulation)",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
