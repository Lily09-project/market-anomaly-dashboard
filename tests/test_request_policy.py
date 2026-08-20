from __future__ import annotations

import pytest

from src.request_policy import RequestBudget, RequestBudgetExceeded, request_with_retry


class Response:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_request_with_retry_retries_transient_status_and_uses_backoff() -> None:
    responses = [Response(503), Response(200)]
    sleeps: list[float] = []

    def get(_url: str, **_kwargs):
        return responses.pop(0)

    response, attempts = request_with_retry(
        get,
        "https://example.test",
        timeout=1,
        budget=RequestBudget(max_requests=2),
        sleep=sleeps.append,
    )

    assert response.status_code == 200
    assert attempts == 2
    assert sleeps == [0.25]
    assert response is not None


def test_request_budget_stops_unbounded_retries() -> None:
    budget = RequestBudget(max_requests=1)
    budget.reserve("test")
    with pytest.raises(RequestBudgetExceeded, match="budget exceeded"):
        budget.reserve("test")


def test_request_with_retry_closes_failed_response_before_retry() -> None:
    failed = Response(503)
    calls = [failed, Response(200)]

    def get(_url: str, **_kwargs):
        return calls.pop(0)

    request_with_retry(
        get,
        "https://example.test",
        timeout=1,
        budget=RequestBudget(max_requests=2),
        sleep=lambda _seconds: None,
    )

    assert failed.closed is True
