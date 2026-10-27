import pytest

from conftest import async_wait_until, wait_until


def test_wait_until_returns_the_first_truthy_value():
    calls = iter([None, 0, "ready"])
    assert wait_until(lambda: next(calls), timeout=1, step=0) == "ready"


def test_wait_until_fails_clearly_after_the_timeout():
    with pytest.raises(AssertionError, match="not met within"):
        wait_until(lambda: False, timeout=0.05, step=0.01)


@pytest.mark.asyncio
async def test_async_wait_until_accepts_coroutine_conditions():
    state = {"n": 0}

    async def ready():
        state["n"] += 1
        return state["n"] >= 3

    assert await async_wait_until(ready, timeout=1, step=0) is True
