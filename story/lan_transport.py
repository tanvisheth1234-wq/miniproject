"""A ``Transport`` that moves packets over real TCP sockets between real
processes or machines, driven by a shared topology file.

``UdpTcpTransport`` (mesh/core/transport_udp.py) can't carry a full ``Node``
yet: it never learns a HELLO sender's address, and it reports the packet's
*original* source as the sender instead of the previous hop, which breaks
link-state flooding. This one fixes both for the demo:

- who can hear whom comes from the topology file (section 14.1's
  "range emulation": a flat LAN is made to behave like a multi-hop radio
  mesh by only ever talking to configured neighbours);
- every connection starts with a one-line preamble naming the previous hop,
  followed by the unmodified packet bytes;
- ``broadcast`` is a send to each configured neighbour, so it works on
  networks that block multicast (the plan's "seed list" fallback);
- ``enabled`` is a power switch: when False the device neither sends nor
  hears anything, exactly like a dead radio.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Callable, Optional

from mesh.core.packet import HEADER_SIZE, Packet, PacketError
from mesh.core.transport import TransportError

CONNECT_TIMEOUT = 1.5  # seconds -- a dead laptop must fail fast, not hang


async def _within(awaitable, timeout: float):
    """``asyncio.wait_for`` without its cancellation race.

    On Python < 3.12, ``wait_for`` can swallow a ``CancelledError`` that
    arrives at the instant the inner operation completes. A background loop
    (HELLO, link-state gossip) cancelled by ``Node.stop()`` then carries on
    forever and ``stop()`` never returns. ``asyncio.wait`` has no such
    window: cancellation always propagates.
    """
    task = asyncio.ensure_future(awaitable)
    try:
        done, _pending = await asyncio.wait({task}, timeout=timeout)
        if not done:
            raise asyncio.TimeoutError
        return task.result()
    finally:
        if not task.done():
            task.cancel()
            task.add_done_callback(lambda t: t.cancelled() or t.exception())


class LanTransport:
    def __init__(
        self,
        node_id: str,
        listen_port: int,
        peers: dict[str, tuple[str, int]],
        neighbours: set[str],
        listen_host: str = "0.0.0.0",
    ) -> None:
        self.node_id = node_id
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.peers = peers
        self.neighbours = set(neighbours)
        self.enabled = True

        self._callback: Optional[Callable[[str, bytes], None]] = None
        self._server: Optional[asyncio.AbstractServer] = None

    # -- Transport interface ------------------------------------------------

    def on_receive(self, callback: Callable[[str, bytes], None]) -> None:
        self._callback = callback

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.listen_host, self.listen_port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            # Server.wait_closed() can block forever on Windows (Proactor loop,
            # Python < 3.12) while a client connection is still winding down
            with contextlib.suppress(asyncio.TimeoutError):
                await _within(self._server.wait_closed(), CONNECT_TIMEOUT)
            self._server = None

    async def send(self, node_id: str, data: bytes) -> None:
        if not self.enabled:
            raise TransportError("this device is switched off")
        if node_id not in self.neighbours or node_id not in self.peers:
            raise TransportError(f"{self.node_id!r} has no link to {node_id!r}")
        host, port = self.peers[node_id]
        me = self.node_id.encode("ascii")
        writer = None
        try:
            _reader, writer = await _within(asyncio.open_connection(host, port), CONNECT_TIMEOUT)
            writer.write(bytes([len(me)]) + me + data)
            await _within(writer.drain(), CONNECT_TIMEOUT)
        except (OSError, asyncio.TimeoutError) as exc:
            raise TransportError(f"could not reach {node_id!r}: {exc}") from exc
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(OSError, asyncio.TimeoutError):
                    await _within(writer.wait_closed(), CONNECT_TIMEOUT)

    async def broadcast(self, data: bytes) -> None:
        if not self.enabled:
            return
        await asyncio.gather(*(self._try_send(n, data) for n in sorted(self.neighbours)))

    # -- internals ----------------------------------------------------------

    async def _try_send(self, node_id: str, data: bytes) -> None:
        with contextlib.suppress(TransportError):
            await self.send(node_id, data)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            name_len = (await reader.readexactly(1))[0]
            previous_hop = (await reader.readexactly(name_len)).decode("ascii")
            header = await reader.readexactly(HEADER_SIZE)
            remaining = Packet.remaining_length(header)
            rest = await reader.readexactly(remaining) if remaining else b""
            if self.enabled and self._callback is not None and previous_hop in self.neighbours:
                self._callback(previous_hop, header + rest)
        except (asyncio.IncompleteReadError, PacketError, ConnectionError, UnicodeDecodeError):
            pass
        finally:
            writer.close()
            with contextlib.suppress(OSError, asyncio.TimeoutError):
                await _within(writer.wait_closed(), CONNECT_TIMEOUT)
