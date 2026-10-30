from __future__ import annotations

import json

import pytest

from src import fetch_twse
from src.fetch_twse import BASE_URL, ENDPOINTS, fetch_twse as fetch, normalize_twse_payloads, parse_number, roc_to_iso

SYMBOLS = ["0050", "2330"]


def _payloads(**overrides):
    payloads = {
        "daily": [
            {"Date": "1151029", "Code": "0050", "ClosingPrice": "107.25", "Change": "-1.4000", "TradeVolume": "86630134", "TradeValue": "9292291798"},
            {"Date": "1151029", "Code": "2330", "ClosingPrice": "2415.00", "Change": "-10.0000", "TradeVolume": "18403916", "TradeValue": "44316626887"},
            {"Date": "1151029", "Code": "1101", "ClosingPrice": "30.00", "Change": "0", "TradeVolume": "1", "TradeValue": "1"},
        ],
        "valuation": [{"Date": "1151029", "Code": "2330", "PEratio": "27.99", "DividendYield": "0.91", "PBratio": "9.74"}],
        "margin": [
            {"股票代號": "0050", "融資今日餘額": "25690", "融資前日餘額": "25184", "融券今日餘額": "339", "融券前日餘額": "348"},
            {"股票代號": "2330", "融資今日餘額": "35343", "融資前日餘額": "35332", "融券今日餘額": "16", "融券前日餘額": ""},
        ],
        "market": [
            {"Date": "1151029", "TAIEX": "46368.33", "Change": "-667.25", "TradeValue": "823812748529"},
            {"Date": "1151001", "TAIEX": "48353.49", "Change": "413.36", "TradeValue": "874046252416"},
        ],
    }
    payloads.update(overrides)
    return payloads


def test_roc_dates_and_numbers():
    assert roc_to_iso("1151029") == "2026-10-29"
    assert parse_number("1,234.5") == 1234.5
    assert parse_number("") is None
    assert parse_number("", blank=0.0) == 0.0
    with pytest.raises(ValueError):
        roc_to_iso("2026-10-29")
    with pytest.raises(ValueError):
        parse_number("12abc")


def test_normalize_keeps_tracked_symbols_and_tolerates_etf_valuation():
    snapshot = normalize_twse_payloads(_payloads(), SYMBOLS)
    assert snapshot["trade_date"] == "2026-10-29"
    assert set(snapshot["daily"]) == set(SYMBOLS)
    assert snapshot["daily"]["2330"]["close"] == 2415.0
    assert "0050" not in snapshot["valuation"]
    assert snapshot["margin"]["2330"]["short_previous"] == 0.0
    assert [m["date"] for m in snapshot["market"]] == ["2026-10-01", "2026-10-29"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"daily": []},
        {"daily": [{"Date": "1151029", "Code": "0050", "ClosingPrice": "107.25"}]},
        {"daily": [{"Date": "1151029", "Code": "0050", "ClosingPrice": ""}, {"Date": "1151029", "Code": "2330", "ClosingPrice": "1"}]},
        {"daily": [{"Date": "1151029", "Code": "0050", "ClosingPrice": "1"}, {"Date": "1151028", "Code": "2330", "ClosingPrice": "1"}]},
        {"valuation": [{"Date": "1151028", "Code": "2330", "PEratio": "1", "DividendYield": "1", "PBratio": "1"}]},
        {"margin": [{"股票代號": "0050", "融資今日餘額": "1"}]},
        {"market": [{"Date": "1151029", "TAIEX": ""}]},
        {"market": [{"Date": "1151029", "TAIEX": "1"}, {"Date": "1151029", "TAIEX": "2"}]},
    ],
)
def test_normalize_rejects_incomplete_or_inconsistent_payloads(overrides):
    with pytest.raises(ValueError):
        normalize_twse_payloads(_payloads(**overrides), SYMBOLS)


class _Response:
    def __init__(self, payload, url):
        self.content = json.dumps(payload).encode()
        self.headers = {"content-type": "application/json"}
        self.status_code = 200
        self.url = url

    def raise_for_status(self):
        pass

    def close(self):
        pass


class _Client:
    def __init__(self, payloads, *, redirect_to=None):
        self.payloads = payloads
        self.redirect_to = redirect_to
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        name = next(n for n, path in ENDPOINTS.items() if url == BASE_URL + path)
        return _Response(self.payloads[name], self.redirect_to or url)


def _config(tmp_path):
    return {"api": {"symbols": SYMBOLS, "timeout_seconds": 5}, "data": {"raw_dir": tmp_path / "raw"}}


def test_fetch_writes_a_snapshot_from_fixed_endpoints(tmp_path):
    client = _Client(_payloads())
    path = fetch(_config(tmp_path), client=client)
    assert path is not None
    assert client.urls == [BASE_URL + p for p in ENDPOINTS.values()]
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    assert snapshot["trade_date"] == "2026-10-29"


def test_fetch_failure_removes_stale_snapshot(tmp_path, capsys):
    stale = tmp_path / "raw" / fetch_twse.SNAPSHOT_FILE
    stale.parent.mkdir(parents=True)
    stale.write_text("{}", encoding="utf-8")
    assert fetch(_config(tmp_path), client=_Client(_payloads(daily=[]))) is None
    assert not stale.exists()
    assert "TWSE OpenAPI fetch failed" in capsys.readouterr().out


def test_fetch_rejects_cross_host_responses(tmp_path):
    client = _Client(_payloads(), redirect_to="https://example.com/v1/x")
    assert fetch(_config(tmp_path), client=client) is None
