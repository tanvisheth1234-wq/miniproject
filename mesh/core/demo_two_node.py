"""Two-node demo: run once as `receiver`, once as `sender`, in two separate
terminals, to watch packet.py + transport_udp.py move a real message
across a real TCP socket. See docs/project-plan.md section 24.7.

Receiver (terminal 1):
    python -m mesh.core.demo_two_node receiver --id B --port 9002

Sender (terminal 2), after the receiver is listening:
    python -m mesh.core.demo_two_node sender --id A --port 9001 \
        --peer-id B --peer-host 127.0.0.1 --peer-port 9002 \
        --message "trapped on floor 3, need help"

Both processes bind their own TCP port (per the Transport interface's
start()/stop() lifecycle), so pick different --port values when running
both on the same machine. The receiver prints every field of the parsed
52-byte header plus a labelled hex dump for each packet it gets; the
sender prints the same hex dump for what it sent, so the two can be
compared byte-for-byte.
"""

from __future__ import annotations

import argparse
import asyncio

from .packet import HEADER_FIELD_OFFSETS, HEADER_SIZE, Packet, PacketType, Priority, hexdump
from .transport_udp import UdpTcpTransport

_TYPE_NAMES = {0: "HELLO", 1: "LINK_STATE", 2: "DATA", 3: "ACK"}
_PRIORITY_NAMES = {0: "SOS", 1: "NORMAL", 2: "STATUS"}


def _on_data_received(sender_id: str, data: bytes) -> None:
    print(f"\n[recv] {len(data)} bytes from {sender_id!r}")
    try:
        pkt = Packet.unpack(data)
    except Exception as exc:  # malformed packet: report and keep listening
        print(f"  !! failed to parse: {exc}")
        return

    print("  -- parsed header --")
    print(f"  type       : {pkt.type} ({_TYPE_NAMES.get(pkt.type, '?')})")
    print(f"  priority   : {pkt.priority} ({_PRIORITY_NAMES.get(pkt.priority, '?')})")
    print(f"  ttl        : {pkt.ttl}")
    print(f"  flags      : {pkt.flags:#04x}")
    print(f"  hop_count  : {pkt.hop_count}")
    print(f"  msg_id     : {pkt.msg_id}")
    print(f"  src        : {pkt.src!r}")
    print(f"  dst        : {pkt.dst!r}")
    print(f"  timestamp  : {pkt.timestamp}")
    print(f"  path       : {pkt.path}")
    print(f"  payload    : {pkt.payload!r}")
    print("\n  -- labelled hex dump (header) --")
    print(hexdump(data[:HEADER_SIZE], labels=HEADER_FIELD_OFFSETS))


async def run_receiver(args: argparse.Namespace) -> None:
    transport = UdpTcpTransport(node_id=args.id, host="0.0.0.0", tcp_port=args.port)
    transport.on_receive(_on_data_received)
    await transport.start()
    print(f"[{args.id}] listening on tcp://0.0.0.0:{args.port} -- Ctrl+C to stop")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await transport.stop()


async def run_sender(args: argparse.Namespace) -> None:
    transport = UdpTcpTransport(node_id=args.id, host="0.0.0.0", tcp_port=args.port)
    transport.add_peer(args.peer_id, args.peer_host, args.peer_port)
    await transport.start()
    try:
        pkt = Packet(
            type=PacketType.DATA,
            priority=Priority.SOS if args.sos else Priority.NORMAL,
            src=args.id,
            dst=args.peer_id,
            payload=args.message.encode("utf-8"),
        )
        data = pkt.pack()
        print(
            f"[{args.id}] sending {len(data)} bytes to {args.peer_id!r} "
            f"at {args.peer_host}:{args.peer_port}"
        )
        print(hexdump(data[:HEADER_SIZE], labels=HEADER_FIELD_OFFSETS))
        await transport.send(args.peer_id, data)
        print(f"[{args.id}] sent.")
    finally:
        await transport.stop()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Two-node packet.py / transport_udp.py demo (section 24.7)."
    )
    sub = parser.add_subparsers(dest="role", required=True)

    recv = sub.add_parser("receiver", help="listen for incoming packets and print them")
    recv.add_argument("--id", required=True, help="this node's ID (<=8 ASCII chars)")
    recv.add_argument("--port", type=int, default=9001, help="TCP port to listen on")

    send = sub.add_parser("sender", help="send one DATA packet to a peer")
    send.add_argument("--id", required=True, help="this node's ID (<=8 ASCII chars)")
    send.add_argument("--port", type=int, default=9002, help="TCP port this node binds")
    send.add_argument("--peer-id", required=True, help="destination node ID (<=8 ASCII chars)")
    send.add_argument("--peer-host", required=True, help="destination host/IP")
    send.add_argument("--peer-port", type=int, required=True, help="destination TCP port")
    send.add_argument("--message", default="trapped, need help", help="payload text to send")
    send.add_argument("--sos", action="store_true", help="mark the message SOS priority")

    args = parser.parse_args()
    if args.role == "receiver":
        asyncio.run(run_receiver(args))
    else:
        asyncio.run(run_sender(args))


if __name__ == "__main__":
    main()
