"""Three-node relay demo: A -> B -> C in three terminals, to watch
relay.py forward a packet it isn't the destination of. See
docs/project-plan.md section 17 (week 2 milestone: "single-hop relay
A->B->C").

Receiver (terminal 1) -- the final destination:
    python -m mesh.core.demo_relay receiver --id C --port 9003

Relay (terminal 2) -- forwards anything not addressed to itself:
    python -m mesh.core.demo_relay relay --id B --port 9002 \
        --dst-id C --next-hop-id C --next-hop-host 127.0.0.1 --next-hop-port 9003

Sender (terminal 3), after the other two are listening:
    python -m mesh.core.demo_relay sender --id A --port 9001 \
        --first-hop-id B --first-hop-host 127.0.0.1 --first-hop-port 9002 \
        --dst C --message "trapped on floor 3, need help"

A never talks to C directly -- the packet's wire-level next hop is B,
while the packet's dst field (and therefore final delivery) is C. The
receiver prints the accumulated path so "relayed via 1 node" is visible.
"""

from __future__ import annotations

import argparse
import asyncio

from .packet import HEADER_FIELD_OFFSETS, HEADER_SIZE, Packet, PacketType, Priority, hexdump
from .relay import RelayNode
from .transport_udp import UdpTcpTransport

_TYPE_NAMES = {0: "HELLO", 1: "LINK_STATE", 2: "DATA", 3: "ACK"}
_PRIORITY_NAMES = {0: "SOS", 1: "NORMAL", 2: "STATUS"}


def _print_packet(label: str, pkt: Packet, data: bytes) -> None:
    print(f"\n{label} {len(data)} bytes")
    print(f"  type       : {pkt.type} ({_TYPE_NAMES.get(pkt.type, '?')})")
    print(f"  priority   : {pkt.priority} ({_PRIORITY_NAMES.get(pkt.priority, '?')})")
    print(f"  ttl        : {pkt.ttl}")
    print(f"  hop_count  : {pkt.hop_count}")
    print(f"  msg_id     : {pkt.msg_id}")
    print(f"  src        : {pkt.src!r}")
    print(f"  dst        : {pkt.dst!r}")
    print(f"  path       : {pkt.path}  (origin + {pkt.hop_count} relay hop(s))")
    print(f"  payload    : {pkt.payload!r}")
    print(hexdump(data[:HEADER_SIZE], labels=HEADER_FIELD_OFFSETS))


async def run_receiver(args: argparse.Namespace) -> None:
    transport = UdpTcpTransport(node_id=args.id, host="0.0.0.0", tcp_port=args.port)
    relay = RelayNode(args.id, transport)
    relay.on_deliver = lambda pkt: _print_packet(f"[{args.id}] delivered", pkt, pkt.pack())
    relay.register()
    await transport.start()
    print(f"[{args.id}] listening on tcp://0.0.0.0:{args.port} -- Ctrl+C to stop")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await transport.stop()


async def run_relay(args: argparse.Namespace) -> None:
    transport = UdpTcpTransport(node_id=args.id, host="0.0.0.0", tcp_port=args.port)
    transport.add_peer(args.next_hop_id, args.next_hop_host, args.next_hop_port)

    relay = RelayNode(args.id, transport)
    relay.set_next_hop(args.dst_id, args.next_hop_id)
    relay.on_forward = lambda pkt, next_hop: print(
        f"[{args.id}] forwarding {pkt.msg_id} toward {pkt.dst!r} via next hop {next_hop!r} "
        f"(ttl {pkt.ttl}, hop_count {pkt.hop_count})"
    )
    relay.on_drop = lambda pkt, reason: print(f"[{args.id}] dropped {pkt.msg_id}: {reason}")
    relay.register()

    await transport.start()
    print(
        f"[{args.id}] relaying on tcp://0.0.0.0:{args.port}: "
        f"messages for {args.dst_id!r} -> next hop {args.next_hop_id!r} -- Ctrl+C to stop"
    )
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await transport.stop()


async def run_sender(args: argparse.Namespace) -> None:
    transport = UdpTcpTransport(node_id=args.id, host="0.0.0.0", tcp_port=args.port)
    transport.add_peer(args.first_hop_id, args.first_hop_host, args.first_hop_port)
    await transport.start()
    try:
        pkt = Packet(
            type=PacketType.DATA,
            priority=Priority.SOS if args.sos else Priority.NORMAL,
            src=args.id,
            dst=args.dst,
            path=[args.id],
            payload=args.message.encode("utf-8"),
        )
        data = pkt.pack()
        _print_packet(
            f"[{args.id}] sending to final dst {args.dst!r} via first hop {args.first_hop_id!r},",
            pkt,
            data,
        )
        await transport.send(args.first_hop_id, data)
        print(f"[{args.id}] sent.")
    finally:
        await transport.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Three-node relay demo (A -> B -> C), section 17 week 2 milestone."
    )
    sub = parser.add_subparsers(dest="role", required=True)

    recv = sub.add_parser("receiver", help="final destination: listen and print delivered packets")
    recv.add_argument("--id", required=True, help="this node's ID (<=8 ASCII chars)")
    recv.add_argument("--port", type=int, required=True, help="TCP port to listen on")

    relay = sub.add_parser("relay", help="forward anything not addressed to this node")
    relay.add_argument("--id", required=True, help="this node's ID (<=8 ASCII chars)")
    relay.add_argument("--port", type=int, required=True, help="TCP port to listen on")
    relay.add_argument(
        "--dst-id", required=True, help="final message destination this route applies to"
    )
    relay.add_argument(
        "--next-hop-id", required=True, help="immediate peer to forward toward (may differ from --dst-id)"
    )
    relay.add_argument("--next-hop-host", required=True, help="next hop's host/IP")
    relay.add_argument("--next-hop-port", type=int, required=True, help="next hop's TCP port")

    send = sub.add_parser("sender", help="send one DATA packet toward a (possibly multi-hop) destination")
    send.add_argument("--id", required=True, help="this node's ID (<=8 ASCII chars)")
    send.add_argument("--port", type=int, required=True, help="TCP port this node binds")
    send.add_argument("--first-hop-id", required=True, help="node ID of the first hop (e.g. the relay)")
    send.add_argument("--first-hop-host", required=True, help="first hop's host/IP")
    send.add_argument("--first-hop-port", type=int, required=True, help="first hop's TCP port")
    send.add_argument("--dst", required=True, help="final destination node ID (<=8 ASCII chars)")
    send.add_argument("--message", default="trapped, need help", help="payload text to send")
    send.add_argument("--sos", action="store_true", help="mark the message SOS priority")

    args = parser.parse_args()
    if args.role == "receiver":
        asyncio.run(run_receiver(args))
    elif args.role == "relay":
        asyncio.run(run_relay(args))
    else:
        asyncio.run(run_sender(args))


if __name__ == "__main__":
    main()
