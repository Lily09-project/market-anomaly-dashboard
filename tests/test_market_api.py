from __future__ import annotations

import sys

import pandas as pd

from src.market_api import (
    TWSE_COMPANY_PROFILE_URL,
    TWSE_GOVERNANCE_URL,
    _fetch_twse_dataset,
    build_twse_stock_universe,
    build_stock_analysis,
    build_watchlist_cards,
    compute_technical_indicators,
    fetch_yfinance_histories,
    fetch_yfinance_history,
    get_stock_universe,
    lookup_twse_company,
    summarize_history,
    to_yfinance_symbol,
)


def test_yfinance_symbol_mapping() -> None:
    assert to_yfinance_symbol("2330") == "2330.TW"
    assert to_yfinance_symbol("00919") == "00919.TW"
    assert to_yfinance_symbol("006208") == "006208.TW"
    assert to_yfinance_symbol("AAPL") == "AAPL"


def test_stock_universe_is_large_enough_for_real_usage() -> None:
    universe = get_stock_universe()
    symbols = {item["symbol"] for item in universe}
    assert len(universe) >= 45
    assert {"2330.TW", "2881.TW", "00919.TW", "006208.TW", "AAPL", "TSLA", "SPY"} <= symbols


def test_build_watchlist_cards_keeps_stock_metadata(monkeypatch) -> None:
    from src import market_api

    requested_periods = []

    def fake_fetch(symbols, period: str = "6mo", interval: str = "1d"):
        requested_periods.append(period)
        result = {}
        for symbol in symbols:
            dates = pd.bdate_range("2026-01-01", periods=30)
            prices = pd.Series(range(100, 130), dtype="float64")
            result[symbol] = (
                pd.DataFrame(
                    {
                        "date": dates,
                        "open": prices,
                        "high": prices + 1,
                        "low": prices - 1,
                        "close": prices,
                        "volume": 1_000_000,
                        "symbol": symbol,
                    }
                ),
                "test",
            )
        return result

    monkeypatch.setattr(market_api, "fetch_yfinance_histories", fake_fetch)
    cards = build_watchlist_cards(["2330.TW"])
    assert cards[0]["display"] == "台積電"
    assert cards[0]["category"] == "台股上市"
    assert requested_periods == ["1y"]


def test_batch_yfinance_download_is_split_by_symbol(monkeypatch) -> None:
    from src import market_api

    download_kwargs = {}

    class BatchYFinance:
        @staticmethod
        def download(symbols, **kwargs):
            download_kwargs.update(kwargs)
            dates = pd.bdate_range("2026-01-01", periods=5, name="Date")
            values = {}
            for offset, symbol in enumerate(symbols):
                base = pd.Series(range(100 + offset, 105 + offset), index=dates, dtype="float64")
                values[(symbol, "Open")] = base
                values[(symbol, "High")] = base + 2
                values[(symbol, "Low")] = base - 2
                values[(symbol, "Close")] = base + 1
                values[(symbol, "Adj Close")] = base + 1
                values[(symbol, "Volume")] = pd.Series(1_000_000, index=dates, dtype="float64")
            frame = pd.DataFrame(values, index=dates)
            frame.columns = pd.MultiIndex.from_tuples(frame.columns)
            return frame

    monkeypatch.setattr(market_api, "yf", BatchYFinance)
    histories = fetch_yfinance_histories(["2330.TW", "2454.TW"], period="1mo")
    assert list(histories) == ["2330.TW", "2454.TW"]
    assert download_kwargs["timeout"] == market_api.YFINANCE_TIMEOUT_SECONDS
    for symbol, (history, source) in histories.items():
        assert source == "yfinance"
        assert len(history) == 5
        assert set(history["symbol"]) == {symbol}
        assert {"date", "open", "high", "low", "close", "volume"} <= set(history.columns)


def test_twse_company_profiles_expand_stock_universe() -> None:
    profiles = pd.DataFrame(
        {
            "公司代號": ["2330", "1101", "9999"],
            "公司簡稱": ["台積電", "台泥", "測試公司"],
            "產業別": ["24", "01", "30"],
        }
    )
    parsed = build_twse_stock_universe(profiles)
    assert {item["symbol"] for item in parsed} == {"2330.TW", "1101.TW", "9999.TW"}
    universe = get_stock_universe(profiles)
    lookup = {item["symbol"]: item for item in universe}
    assert lookup["2330.TW"]["category"] == "半導體業"
    assert lookup["9999.TW"]["display"] == "測試公司"
    assert TWSE_COMPANY_PROFILE_URL.endswith("t187ap03_L")


def test_yfinance_history_fallback_or_live_shape() -> None:
    history, source = fetch_yfinance_history("2330.TW", period="1mo")
    assert source in {"yfinance", "sample"}
    assert {"date", "open", "high", "low", "close", "volume", "symbol"} <= set(history.columns)
    assert len(history) > 0
    summary = summarize_history(history)
    assert "latest_close" in summary


def test_yfinance_download_noise_is_suppressed(monkeypatch, capsys) -> None:
    from src import market_api

    class NoisyYFinance:
        @staticmethod
        def download(*args, **kwargs):
            print("simulated yfinance connection failure", file=sys.stderr)
            return pd.DataFrame()

    monkeypatch.setattr(market_api, "yf", NoisyYFinance)
    history, source = market_api.fetch_yfinance_history("2330.TW", period="1mo")
    captured = capsys.readouterr()
    assert source == "sample"
    assert len(history) > 0
    assert "simulated yfinance connection failure" not in captured.err


def test_yfinance_none_response_uses_sample_fallback(monkeypatch) -> None:
    from src import market_api

    class NoneYFinance:
        @staticmethod
        def download(*args, **kwargs):
            return None

    monkeypatch.setattr(market_api, "yf", NoneYFinance)
    history, source = market_api.fetch_yfinance_history("2330.TW", period="1mo")

    assert source == "sample"
    assert not history.empty
    assert {"date", "open", "high", "low", "close", "volume", "symbol"} <= set(history.columns)


def test_twse_dataset_unwraps_list_payload(monkeypatch, tmp_path) -> None:
    from src import market_api

    class WrappedResponse:
        headers = {"content-type": "application/json"}

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"公司代號": "2330", "公司簡稱": "台積電"}]}

    class WrappedRequests:
        @staticmethod
        def get(*args, **kwargs):
            return WrappedResponse()

    monkeypatch.setattr(market_api, "requests", WrappedRequests)
    data, source = _fetch_twse_dataset("https://example.test", tmp_path / "twse.csv", 1)

    assert source == "twse_openapi"
    assert data.to_dict(orient="records") == [{"公司代號": "2330", "公司簡稱": "台積電"}]


def test_technical_indicators_are_generated() -> None:
    history, _ = fetch_yfinance_history("2330.TW", period="1mo")
    data = compute_technical_indicators(history)
    assert {"ma5", "ma20", "ma60", "rsi14", "volume_ratio_20", "volatility_20"} <= set(data.columns)
    assert data["rsi14"].between(0, 100).all()


def test_stock_analysis_summary_is_generated() -> None:
    history, _ = fetch_yfinance_history("2330.TW", period="3mo")
    analysis = build_stock_analysis(history)
    assert {"latest", "technical", "signals", "performance", "health", "data"} <= set(analysis)
    assert len(analysis["signals"]) == 4
    assert len(analysis["health"]["dimensions"]) == 5
    assert 0 <= analysis["technical"]["range_position"] <= 100
    assert 0 <= analysis["health"]["overall_score"] <= 5


def test_twse_governance_lookup_aliases() -> None:
    data = pd.DataFrame(
        {
            "公司代號": ["2330"],
            "公司簡稱": ["台積電"],
            "公司治理評鑑等級": ["前 5%"],
        }
    )
    info = lookup_twse_company("2330.TW", data)
    assert info["twse_name"] == "台積電"
    assert info["governance_level"] == "前 5%"
    assert TWSE_GOVERNANCE_URL.endswith("t187ap46_L_20")
