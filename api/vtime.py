"""Run an asyncio program in virtual time.

The engine's timers (3 s HELLOs, 10 s neighbour timeout, 4 s ACK timeout,
5 s link-state gossip) are the real, spec'd values. Waiting them out in real
time would make a 200-run, 40-node evaluation take hours -- and worse, it
would mix CPU time into the latency numbers. Here the event loop's clock is
a number we control: whenever every task is asleep, the loop jumps straight
to the next scheduled wake-up instead of waiting for it. ``time.time()`` and
``time.monotonic()`` are pointed at the same clock, so the engine's own
timestamps (``Packet.timestamp``, ACK ages, HELLO windows) agree with it.

Only used for headless simulation runs, always in a worker process or a
test; the live lab runs on the real clock. Sockets are not supported (the
simulator doesn't need any).
"""

from __future__ import annotations

import asyncio
import selectors
import time
from typing import Any, Awaitable, Callable

_EPOCH = 1_700_000_000.0  # an arbitrary but fixed wall-clock start, for reproducibility


class VirtualClock:
    def __init__(self) -> None:
        self.now = 0.0  # seconds elapsed in the simulation

    def wall(self) -> float:
        return _EPOCH + self.now

    def monotonic(self) -> float:
        return 10_000.0 + self.now


class _JumpingSelector(selectors.SelectSelector):
    """Instead of blocking for ``timeout`` seconds, advance the virtual
    clock by that much and return immediately."""

    def __init__(self, clock: VirtualClock) -> None:
        super().__init__()
        self._clock = clock

    def select(self, timeout=None):  # type: ignore[override]
        if timeout is None:
            # nothing ready and nothing scheduled: a real loop would sleep
            # forever, so this is a hang in the simulated program.
            raise RuntimeError("virtual-time loop is idle with no scheduled wake-up (deadlock)")
        if timeout > 0:
            self._clock.now += timeout
        return super().select(0)


def run_virtual(main: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
    """Run ``await main(*args, **kwargs)`` to completion on a virtual clock
    and return its result."""
    clock = VirtualClock()
    loop = asyncio.SelectorEventLoop(_JumpingSelector(clock))
    loop.time = lambda: clock.now  # type: ignore[method-assign]
    real_time, real_monotonic = time.time, time.monotonic
    time.time, time.monotonic = clock.wall, clock.monotonic  # type: ignore[assignment]
    try:
        return loop.run_until_complete(main(*args, **kwargs))
    finally:
        time.time, time.monotonic = real_time, real_monotonic  # type: ignore[assignment]
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        finally:
            loop.close()
