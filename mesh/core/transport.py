"""The transport boundary: the mesh engine must never know how bytes
physically move. See docs/project-plan.md section 6.1.

Two implementations exist: ``UdpTcpTransport`` (transport_udp.py, real
sockets) and, in a later phase, ``SimulatedTransport`` (transport_sim.py,
in-memory). Both satisfy this same interface, so routing and reliability
code is written once against ``Transport`` and never against sockets
directly.
"""

from __future__ import annotations

from typing import Callable, Protocol, runtime_checkable


class TransportError(RuntimeError):
    """Raised for transport-level failures (unknown peer, send failure, ...)."""


@runtime_checkable
class Transport(Protocol):
    async def send(self, node_id: str, data: bytes) -> None:
        """Send ``data`` to the single node ``node_id``."""
        ...

    def on_receive(self, callback: Callable[[str, bytes], None]) -> None:
        """Register ``callback(sender_id, data)`` for every inbound message."""
        ...

    async def broadcast(self, data: bytes) -> None:
        """Send ``data`` to every reachable neighbour at once."""
        ...

    async def start(self) -> None:
        """Begin listening / sending. Idempotent-ish: call once before use."""
        ...

    async def stop(self) -> None:
        """Stop listening and release any sockets."""
        ...
