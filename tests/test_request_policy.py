from __future__ import annotations

import pytest

from src.request_policy import (
    RequestBudget,
    RequestBudgetExceeded,
    request_with_retry,
    validate_response_origin,
    validate_upstream_url,
)


class Response:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_request_with_retry_retries_transient_status_and_uses_backoff() -> None:
    responses = [Response(503), Response(200)]
    sleeps: list[float] = []
    calls: list[dict[str, object]] = []

    def get(_url: str, **kwargs):
        calls.append(kwargs)
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
    assert all(call["allow_redirects"] is False for call in calls)


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


def test_upstream_url_validation_rejects_insecure_and_non_global_targets() -> None:
    assert validate_upstream_url("https://example.test/data?token=private")
    assert validate_upstream_url("https://openapi.twse.com.tw/data", allowed_hosts={"openapi.twse.com.tw"})

    with pytest.raises(ValueError, match="HTTPS"):
        validate_upstream_url("http://example.test/data")
    with pytest.raises(ValueError, match="credentials"):
        validate_upstream_url("https://user:secret@example.test/data")
    with pytest.raises(ValueError, match="globally routable"):
        validate_upstream_url("https://127.0.0.1/data")
    with pytest.raises(ValueError, match="globally routable"):
        validate_upstream_url("https://2130706433/data")
    with pytest.raises(ValueError, match="publicly routable"):
        validate_upstream_url("https://localhost/data")
    with pytest.raises(ValueError, match="not allowed"):
        validate_upstream_url("https://example.test/data", allowed_hosts={"openapi.twse.com.tw"})


def test_response_origin_validation_rejects_redirects_and_cross_host_responses() -> None:
    class ResponseWithUrl(Response):
        def __init__(self, status_code: int, url: str):
            super().__init__(status_code)
            self.url = url

    with pytest.raises(ValueError, match="redirects"):
        validate_response_origin(ResponseWithUrl(302, "https://evil.invalid"), "https://example.test")
    with pytest.raises(ValueError, match="origin"):
        validate_response_origin(ResponseWithUrl(200, "https://evil.invalid"), "https://example.test")
