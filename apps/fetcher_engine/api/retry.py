from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar


T = TypeVar("T")


@dataclass(slots=True)
class RetryOutcome:
    attempts: int = 1
    retries: int = 0


def is_retryable_exception(exc: Exception) -> bool:
    retryable_types = (
        TimeoutError,
        ConnectionError,
        OSError,
    )
    if isinstance(exc, retryable_types):
        return True
    message = str(exc).lower()
    return any(
        keyword in message
        for keyword in (
            "timeout",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "network",
            "503",
            "502",
            "504",
            "429",
        )
    )


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 0,
    backoff_seconds: float = 0.0,
    should_retry: Callable[[Exception], bool] | None = None,
) -> tuple[T, RetryOutcome]:
    outcome = RetryOutcome()
    predicate = should_retry or is_retryable_exception
    attempt = 0
    while True:
        attempt += 1
        try:
            result = await operation()
            outcome.attempts = attempt
            outcome.retries = max(0, attempt - 1)
            return result, outcome
        except Exception as exc:
            if attempt > max_retries or not predicate(exc):
                outcome.attempts = attempt
                outcome.retries = max(0, attempt - 1)
                raise
            await asyncio.sleep(max(backoff_seconds, 0.0) * attempt)
