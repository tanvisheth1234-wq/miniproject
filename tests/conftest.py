"""Shared test helpers.

Timing-sensitive tests must wait for a *condition*, not for a fixed time:
on a busy machine a fixed sleep is sometimes too short (the test fails) and
always too long on an idle one (the suite is slow).
"""

from __future__ import annotations

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


def wait_until(condition: Callable[[], T], timeout: float = 6.0, step: float = 0.05) -> T:
    """Call ``condition`` until it returns something truthy and return that;
    fail with a clear message after ``timeout`` seconds."""
    deadline = time.monotonic() + timeout
    while True:
        result = condition()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"condition not met within {timeout:.1f} s")
        time.sleep(step)


async def async_wait_until(condition: Callable[[], T | Awaitable[T]], timeout: float = 6.0,
                           step: float = 0.05) -> T:
    """``wait_until`` for asyncio tests: lets the event loop run between checks.
    ``condition`` may be a plain function or a coroutine function."""
    deadline = time.monotonic() + timeout
    while True:
        result = condition()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        if time.monotonic() >= deadline:
            raise AssertionError(f"condition not met within {timeout:.1f} s")
        await asyncio.sleep(step)
