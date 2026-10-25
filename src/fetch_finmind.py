"""Fetch public, unauthenticated FinMind Taiwan stock daily prices.

The production Pages pipeline uses this adapter in strict mode. It performs
one bounded request per configured symbol and never accepts a caller-supplied
URL or token.
"""
from __future__ import annotations

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

from src.fetch_market_data import normalize_market_columns
from src.request_policy import RequestBudget, request_with_retry, validate_response_origin, validate_upstream_url
from src.utils import atomic_write_dataframe, ensure_parent, load_config, normalize_http_timeout, read_http_response_bytes, safe_exception_message

API_URL = "https://api.finmindtrade.com/api/v4/data"
API_HOSTS = {"api.finmindtrade.com"}
SYMBOL_PATTERN = re.compile(r"^[0-9]{4,6}$")
MAX_SYMBOLS = 8


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
    frame = normalize_market_columns(pd.DataFrame(records))
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
    if not frame[numeric].map(lambda column: column.map(math.isfinite)).all().all():
        raise ValueError("FinMind returned non-finite numeric price fields.")
    bad_price = (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    bad_volume = frame["volume"] < 0
    bad_range = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
    )
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
    return frame.sort_values("date", kind="stable").drop_duplicates(["date", "symbol"], keep="last").reset_index(drop=True)


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
                frames.append(normalize_finmind_payload(payload, symbol, start, end))
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
        return atomic_write_dataframe(combined, target)
    except Exception as exc:
        print(f"FinMind fetch failed; no release data written: {safe_exception_message(exc)}")
        return None
