"""Fetch public, unauthenticated FinMind Taiwan stock daily prices.

The production Pages pipeline uses this adapter in strict mode. It performs
one bounded request per configured symbol and never accepts a caller-supplied
URL or token.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import requests
except Exception:
    requests = None

from src.fetch_market_data import MARKET_COLUMN_ALIASES, normalize_market_columns
from src.request_policy import RequestBudget, request_with_retry, validate_response_origin, validate_upstream_url
from src.utils import atomic_write_dataframe, ensure_parent, load_config, normalize_http_timeout, read_http_response_bytes, safe_exception_message, write_json

API_URL = "https://api.finmindtrade.com/api/v4/data"
API_HOSTS = {"api.finmindtrade.com"}
SYMBOL_PATTERN = re.compile(r"^[0-9]{4,6}$")
MAX_SYMBOLS = 8
NUMERIC_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")


def _taipei_today() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date().isoformat()


def _validate_date(value: Any, name: str) -> str:
    try:
        parsed = datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD.") from exc
    return parsed.isoformat()


def normalize_finmind_payload(payload: Any, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    if not isinstance(payload, dict) or payload.get("status") not in (200, "200"):
        raise ValueError("FinMind returned an unsuccessful response.")
    records = payload.get("data")
    if not isinstance(records, list) or not records:
        raise ValueError("FinMind returned no price records.")
    raw = pd.DataFrame(records)
    # The generic CSV importer is deliberately tolerant. Public API values
    # must instead be numeric as received; never strip letters to invent prices.
    for field in ("open", "high", "low", "close", "volume"):
        column = next((alias for alias in MARKET_COLUMN_ALIASES[field] if alias in raw.columns), None)
        if column is None:
            continue  # The normalizer reports the missing required column.
        for value in raw[column]:
            if isinstance(value, bool):
                raise ValueError("FinMind returned incomplete or invalid numeric price records.")
            if isinstance(value, str):
                if not NUMERIC_PATTERN.fullmatch(value.strip()):
                    raise ValueError("FinMind returned incomplete or invalid numeric price records.")
            elif not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("FinMind returned incomplete or invalid numeric price records.")
    frame = normalize_market_columns(raw)
    if len(frame) != len(records):
        raise ValueError("FinMind returned incomplete or invalid price records.")
    if frame.empty:
        raise ValueError("FinMind returned no usable price records.")
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    if frame["date"].isna().any():
        raise ValueError("FinMind returned an invalid trading date.")
    frame["date"] = frame["date"].dt.strftime("%Y-%m-%d")
    if set(frame["symbol"].astype(str)) != {symbol}:
        raise ValueError("FinMind returned data for an unexpected symbol.")
    if (frame["date"] < start_date).any() or (frame["date"] > end_date).any():
        raise ValueError("FinMind returned data outside the requested date range.")
    numeric = ["open", "high", "low", "close", "volume"]
    frame[numeric] = frame[numeric].apply(lambda column: pd.to_numeric(column, errors="coerce"))
    if frame[numeric].isna().any().any():
        raise ValueError("FinMind returned invalid numeric price fields.")
    finite = frame[numeric].apply(lambda column: column.map(math.isfinite))
    if not finite.all().all():
        raise ValueError("FinMind returned non-finite numeric price fields.")
    ohlc = ["open", "high", "low", "close"]
    # FinMind documents all-zero OHLC as a day with no announced transaction price.
    # Only the exact all-zero OHLC + zero-volume row is excluded from price analysis.
    no_trade = frame[ohlc].eq(0).all(axis=1) & frame["volume"].eq(0)
    bad_price = (frame[ohlc] <= 0).any(axis=1) & ~no_trade
    bad_volume = frame["volume"] < 0
    bad_range = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
    duplicate = frame.duplicated(["date", "symbol"], keep=False)
    invalid = bad_price | bad_volume | bad_range
    if invalid.any():
        sample = frame.loc[invalid, ["symbol", "date"]].drop_duplicates().head(5)
        dates = ", ".join(f"{row.symbol} {row.date}" for row in sample.itertuples(index=False))
        reasons = []
        if bad_price.any():
            reasons.append("non-positive price")
        if bad_volume.any():
            reasons.append("negative volume")
        if bad_range.any():
            reasons.append("OHLC range")
        raise ValueError(f"FinMind returned inconsistent OHLCV values ({', '.join(reasons)}): {dates}")
    if duplicate.any():
        raise ValueError("FinMind returned duplicate symbol/date price records.")
    source_row_count = len(frame)
    excluded_no_trade_rows = int(no_trade.sum())
    frame = frame.loc[~no_trade].copy()
    if frame.empty:
        raise ValueError("FinMind returned no usable priced records after excluding documented no-trade rows.")
    frame = frame.sort_values("date", kind="stable").reset_index(drop=True)
    frame.attrs["source_row_count"] = source_row_count
    frame.attrs["excluded_no_trade_rows"] = excluded_no_trade_rows
    return frame


def fetch_finmind(config: dict[str, Any] | None = None, *, client: Any = None) -> Path | None:
    cfg = config or load_config()
    api = cfg.get("api", {})
    symbols = [str(item).strip() for item in api.get("symbols", [])]
    start = _validate_date(api.get("start_date", "2021-01-01"), "start_date")
    end = _validate_date(api.get("end_date") or _taipei_today(), "end_date")
    try:
        if not symbols or len(symbols) > MAX_SYMBOLS or len(set(symbols)) != len(symbols):
            raise ValueError("Configured symbol list is empty, duplicated, or too large.")
        if any(not SYMBOL_PATTERN.fullmatch(symbol) for symbol in symbols):
            raise ValueError("Only numeric Taiwan stock symbols are allowed.")
        if start > end:
            raise ValueError("Configured date range is reversed.")
        validate_upstream_url(API_URL, allowed_hosts=API_HOSTS)
        http = client or requests
        if http is None:
            raise RuntimeError("requests is not installed.")
        timeout = normalize_http_timeout(api.get("timeout_seconds"), default=20.0)
        budget = RequestBudget(max_requests=len(symbols) * 2)
        frames: list[pd.DataFrame] = []
        source_row_count = 0
        excluded_no_trade_rows = 0
        for symbol in symbols:
            params = {"dataset": "TaiwanStockPrice", "data_id": symbol, "start_date": start, "end_date": end}
            response, _attempts = request_with_retry(
                lambda url, **kwargs: http.get(url, params=params, **kwargs),
                API_URL,
                timeout=timeout,
                budget=budget,
                provider="finmind",
            )
            try:
                validate_response_origin(response, API_URL, allowed_hosts=API_HOSTS)
                response.raise_for_status()
                payload = json.loads(read_http_response_bytes(response).decode("utf-8-sig"))
                normalized = normalize_finmind_payload(payload, symbol, start, end)
                source_row_count += int(normalized.attrs["source_row_count"])
                excluded_no_trade_rows += int(normalized.attrs["excluded_no_trade_rows"])
                frames.append(normalized)
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        combined = pd.concat(frames, ignore_index=True)
        minimum = max(1, int(api.get("minimum_history_days", 400)))
        counts = combined.groupby("symbol")["date"].nunique()
        if set(counts.index.astype(str)) != set(symbols) or (counts < minimum).any():
            raise ValueError("FinMind history is shorter than the configured minimum.")
        common_dates = set.intersection(*(set(group["date"]) for _, group in combined.groupby("symbol")))
        if len(common_dates) < minimum:
            raise ValueError("FinMind symbols do not share enough trading dates for comparison.")
        target = ensure_parent(Path(cfg["data"]["raw_dir"]) / "market_finmind.csv")
        written = atomic_write_dataframe(combined, target)
        write_json(
            {
                "provider": "finmind",
                "status": "success",
                "data_source": "API Data",
                "is_simulated_data": False,
                "row_count": int(len(combined)),
                "source_row_count": source_row_count,
                "excluded_no_trade_rows": excluded_no_trade_rows,
                "data_file_sha256": hashlib.sha256(written.read_bytes()).hexdigest(),
                "symbols": symbols,
                "range": {"start": start, "end": end},
            },
            cfg["data"].get("source_metadata_path", "reports/metrics/source_metadata.json"),
        )
        return written
    except Exception as exc:
        print(f"FinMind fetch failed; no release data written: {safe_exception_message(exc)}")
        return None
