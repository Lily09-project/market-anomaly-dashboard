from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from src.fetch_finmind import API_URL, fetch_finmind, normalize_finmind_payload


def _record(day: str, symbol: str = "2330", close: float = 100.0) -> dict:
    return {"date": day, "stock_id": symbol, "Trading_Volume": 1000, "open": close - 1, "max": close + 1, "min": close - 2, "close": close}


def _config(tmp_path, symbols=("2330",), minimum=1):
    return {"api": {"provider": "finmind", "symbols": list(symbols), "start_date": "2026-01-01", "end_date": "2026-01-05", "minimum_history_days": minimum, "timeout_seconds": 5}, "data": {"raw_dir": tmp_path}}


class _Response:
    def __init__(self, payload, *, status_code=200, url=API_URL):
        self.content = json.dumps(payload).encode()
        self.headers = {"content-type": "application/json", "content-length": str(len(self.content))}
        self.status_code = status_code
        self.url = url
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


def test_finmind_field_mapping_and_numeric_rows():
    frame = normalize_finmind_payload({"status": 200, "data": [_record("2026-01-02"), _record("2026-01-05", close=105)]}, "2330", "2026-01-01", "2026-01-05")
    assert list(frame.columns) == ["date", "symbol", "open", "high", "low", "close", "volume"]
    assert frame["symbol"].tolist() == ["2330", "2330"]
    assert frame["high"].tolist() == [101.0, 106.0]
    assert frame["volume"].tolist() == [1000, 1000]


def test_finmind_rejects_non_finite_price_values():
    payload = {"status": 200, "data": [{**_record("2026-01-02"), "open": float("inf"), "max": float("inf"), "close": float("inf")}]}
    with pytest.raises(ValueError):
        normalize_finmind_payload(payload, "2330", "2026-01-01", "2026-01-05")


def test_finmind_rejects_dropped_incomplete_source_rows():
    payload = {"status": 200, "data": [_record("2026-01-02"), {**_record("2026-01-05"), "close": None}]}
    with pytest.raises(ValueError, match="incomplete or invalid"):
        normalize_finmind_payload(payload, "2330", "2026-01-01", "2026-01-05")


@pytest.mark.parametrize(("payload", "symbol", "message"), [
    ({"status": 403, "data": []}, "2330", "unsuccessful"),
    ({"status": 200, "data": []}, "2330", "no price records"),
    ({"status": 200, "data": [_record("2026-01-02", "0050")]}, "2330", "unexpected symbol"),
    ({"status": 200, "data": [_record("2025-12-31")]}, "2330", "outside"),
    ({"status": 200, "data": [{**_record("2026-01-02"), "max": 50}]}, "2330", "inconsistent"),
])
def test_finmind_rejects_bad_payloads(payload, symbol, message):
    with pytest.raises(ValueError, match=message):
        normalize_finmind_payload(payload, symbol, "2026-01-01", "2026-01-05")


def test_fetch_finmind_uses_fixed_public_host_no_token_and_writes_atomically(tmp_path):
    seen = []
    dates = [date(2026, 1, 2) + timedelta(days=i) for i in range(2)]

    class Client:
        @staticmethod
        def get(url, **kwargs):
            seen.append((url, kwargs))
            symbol = kwargs["params"]["data_id"]
            return _Response({"status": 200, "data": [_record(d.isoformat(), symbol) for d in dates]})

    path = fetch_finmind(_config(tmp_path, ("2330", "0050"), 2), client=Client)
    assert path == tmp_path / "market_finmind.csv"
    assert len(seen) == 2
    for url, kwargs in seen:
        assert url == API_URL
        assert kwargs["allow_redirects"] is False
        assert kwargs["params"]["dataset"] == "TaiwanStockPrice"
        assert "token" not in kwargs["params"] and "api_token" not in kwargs["params"]
    saved = pd.read_csv(path, dtype={"symbol": "string"})
    assert set(saved["symbol"]) == {"2330", "0050"}


def test_fetch_finmind_does_not_replace_existing_data_on_partial_failure(tmp_path):
    target = tmp_path / "market_finmind.csv"
    target.write_text("previous verified data", encoding="utf-8")
    calls = 0

    class Client:
        @staticmethod
        def get(url, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return _Response({"status": 200, "data": [_record("2026-01-02", "2330")]})
            return _Response({"status": 500, "data": []}, status_code=500)

    assert fetch_finmind(_config(tmp_path, ("2330", "0050"), 1), client=Client) is None
    assert target.read_text(encoding="utf-8") == "previous verified data"


def test_fetch_finmind_rejects_redirect_origin_and_invalid_symbols(tmp_path):
    class RedirectClient:
        @staticmethod
        def get(url, **kwargs):
            return _Response({"status": 200, "data": [_record("2026-01-02")]}, url="https://evil.example/")

    assert fetch_finmind(_config(tmp_path), client=RedirectClient) is None
    assert fetch_finmind(_config(tmp_path, ("2330?token=x",), 1), client=RedirectClient) is None


def test_require_api_stops_instead_of_using_sample(monkeypatch, tmp_path):
    import run_all

    calls = []
    config = {"api": {"provider": "finmind"}, "data": {}}
    monkeypatch.setattr(run_all, "load_config", lambda: config)
    monkeypatch.setattr(run_all, "ensure_project_dirs", lambda _config: None)
    monkeypatch.setattr(run_all, "fetch_finmind", lambda _config: None)
    monkeypatch.setattr(run_all, "generate_sample_data", lambda _config: calls.append("sample"))
    with pytest.raises(RuntimeError, match="refusing to build a sample-data release"):
        run_all.run("api", tmp_path / "out", require_api=True)
    assert calls == []
