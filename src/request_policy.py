from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit


DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_BACKOFF_SECONDS = 0.25
RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})


class RequestBudgetExceeded(RuntimeError):
    """Raised when a data provider would exceed the configured request budget."""


def validate_upstream_url(
    url: str,
    *,
    allowed_hosts: Collection[str] | None = None,
) -> str:
    """Validate an HTTPS upstream URL before making an outbound request."""

    try:
        parsed = urlsplit(str(url))
        hostname = parsed.hostname
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("Upstream URL is malformed.") from exc
    if parsed.scheme != "https" or not hostname:
        raise ValueError("Upstream URL must use HTTPS and include a hostname.")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Upstream URL must not include credentials or fragments.")
    if port not in (None, 443):
        raise ValueError("Upstream URL must use the default HTTPS port.")

    normalized_host = hostname.rstrip(".").lower()
    if normalized_host in {"localhost", "localhost.localdomain"} or normalized_host.endswith(
        (".localhost", ".local")
    ):
        raise ValueError("Upstream host must be publicly routable.")
    if allowed_hosts is not None:
        normalized_allowed = {str(host).rstrip(".").lower() for host in allowed_hosts}
        if normalized_host not in normalized_allowed:
            raise ValueError(f"Upstream host is not allowed: {normalized_host}.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            address = ipaddress.ip_address(socket.inet_aton(hostname))
        except (OSError, ValueError):
            address = None
    if address is not None and not address.is_global:
        raise ValueError("Upstream IP address must be globally routable.")
    return str(url)


def validate_response_origin(
    response: Any,
    requested_url: str,
    *,
    allowed_hosts: Collection[str] | None = None,
) -> None:
    """Reject redirects or a response whose origin differs from the request."""

    status_code = getattr(response, "status_code", None)
    if status_code is not None and 300 <= int(status_code) < 400:
        raise ValueError("Upstream redirects are not allowed.")
    requested = validate_upstream_url(requested_url, allowed_hosts=allowed_hosts)
    response_url = str(getattr(response, "url", "") or "")
    if not response_url:
        return
    response_parsed = urlsplit(response_url)
    requested_parsed = urlsplit(requested)
    validate_upstream_url(response_url, allowed_hosts=allowed_hosts)
    if (
        response_parsed.hostname.rstrip(".").lower()
        != requested_parsed.hostname.rstrip(".").lower()
    ):
        raise ValueError("Upstream response origin differs from the requested host.")


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

    Redirects are disabled; callers validate the response origin before parsing.
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
            response = request_get(url, timeout=timeout, stream=True, allow_redirects=False)
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
