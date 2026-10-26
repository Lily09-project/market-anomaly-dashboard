from __future__ import annotations

import hashlib
import json
from datetime import date

import pandas as pd
import pytest

from src.fetch_twse import API_URL, fetch_twse, normalize_twse_payload


FIELDS = ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差", "成交筆數", "註記"]


def _row(day: str, *, no_trade: bool = False) -> list[str]:
    if no_trade:
        return [day, "0", "0", "0", "0", "0", "0", "0", "0", ""]
    return [day, "1,000", "100,000", "99.00", "102.00", "98.00", "101.00", "+2.00", "100", ""]


def _payload(rows: list[list[str]] | None = None, *, stat: str = "OK", fields: list[str] | None = None) -> dict:
    return {"stat": stat, "date": "20260101", "fields": fields or FIELDS, "data": rows if rows is not None else [_row("115/01/02"), _row("115/01/05")]}


def _config(tmp_path, symbols=("2330",), minimum=1, start="2026-01-01", end="2026-01-31"):
    return {
        "api": {"provider": "twse", "symbols": list(symbols), "start_date": start, "end_date": end, "minimum_history_days": minimum, "timeout_seconds": 5},
        "data": {"raw_dir": tmp_path / "raw", "source_metadata_path": tmp_path / "metrics" / "source_metadata.json"},
    }


class _Response:
    def __init__(self, payload, *, status_code=200, url=API_URL):
        self.content = json.dumps(payload, ensure_ascii=False).encode()
        self.headers = {"content-type": "application/json", "content-length": str(len(self.content))}
        self.status_code = status_code
        self.url = url
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def close(self):
        self.closed = True


def test_twse_maps_fields_and_converts_roc_dates_and_commas():
    frame = normalize_twse_payload(_payload(), "2330", date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 1))
    assert list(frame.columns) == ["date", "symbol", "open", "high", "low", "close", "volume"]
    assert frame["date"].tolist() == ["2026-01-02", "2026-01-05"]
    assert frame["symbol"].tolist() == ["2330", "2330"]
    assert frame["volume"].tolist() == [1000.0, 1000.0]
    assert frame["close"].tolist() == [101.0, 101.0]


def test_twse_excludes_only_exact_zero_price_zero_volume_rows():
    frame = normalize_twse_payload(
        _payload([_row("115/01/02"), _row("115/01/05", no_trade=True)]),
        "2330",
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 1, 1),
    )
    assert len(frame) == 1
    assert frame.attrs["source_row_count"] == 2
    assert frame.attrs["excluded_no_trade_rows"] == 1


def test_twse_zero_volume_price_placeholders_are_excluded_without_hiding_traded_rows():
    no_trade = ["115/01/02", "0", "0", "--", "", "-", "--", "0", "0", ""]
    frame = normalize_twse_payload(
        _payload([no_trade]), "2330", date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 1)
    )
    assert frame.empty
    assert frame.attrs["source_row_count"] == 1
    assert frame.attrs["excluded_no_trade_rows"] == 1

    traded = _row("115/01/02")
    traded[3] = "--"
    with pytest.raises(ValueError, match="invalid daily-price records in fields: open"):
        normalize_twse_payload(
            _payload([traded]), "2330", date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 1)
        )


def test_twse_preserves_counts_when_every_row_is_a_zero_trade_row():
    frame = normalize_twse_payload(
        _payload([_row("115/01/02", no_trade=True)]),
        "2330",
        date(2026, 1, 1),
        date(2026, 1, 31),
        date(2026, 1, 1),
    )
    assert frame.empty
    assert frame.attrs["source_row_count"] == 1
    assert frame.attrs["excluded_no_trade_rows"] == 1


@pytest.mark.parametrize(
    ("payload", "symbol", "month", "message"),
    [
        (_payload(stat="查無資料"), "2330", date(2026, 1, 1), "unsuccessful"),
        (_payload(fields=["日期", "收盤價"]), "2330", date(2026, 1, 1), "schema"),
        (_payload([_row("115/02/02")]), "2330", date(2026, 1, 1), "outside the requested month"),
        (_payload([_row("115/01/02")[:-1]]), "2330", date(2026, 1, 1), "incomplete"),
        (_payload([["115/01/02", "1", "1", "NaN", "2", "1", "1", "0", "1", ""]]), "2330", date(2026, 1, 1), "invalid daily-price records in fields: open"),
    ],
)
def test_twse_rejects_untrusted_or_malformed_payloads(payload, symbol, month, message):
    with pytest.raises(ValueError, match=message):
        normalize_twse_payload(payload, symbol, date(2026, 1, 1), date(2026, 1, 31), month)


@pytest.mark.parametrize(
    "row",
    [
        ["115/01/02", "1", "1", "0", "2", "1", "1", "0", "1", ""],
        ["115/01/02", "-1", "1", "99", "102", "98", "101", "0", "1", ""],
        ["115/01/02", "1", "1", "99", "98", "100", "101", "0", "1", ""],
    ],
)
def test_twse_rejects_bad_ohlcv_values(row):
    with pytest.raises(ValueError, match="inconsistent OHLCV"):
        normalize_twse_payload(_payload([row]), "2330", date(2026, 1, 1), date(2026, 1, 31), date(2026, 1, 1))


def test_twse_clips_partial_boundary_months():
    frame = normalize_twse_payload(
        _payload([_row("115/01/02"), _row("115/01/05")]),
        "2330",
        date(2026, 1, 3),
        date(2026, 1, 5),
        date(2026, 1, 1),
    )
    assert frame["date"].tolist() == ["2026-01-05"]


def test_twse_fetches_each_symbol_month_without_credentials_and_records_provenance(tmp_path):
    calls = []

    class Client:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return _Response(_payload())

    path = fetch_twse(_config(tmp_path, ("2330", "0050"), minimum=2), client=Client(), sleep=lambda _seconds: None)
    assert path == tmp_path / "raw" / "market_twse.csv"
    assert len(calls) == 2
    for url, kwargs in calls:
        assert url == API_URL
        assert kwargs["allow_redirects"] is False
        assert kwargs["params"]["response"] == "json"
        assert kwargs["params"]["stockNo"] in {"2330", "0050"}
        assert "token" not in kwargs["params"] and "api_key" not in kwargs["params"]
    metadata = json.loads((tmp_path / "metrics" / "source_metadata.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert metadata["provider"] == "twse"
    assert metadata["data_source"] == "TWSE public daily transaction data"
    assert metadata["is_simulated_data"] is False
    assert metadata["row_count"] == 4
    assert metadata["request_count"] == 2
    assert metadata["data_file_sha256"] == digest


def test_twse_requests_each_month_for_the_full_configured_range(tmp_path):
    calls = []

    class Client:
        def get(self, url, **kwargs):
            calls.append(kwargs["params"])
            date_param = kwargs["params"]["date"]
            month = date_param[4:6]
            day = "115/01/02" if month == "01" else "115/02/02"
            return _Response(_payload([_row(day)]))

    path = fetch_twse(
        _config(tmp_path, ("2330",), minimum=2, start="2026-01-01", end="2026-02-28"),
        client=Client(),
        sleep=lambda _seconds: None,
    )
    assert path is not None
    assert [item["date"] for item in calls] == ["20260101", "20260201"]
    assert len(pd.read_csv(path)) == 2


def test_twse_does_not_replace_existing_data_after_partial_failure(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    target = raw_dir / "market_twse.csv"
    target.write_text("previous valid snapshot\n", encoding="utf-8")
    count = 0

    class Client:
        def get(self, _url, **kwargs):
            nonlocal count
            count += 1
            if kwargs.get("params", {}).get("stockNo") == "0050":
                raise RuntimeError("network unavailable")
            return _Response(_payload())

    assert fetch_twse(_config(tmp_path, ("2330", "0050")), client=Client(), sleep=lambda _seconds: None) is None
    assert target.read_text(encoding="utf-8") == "previous valid snapshot\n"


def test_twse_rejects_redirects_and_invalid_symbols(tmp_path, capsys):
    class RedirectClient:
        def get(self, _url, **_kwargs):
            response = _Response(_payload(), status_code=302, url=API_URL)
            response.headers["Location"] = "https://example.test/continue?token=secret"
            return response

    assert fetch_twse(_config(tmp_path), client=RedirectClient(), sleep=lambda _seconds: None) is None
    message = capsys.readouterr().out
    assert "2330/2026-01" in message
    assert "https://example.test/" in message
    assert "token=secret" not in message
    assert fetch_twse(_config(tmp_path, ("2330?token=secret",)), client=RedirectClient(), sleep=lambda _seconds: None) is None

def test_twse_failure_identifies_month_without_echoing_untrusted_payload(tmp_path, capsys):
    class InvalidClient:
        def get(self, _url, **_kwargs):
            return _Response(_payload([_row("115/02/02")]))

    assert fetch_twse(_config(tmp_path), client=InvalidClient(), sleep=lambda _seconds: None) is None
    message = capsys.readouterr().out
    assert "2330/2026-01" in message
    assert "reason=date_outside_month" in message
    assert "115/02/02" not in message


def test_twse_invalid_record_reports_only_safe_field_code(tmp_path, capsys):
    row = _row("115/01/02")
    row[3] = "raw-upstream-invalid-price"

    class InvalidRecordClient:
        def get(self, _url, **_kwargs):
            return _Response(_payload([row]))

    assert fetch_twse(_config(tmp_path), client=InvalidRecordClient(), sleep=lambda _seconds: None) is None
    message = capsys.readouterr().out
    assert "reason=invalid_records_open" in message
    assert "raw-upstream-invalid-price" not in message


def test_twse_malformed_json_reports_only_a_safe_validation_code(tmp_path, capsys):
    class InvalidJsonClient:
        def get(self, _url, **_kwargs):
            response = _Response(_payload())
            response.content = b'{"stat":"OK","marker":"raw-upstream-marker"'
            response.headers["content-length"] = str(len(response.content))
            return response

    assert fetch_twse(_config(tmp_path), client=InvalidJsonClient(), sleep=lambda _seconds: None) is None
    message = capsys.readouterr().out
    assert "reason=invalid_json" in message
    assert "raw-upstream-marker" not in message
