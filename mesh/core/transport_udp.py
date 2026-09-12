
from __future__ import annotations

import asyncio
import socket
import struct
from typing import Callable, Optional

from .packet import HEADER_SIZE, Packet, PacketError
from .transport import TransportError

DEFAULT_MULTICAST_GROUP = "239.10.10.1"
DEFAULT_MULTICAST_PORT = 9999


class _MulticastProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_datagram: Callable[[bytes, tuple], None]):
        self._on_datagram = on_datagram

    def datagram_received(self, data: bytes, addr) -> None:
        self._on_datagram(data, addr)


class UdpTcpTransport:
    """Transport implementation per section 6.1 / 13: UDP multicast for
    discovery-style broadcasts, TCP per hop for addressed messages."""

    def __init__(
        self,
        node_id: str,
        host: str = "0.0.0.0",
        tcp_port: int = 9001,
        multicast_group: str = DEFAULT_MULTICAST_GROUP,
        multicast_port: int = DEFAULT_MULTICAST_PORT,
    ):
        self.node_id = node_id
        self.host = host
        self.tcp_port = tcp_port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port

        self._callback: Optional[Callable[[str, bytes], None]] = None
        self._peers: dict[str, tuple[str, int]] = {}

        self._tcp_server: Optional[asyncio.AbstractServer] = None
        self._mc_transport: Optional[asyncio.DatagramTransport] = None

    # -- peer table (stand-in for discovery.py, not yet implemented) -----

    def add_peer(self, node_id: str, host: str, port: int) -> None:
        """Register the (host, tcp_port) address for ``node_id`` so
        ``send()`` can reach it. Will be superseded by discovery.py, which
        will populate this same table from HELLO broadcasts."""
        self._peers[node_id] = (host, port)

    # -- Transport interface ---------------------------------------------

    def on_receive(self, callback: Callable[[str, bytes], None]) -> None:
        self._callback = callback

    async def start(self) -> None:
        self._tcp_server = await asyncio.start_server(
            self._handle_tcp_client, self.host, self.tcp_port
        )
        await self._start_multicast_listener()

    async def stop(self) -> None:
        if self._tcp_server is not None:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
            self._tcp_server = None
        if self._mc_transport is not None:
            self._mc_transport.close()
            self._mc_transport = None

    async def send(self, node_id: str, data: bytes) -> None:
        if node_id not in self._peers:
            raise TransportError(f"no known address for peer {node_id!r}")
        host, port = self._peers[node_id]
        reader, writer = await asyncio.open_connection(host, port)
        try:
            writer.write(data)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def broadcast(self, data: bytes) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        try:
            await loop.run_in_executor(
                None, sock.sendto, data, (self.multicast_group, self.multicast_port)
            )
        finally:
            sock.close()

    # -- internals ---------------------------------------------------------

    async def _handle_tcp_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer_addr = writer.get_extra_info("peername")
        try:
            header = await reader.readexactly(HEADER_SIZE)
            remaining = Packet.remaining_length(header)
            rest = await reader.readexactly(remaining) if remaining else b""
            self._dispatch(header + rest, peer_addr)
        except (asyncio.IncompleteReadError, PacketError, ConnectionError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass

    async def _start_multicast_listener(self) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.bind(("", self.multicast_port))
        mreq = struct.pack("4s4s", socket.inet_aton(self.multicast_group), socket.inet_aton("0.0.0.0"))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        sock.setblocking(False)

        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: _MulticastProtocol(self._on_multicast_datagram),
            sock=sock,
        )
        self._mc_transport = transport

    def _on_multicast_datagram(self, data: bytes, addr) -> None:
        self._dispatch(data, addr)

    def _dispatch(self, data: bytes, addr) -> None:
        if self._callback is None:
            return
        sender_id = self._resolve_sender(data, addr)
        self._callback(sender_id, data)

    @staticmethod
    def _resolve_sender(data: bytes, addr) -> str:
        """Best-effort sender identity: the packet's own src field if it
        parses, else the socket peer address."""
        try:
            return Packet.unpack(data).src
        except PacketError:
            return addr[0] if addr else "unknown"
