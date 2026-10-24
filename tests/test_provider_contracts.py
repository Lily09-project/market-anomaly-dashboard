from __future__ import annotations

import json

import pandas as pd

from src import fetch_market_data, fetch_yfinance


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
        "api": {"market_url": "https://example.test/market"},
        "data": {"raw_dir": tmp_path, "start_date": "2026-01-01", "end_date": "2026-02-01"},
    }


def test_yfinance_symbols_use_the_taiwan_suffix() -> None:
    assert fetch_yfinance.to_yfinance_symbol("2330") == "2330.TW"
    assert fetch_yfinance.to_yfinance_symbol(" aapl ") == "AAPL"


def test_yfinance_normalization_coerces_numeric_values_and_deduplicates_dates() -> None:
    raw = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-03", "2026-01-02", "2026-01-02"]),
            "Open": ["101.0", "100.0", "100.5"],
            "High": ["103.0", "102.0", "102.5"],
            "Low": ["99.0", "98.0", "98.5"],
            "Close": ["102.0", "101.0", "101.5"],
            "Volume": ["1,000", "900", "950"],
        }
    ).set_index("Date")
    normalized = fetch_yfinance.normalize_download(raw, "2330.TW", "2330")
    assert normalized["date"].tolist() == ["2026-01-02", "2026-01-03"]
    assert normalized["close"].tolist() == [101.5, 102.0]
    assert set(normalized["symbol"]) == {"2330"}
    assert fetch_yfinance.normalize_download(None, "2330.TW", "2330").empty
    assert fetch_yfinance.normalize_download(pd.DataFrame({"x": [1]}), "2330.TW", "2330").empty


def test_yfinance_multi_index_download_is_split_per_ticker(tmp_path) -> None:
    index = pd.Index(pd.to_datetime(["2026-01-02", "2026-01-05"]), name="Date")
    columns = pd.MultiIndex.from_product([["2330.TW", "0050.TW"], ["Open", "High", "Low", "Close", "Volume"]])
    frame = pd.DataFrame([[1, 2, 0.5, 1.5, 10] * 2, [2, 3, 1.5, 2.5, 20] * 2], index=index, columns=columns)

    class FakeYf:
        calls: list[dict] = []

        @classmethod
        def download(cls, tickers, **kwargs):
            cls.calls.append({"tickers": tickers, **kwargs})
            return frame

    path = fetch_yfinance.fetch_yfinance(_config(tmp_path), ["2330", "0050"], module=FakeYf)
    saved = pd.read_csv(path, dtype={"symbol": "string"})
    assert sorted(saved["symbol"].unique()) == ["0050", "2330"]
    assert FakeYf.calls[0]["tickers"] == ["2330.TW", "0050.TW"]
    assert FakeYf.calls[0]["start"] == "2026-01-01"


def test_yfinance_failures_fall_back(tmp_path, capsys) -> None:
    class Broken:
        @staticmethod
        def download(*args, **kwargs):
            raise RuntimeError("network down token=secret")

    class Empty:
        @staticmethod
        def download(*args, **kwargs):
            return pd.DataFrame()

    assert fetch_yfinance.fetch_yfinance(_config(tmp_path), ["2330"], module=Broken) is None
    assert fetch_yfinance.fetch_yfinance(_config(tmp_path), ["2330"], module=Empty) is None
    assert "falling back" in capsys.readouterr().out


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


def test_market_url_can_come_from_the_environment(monkeypatch, tmp_path) -> None:
    seen: list[str] = []

    class Requests:
        @staticmethod
        def get(url, **kwargs):
            seen.append(url)
            return _Response({"data": []})

    monkeypatch.setattr(fetch_market_data, "requests", Requests)
    monkeypatch.setenv("MARKET_API_URL", "https://example.test/from-env")
    config = _config(tmp_path)
    config["api"]["market_url"] = ""
    assert fetch_market_data.fetch_market_data(config) is None
    assert seen == ["https://example.test/from-env"]
