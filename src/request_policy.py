from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_BACKOFF_SECONDS = 0.25
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class RequestBudgetExceeded(RuntimeError):
    """Raised when a data provider would exceed the configured request budget."""


@dataclass
class RequestBudget:
    """Small per-operation budget that prevents unbounded provider calls."""

    max_requests: int = 8
    used_requests: int = 0

    def reserve(self, provider: str = "provider", count: int = 1) -> None:
        if count < 1:
            raise ValueError("count must be positive")
        if self.used_requests + count > self.max_requests:
            raise RequestBudgetExceeded(
                f"{provider} request budget exceeded ({self.max_requests})."
            )
        self.used_requests += count

    @property
    def remaining(self) -> int:
        return max(0, self.max_requests - self.used_requests)


def request_with_retry(
    request_get: Callable[..., Any],
    url: str,
    *,
    timeout: float,
    budget: RequestBudget | None = None,
    provider: str = "http",
    attempts: int = DEFAULT_RETRY_ATTEMPTS,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[Any, int]:
    """Run a bounded GET with retryable HTTP status handling.

    The response is returned open so the caller can stream and close it after
    parsing. Network failures are re-raised after the final attempt.
    """
    attempts = max(1, min(int(attempts), 3))
    backoff_seconds = max(0.0, float(backoff_seconds))
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        if budget is not None:
            budget.reserve(provider)
        response = None
        try:
            response = request_get(url, timeout=timeout, stream=True)
            status_code = getattr(response, "status_code", None)
            if status_code in RETRYABLE_STATUS_CODES and attempt < attempts:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
                sleep(backoff_seconds * (2 ** (attempt - 1)))
                continue
            return response, attempt
        except Exception as exc:
            last_error = exc
            close = getattr(response, "close", None)
            if callable(close):
                close()
            if attempt >= attempts:
                raise
            sleep(backoff_seconds * (2 ** (attempt - 1)))
    if last_error is not None:
        raise last_error
    raise RuntimeError("request retry loop ended unexpectedly")
