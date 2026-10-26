"""Fetch real TWSE historical daily prices through its public JSON query.

The official stock-day endpoint returns one symbol and one month per request.
Requests use a fixed HTTPS host and never send credentials or accept caller URLs.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import pandas as pd

try:
    import requests
except Exception:
    requests = None

from src.fetch_market_data import normalize_market_columns
from src.request_policy import RequestBudget, request_with_retry, validate_response_origin, validate_upstream_url
from src.utils import atomic_write_dataframe, clean_numeric, ensure_parent, normalize_http_timeout, parse_date, read_http_response_bytes, safe_exception_message, write_json

API_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
API_HOSTS = {"www.twse.com.tw"}
SYMBOL_PATTERN = re.compile(r"^[0-9]{4,6}$")
MAX_SYMBOLS = 8
MAX_HISTORY_MONTHS = 120
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MIN_REQUEST_INTERVAL_SECONDS = 0.5
REQUIRED_FIELDS = {"日期", "成交股數", "開盤價", "最高價", "最低價", "收盤價"}

_VALIDATION_REASON_BY_MESSAGE = {
    "TWSE returned an unsuccessful response.": "unsuccessful_status",
    "TWSE returned an invalid field list.": "invalid_fields",
    "TWSE returned an incomplete daily-price schema.": "incomplete_schema",
    "TWSE returned an invalid data list.": "invalid_data_list",
    "TWSE returned more rows than a calendar month can contain.": "too_many_rows",
    "TWSE returned incomplete daily-price rows.": "incomplete_rows",
    "TWSE returned incomplete or invalid daily-price records.": "invalid_records",
    "TWSE returned an invalid trading date.": "invalid_trading_date",
    "TWSE returned a date outside the requested month.": "date_outside_month",
    "TWSE returned data for an unexpected symbol.": "unexpected_symbol",
    "TWSE returned invalid numeric price fields.": "invalid_numeric_fields",
    "TWSE returned non-finite numeric price fields.": "non_finite_fields",
    "TWSE returned inconsistent OHLCV values.": "inconsistent_ohlcv",
    "TWSE returned duplicate symbol/date records.": "duplicate_records",
}


def _safe_validation_reason(error: BaseException) -> str:
    """Return only a stable code; never include upstream-controlled response text."""
    if isinstance(error, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(error, UnicodeError):
        return "invalid_encoding"
    message = str(error)
    field_prefix = "TWSE returned invalid daily-price records in fields: "
    if message.startswith(field_prefix) and message.endswith("."):
        fields = message[len(field_prefix):-1].split(",")
        allowed_fields = {"date", "open", "high", "low", "close", "volume"}
        if fields and all(field in allowed_fields for field in fields):
            return "invalid_records_" + "_".join(fields)
    if message.startswith("HTTP response exceeds "):
        return "response_too_large"
    if message.startswith("Market data missing columns:"):
        return "missing_columns"
    return _VALIDATION_REASON_BY_MESSAGE.get(message, "invalid_payload")


def _invalid_normalized_fields(raw: pd.DataFrame) -> list[str]:
    """Classify dropped records by field without exposing response values."""
    checks = [
        ("date", "日期", parse_date),
        ("open", "開盤價", clean_numeric),
        ("high", "最高價", clean_numeric),
        ("low", "最低價", clean_numeric),
        ("close", "收盤價", clean_numeric),
        ("volume", "成交股數", clean_numeric),
    ]
    return [
        name
        for name, source, parser in checks
        if raw[source].map(parser).isna().any()
    ]


def _taipei_today() -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


def _validate_date(value: Any, name: str) -> date:
    text = str(value or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"{name} must use YYYY-MM-DD.")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{name} must use a valid YYYY-MM-DD date.") from exc


def _month_starts(start: date, end: date) -> list[date]:
    count = (end.year - start.year) * 12 + end.month - start.month + 1
    if count < 1:
        raise ValueError("The requested market-data date range is reversed.")
    if count > MAX_HISTORY_MONTHS:
        raise ValueError(f"The requested range exceeds {MAX_HISTORY_MONTHS} months.")
    return [
        date(start.year + (start.month - 1 + offset) // 12, (start.month - 1 + offset) % 12 + 1, 1)
        for offset in range(count)
    ]


def _safe_redirect_target(response: Any) -> str:
    """Describe a redirect without logging its query string or credentials."""
    headers = getattr(response, "headers", {}) or {}
    location = headers.get("location") or headers.get("Location")
    if not location:
        return "unknown destination"
    try:
        parsed = urlsplit(urljoin(API_URL, str(location)))
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.port not in (None, 443) or not host:
            return "non-HTTPS destination"
        if host not in API_HOSTS:
            return f"https://{host}/"
        return f"https://{host}{parsed.path[:120]}"
    except (TypeError, ValueError):
        return "invalid destination"


def _empty_frame() -> pd.DataFrame:
    frame = pd.DataFrame(columns=["date", "symbol", "open", "high", "low", "close", "volume"])
    frame.attrs["source_row_count"] = 0
    frame.attrs["excluded_no_trade_rows"] = 0
    return frame


def normalize_twse_payload(
    payload: Any,
    symbol: str,
    start_date: date,
    end_date: date,
    requested_month: date,
) -> pd.DataFrame:
    """Validate and normalize one TWSE Stock Day monthly JSON response."""
    if not isinstance(payload, dict) or payload.get("stat") != "OK":
        raise ValueError("TWSE returned an unsuccessful response.")
    fields = payload.get("fields")
    records = payload.get("data")
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        raise ValueError("TWSE returned an invalid field list.")
    if not REQUIRED_FIELDS.issubset(fields):
        raise ValueError("TWSE returned an incomplete daily-price schema.")
    if not isinstance(records, list):
        raise ValueError("TWSE returned an invalid data list.")
    if len(records) > 40:
        raise ValueError("TWSE returned more rows than a calendar month can contain.")
    if not records:
        return _empty_frame()
    if any(not isinstance(row, list) or len(row) != len(fields) for row in records):
        raise ValueError("TWSE returned incomplete daily-price rows.")

    raw = pd.DataFrame(records, columns=fields)
    raw["symbol"] = symbol
    frame = normalize_market_columns(raw)
    if len(frame) != len(records) or frame.empty:
        invalid_fields = _invalid_normalized_fields(raw)
        if invalid_fields:
            raise ValueError(
                "TWSE returned invalid daily-price records in fields: "
                + ",".join(invalid_fields)
                + "."
            )
        raise ValueError("TWSE returned incomplete or invalid daily-price records.")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.isna().any():
        raise ValueError("TWSE returned an invalid trading date.")
    month_first = requested_month.replace(day=1)
    month_last = date(
        requested_month.year + (requested_month.month == 12),
        1 if requested_month.month == 12 else requested_month.month + 1,
        1,
    ) - timedelta(days=1)
    if (dates.dt.date < month_first).any() or (dates.dt.date > month_last).any():
        raise ValueError("TWSE returned a date outside the requested month.")

    frame["date"] = dates.dt.strftime("%Y-%m-%d")
    if set(frame["symbol"].astype(str)) != {symbol}:
        raise ValueError("TWSE returned data for an unexpected symbol.")
    in_range = frame["date"].between(start_date.isoformat(), end_date.isoformat())
    frame = frame.loc[in_range].copy()
    if frame.empty:
        return _empty_frame()

    numeric = ["open", "high", "low", "close", "volume"]
    if frame[numeric].isna().any().any():
        raise ValueError("TWSE returned invalid numeric price fields.")
    finite = frame[numeric].apply(lambda column: column.map(math.isfinite))
    if not finite.all().all():
        raise ValueError("TWSE returned non-finite numeric price fields.")

    ohlc = ["open", "high", "low", "close"]
    no_trade = frame[ohlc].eq(0).all(axis=1) & frame["volume"].eq(0)
    bad_price = (frame[ohlc] <= 0).any(axis=1) & ~no_trade
    bad_volume = frame["volume"] < 0
    bad_range = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    if (bad_price | bad_volume | bad_range).any():
        raise ValueError("TWSE returned inconsistent OHLCV values.")
    if frame.duplicated(["date", "symbol"], keep=False).any():
        raise ValueError("TWSE returned duplicate symbol/date records.")

    source_row_count = len(frame)
    excluded_no_trade_rows = int(no_trade.sum())
    frame = frame.loc[~no_trade].copy()
    if frame.empty:
        empty = _empty_frame()
        empty.attrs["source_row_count"] = source_row_count
        empty.attrs["excluded_no_trade_rows"] = excluded_no_trade_rows
        return empty
    frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    frame.attrs["source_row_count"] = source_row_count
    frame.attrs["excluded_no_trade_rows"] = excluded_no_trade_rows
    return frame


def fetch_twse(
    config: dict[str, Any] | None = None,
    *,
    client: Any = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Path | None:
    """Fetch configured symbols month by month; never replace data on partial failure."""
    cfg = config or {}
    api = cfg.get("api", {})
    symbols = [str(item).strip() for item in api.get("symbols", [])]
    try:
        start = _validate_date(api.get("start_date", "2021-01-01"), "start_date")
        end = _validate_date(api.get("end_date") or _taipei_today().isoformat(), "end_date")
        if not symbols or len(symbols) > MAX_SYMBOLS or len(set(symbols)) != len(symbols):
            raise ValueError("Configured symbol list is empty, duplicated, or too large.")
        if any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in symbols):
            raise ValueError("Only numeric Taiwan stock symbols are allowed.")
        today = _taipei_today()
        if start > end or end > today:
            raise ValueError("Configured market-data dates are reversed or in the future.")
        months = _month_starts(start, end)
        validate_upstream_url(API_URL, allowed_hosts=API_HOSTS)
        http = client or requests
        if http is None:
            raise RuntimeError("requests is not installed.")
        timeout = normalize_http_timeout(api.get("timeout_seconds"), default=20.0)
        budget = RequestBudget(max_requests=len(symbols) * len(months) * 2)
        frames: list[pd.DataFrame] = []
        source_row_count = 0
        excluded_no_trade_rows = 0
        request_count = 0

        for symbol in symbols:
            for month in months:
                if request_count:
                    sleep(MIN_REQUEST_INTERVAL_SECONDS)
                params = {
                    "date": f"{month.year:04d}{month.month:02d}01",
                    "stockNo": symbol,
                    "response": "json",
                }
                response, _attempts = request_with_retry(
                    lambda url, **kwargs: http.get(url, params=params, **kwargs),
                    API_URL,
                    timeout=timeout,
                    budget=budget,
                    provider="twse",
                )
                request_count += 1
                try:
                    try:
                        validate_response_origin(response, API_URL, allowed_hosts=API_HOSTS)
                    except ValueError as exc:
                        status = getattr(response, "status_code", None)
                        if status is not None and 300 <= int(status) < 400:
                            raise ValueError(
                                f"TWSE redirected request {request_count} for {symbol}/{month:%Y-%m} "
                                f"to {_safe_redirect_target(response)}; redirects are rejected."
                            ) from exc
                        raise
                    response.raise_for_status()
                    try:
                        payload = json.loads(read_http_response_bytes(response, MAX_RESPONSE_BYTES).decode("utf-8-sig"))
                        normalized = normalize_twse_payload(payload, symbol, start, end, month)
                    except (UnicodeError, ValueError) as exc:
                        reason = _safe_validation_reason(exc)
                        raise ValueError(
                            f"TWSE response failed validation for {symbol}/{month:%Y-%m} "
                            f"(reason={reason})."
                        ) from exc
                    source_row_count += int(normalized.attrs["source_row_count"])
                    excluded_no_trade_rows += int(normalized.attrs["excluded_no_trade_rows"])
                    if not normalized.empty:
                        frames.append(normalized)
                finally:
                    close = getattr(response, "close", None)
                    if callable(close):
                        close()

        if not frames:
            raise ValueError("TWSE returned no usable daily-price records.")
        combined = pd.concat(frames, ignore_index=True)
        if combined.duplicated(["date", "symbol"], keep=False).any():
            raise ValueError("TWSE returned duplicate symbol/date records across months.")
        minimum = max(1, int(api.get("minimum_history_days", 400)))
        counts = combined.groupby("symbol")["date"].nunique()
        if set(counts.index.astype(str)) != set(symbols) or (counts < minimum).any():
            raise ValueError("TWSE history is shorter than the configured minimum.")
        common_dates = set.intersection(*(set(group["date"]) for _, group in combined.groupby("symbol")))
        if len(common_dates) < minimum:
            raise ValueError("TWSE symbols do not share enough trading dates for comparison.")

        combined = combined.sort_values(["symbol", "date"], kind="stable").reset_index(drop=True)
        target = ensure_parent(Path(cfg["data"]["raw_dir"]) / "market_twse.csv")
        written = atomic_write_dataframe(combined, target)
        write_json(
            {
                "provider": "twse",
                "status": "success",
                "data_source": "TWSE public daily transaction data",
                "is_simulated_data": False,
                "row_count": int(len(combined)),
                "source_row_count": source_row_count,
                "excluded_no_trade_rows": excluded_no_trade_rows,
                "request_count": budget.used_requests,
                "months_requested": len(months),
                "data_file_sha256": hashlib.sha256(written.read_bytes()).hexdigest(),
                "symbols": symbols,
                "range": {"start": str(combined["date"].min()), "end": str(combined["date"].max())},
                "source_url": API_URL,
                "dataset_url": "https://data.gov.tw/dataset/11549",
                "license_url": "https://data.gov.tw/license",
            },
            cfg["data"].get("source_metadata_path", "reports/metrics/source_metadata.json"),
        )
        return written
    except Exception as exc:
        print(f"TWSE fetch failed; no release data written: {safe_exception_message(exc)}")
        return None
