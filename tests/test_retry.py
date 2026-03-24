import pytest

from txtest.services.error_mapper import ErrorMapper
from txtest.services.retry import RetryPolicy, retry_async


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure() -> None:
    attempts = {"count": 0}

    async def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise TimeoutError()
        return "ok"

    result = await retry_async(operation, RetryPolicy(retries=1, backoff_seconds=0), ErrorMapper())
    assert result == "ok"
    assert attempts["count"] == 2
