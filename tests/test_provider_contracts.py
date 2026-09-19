from __future__ import annotations

import json

import pandas as pd

from src import fetch_fx_data, fetch_market_data, market_api


class _Response:
    def __init__(self, payload: object, status_code: int = 200):
        self.headers = {"content-type": "application/json"}
        self.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.status_code = status_code
        self.closed = False

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self) -> None:
        self.closed = True


def _config(tmp_path):
    return {
        "api": {
            "market_url": "https://example.test/market",
            "fx_url": "https://example.test/fx",
        },
        "data": {"raw_dir": tmp_path, "currency_pair": "USD_TWD"},
    }


def test_yfinance_normalization_coerces_numeric_values_and_deduplicates_dates() -> None:
    dates = pd.to_datetime(["2026-01-03", "2026-01-02", "2026-01-02"])
    raw = pd.DataFrame(
        {
            "Date": dates,
            "Open": ["101.0", "100.0", "100.5"],
            "High": ["103.0", "102.0", "102.5"],
            "Low": ["99.0", "98.0", "98.5"],
            "Close": ["102.0", "101.0", "101.5"],
            "Volume": ["1,000", "900", "950"],
        }
    )

    normalized = market_api._normalize_yfinance_download(raw, "2330.TW")

    assert len(normalized) == 2
    assert normalized["date"].tolist() == list(pd.to_datetime(["2026-01-02", "2026-01-03"]))
    assert normalized["close"].tolist() == [101.5, 102.0]
    assert normalized["volume"].dtype.kind in "fi"


def test_twse_dataset_rejects_non_record_payload(monkeypatch, tmp_path) -> None:
    class Requests:
        @staticmethod
        def get(url, **kwargs):
            return _Response({"unexpected": [1, 2, 3]})

    monkeypatch.setattr(market_api, "requests", Requests)
    data, source = market_api._fetch_twse_dataset(
        "https://example.test/twse",
        tmp_path / "twse.csv",
        1,
    )

    assert data.empty
    assert source == "unavailable"
    assert not (tmp_path / "twse.csv").exists()


def test_market_fetcher_does_not_replace_cache_with_empty_response(monkeypatch, tmp_path) -> None:
    existing = tmp_path / "market_raw.csv"
    existing.write_text("date,symbol,open,high,low,close,volume\n2026-01-02,2330,1,2,0.5,1.5,100\n", encoding="utf-8")

    class Requests:
        @staticmethod
        def get(url, **kwargs):
            return _Response({"data": []})

    monkeypatch.setattr(fetch_market_data, "requests", Requests)
    assert fetch_market_data.fetch_market_data(_config(tmp_path)) is None
    assert "2026-01-02" in existing.read_text(encoding="utf-8")


def test_fx_fetcher_does_not_replace_cache_with_empty_response(monkeypatch, tmp_path) -> None:
    existing = tmp_path / "fx_raw.csv"
    existing.write_text("date,currency_pair,exchange_rate\n2026-01-02,USD_TWD,32.5\n", encoding="utf-8")

    class Requests:
        @staticmethod
        def get(url, **kwargs):
            return _Response({"records": []})

    monkeypatch.setattr(fetch_fx_data, "requests", Requests)
    assert fetch_fx_data.fetch_fx_data(_config(tmp_path)) is None
    assert "2026-01-02" in existing.read_text(encoding="utf-8")
