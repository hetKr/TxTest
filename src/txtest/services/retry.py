from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from txtest.services.error_mapper import ErrorMapper


@dataclass(slots=True)
class RetryPolicy:
    retries: int = 0
    backoff_seconds: int = 0


async def retry_async(
    operation: Callable[[], Awaitable[Any]],
    policy: RetryPolicy,
    error_mapper: ErrorMapper,
) -> Any:
    attempt = 0
    while True:
        try:
            return await operation()
        except Exception as exc:
            attempt += 1
            if attempt > policy.retries or not error_mapper.is_transient(exc):
                raise
            if policy.backoff_seconds > 0:
                await asyncio.sleep(policy.backoff_seconds)
