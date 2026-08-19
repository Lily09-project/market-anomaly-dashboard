from __future__ import annotations

import json

import pandas as pd

from src import fetch_fx_data, fetch_market_data


class JsonResponse:
    def __init__(self, payload: object):
        self.headers = {"content-type": "application/json"}
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.closed = False

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        yield self._body[: max(1, len(self._body) // 2)]
        yield self._body[max(1, len(self._body) // 2) :]

    def close(self) -> None:
        self.closed = True


def _base_config(tmp_path):
    return {
        "api": {"market_url": "https://example.test/market?api_key=private", "fx_url": "https://example.test/fx"},
        "data": {"raw_dir": tmp_path, "currency_pair": "USD_TWD"},
    }


def test_market_fetcher_streams_and_normalizes_json(monkeypatch, tmp_path) -> None:
    response = JsonResponse(
        {
            "data": [
                {
                    "date": "2026-01-02",
                    "symbol": "2330",
                    "open": "100",
                    "high": "105",
                    "low": "99",
                    "close": "104",
                    "volume": "1,000",
                }
            ]
        }
    )
    calls = {}

    class Requests:
        @staticmethod
        def get(url, **kwargs):
            calls.update(url=url, kwargs=kwargs)
            return response

    monkeypatch.setattr(fetch_market_data, "requests", Requests)
    output = fetch_market_data.fetch_market_data(_base_config(tmp_path))

    assert output == tmp_path / "market_raw.csv"
    assert pd.read_csv(output).iloc[0]["close"] == 104
    assert calls["kwargs"]["stream"] is True
    assert response.closed is True


def test_fx_fetcher_streams_and_normalizes_json(monkeypatch, tmp_path) -> None:
    response = JsonResponse(
        {"records": [{"date": "2026-01-02", "currency_pair": "USD_TWD", "exchange_rate": "32.5"}]}
    )

    class Requests:
        @staticmethod
        def get(url, **kwargs):
            return response

    monkeypatch.setattr(fetch_fx_data, "requests", Requests)
    output = fetch_fx_data.fetch_fx_data(_base_config(tmp_path))

    assert output == tmp_path / "fx_raw.csv"
    assert pd.read_csv(output).iloc[0]["exchange_rate"] == 32.5
    assert response.closed is True


def test_market_fetcher_does_not_print_url_credentials_on_failure(monkeypatch, tmp_path, capsys) -> None:
    class Requests:
        @staticmethod
        def get(url, **kwargs):
            raise RuntimeError("GET https://example.test/market?api_key=private-token failed")

    monkeypatch.setattr(fetch_market_data, "requests", Requests)
    assert fetch_market_data.fetch_market_data(_base_config(tmp_path)) is None

    output = capsys.readouterr().out
    assert "private-token" not in output
    assert "[REDACTED]" in output