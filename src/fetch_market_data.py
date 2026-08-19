from __future__ import annotations

import json

from io import StringIO
from pathlib import Path

import pandas as pd
try:
    import requests
except Exception:
    requests = None

from src.utils import atomic_write_dataframe, clean_numeric, ensure_parent, load_config, normalize_http_timeout, parse_date, read_http_response_bytes, safe_exception_message


MARKET_COLUMN_ALIASES = {
    "date": ["date", "日期", "交易日期"],
    "symbol": ["symbol", "stock_id", "證券代號", "代號"],
    "open": ["open", "開盤價", "開盤"],
    "high": ["high", "最高價", "最高"],
    "low": ["low", "最低價", "最低"],
    "close": ["close", "收盤價", "收盤"],
    "volume": ["volume", "成交股數", "成交量"],
}


def normalize_market_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for target, aliases in MARKET_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = target
                break
    normalized = df.rename(columns=rename_map).copy()
    required = ["date", "symbol", "open", "high", "low", "close", "volume"]
    missing = [col for col in required if col not in normalized.columns]
    if missing:
        raise ValueError(f"Market data missing columns: {missing}")
    normalized = normalized[required]
    normalized["date"] = normalized["date"].map(parse_date)
    for col in ["open", "high", "low", "close", "volume"]:
        normalized[col] = normalized[col].map(clean_numeric)
    normalized["symbol"] = normalized["symbol"].astype(str).str.strip()
    return normalized.dropna(subset=required)


def _parse_response_payload(payload: bytes, content_type: str = "") -> pd.DataFrame:
    text = payload.decode("utf-8-sig")
    normalized_content_type = str(content_type or "").lower()
    if "json" in normalized_content_type or text.lstrip().startswith(("{", "[")):
        value = json.loads(text)
        if isinstance(value, dict):
            for key in ["data", "records", "result"]:
                if key in value and isinstance(value[key], list):
                    return pd.DataFrame(value[key])
        return pd.DataFrame(value)
    return pd.read_csv(StringIO(text))

def _parse_response(response) -> pd.DataFrame:
    """Backward-compatible response parser for callers outside the fetch path."""
    return _parse_response_payload(
        read_http_response_bytes(response),
        response.headers.get("content-type", ""),
    )

def fetch_market_data(config: dict | None = None) -> Path | None:
    cfg = config or load_config()
    url = cfg["api"].get("market_url", "")
    if requests is None:
        print("requests is not installed; market fallback will be used.")
        return None
    if not url:
        print("Market API URL is empty; fallback will be used.")
        return None
    try:
        timeout = normalize_http_timeout(cfg["api"].get("timeout_seconds"), default=15.0)
        response = requests.get(url, timeout=timeout, stream=True)
        try:
            response.raise_for_status()
            payload = read_http_response_bytes(response)
            normalized = normalize_market_columns(
                _parse_response_payload(payload, response.headers.get("content-type", ""))
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        out = ensure_parent(Path(cfg["data"]["raw_dir"]) / "market_raw.csv")
        return atomic_write_dataframe(normalized, out)
    except Exception as exc:
        print(f"Market API failed; fallback will be used. Reason: {safe_exception_message(exc)}")
        return None

if __name__ == "__main__":
    print(fetch_market_data())
