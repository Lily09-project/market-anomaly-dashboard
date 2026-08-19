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


FX_COLUMN_ALIASES = {
    "date": ["date", "日期", "資料日期"],
    "currency_pair": ["currency_pair", "pair", "幣別", "Currency"],
    "exchange_rate": ["exchange_rate", "rate", "匯率", "即期賣出", "現金賣出"],
}


def normalize_fx_columns(df: pd.DataFrame, default_pair: str = "USD_TWD") -> pd.DataFrame:
    rename_map = {}
    for target, aliases in FX_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns:
                rename_map[alias] = target
                break
    normalized = df.rename(columns=rename_map).copy()
    if "currency_pair" not in normalized.columns:
        normalized["currency_pair"] = default_pair
    required = ["date", "currency_pair", "exchange_rate"]
    missing = [col for col in required if col not in normalized.columns]
    if missing:
        raise ValueError(f"FX data missing columns: {missing}")
    normalized = normalized[required]
    normalized["date"] = normalized["date"].map(parse_date)
    normalized["exchange_rate"] = normalized["exchange_rate"].map(clean_numeric)
    normalized["currency_pair"] = normalized["currency_pair"].astype(str).str.strip()
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

def fetch_fx_data(config: dict | None = None) -> Path | None:
    cfg = config or load_config()
    url = cfg["api"].get("fx_url", "")
    if requests is None:
        print("requests is not installed; FX fallback will be used.")
        return None
    if not url:
        print("FX API URL is empty; fallback will be used.")
        return None
    try:
        timeout = normalize_http_timeout(cfg["api"].get("timeout_seconds"), default=15.0)
        response = requests.get(url, timeout=timeout, stream=True)
        try:
            response.raise_for_status()
            payload = read_http_response_bytes(response)
            normalized = normalize_fx_columns(
                _parse_response_payload(payload, response.headers.get("content-type", "")),
                cfg["data"]["currency_pair"],
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
        out = ensure_parent(Path(cfg["data"]["raw_dir"]) / "fx_raw.csv")
        return atomic_write_dataframe(normalized, out)
    except Exception as exc:
        print(f"FX API failed; fallback will be used. Reason: {safe_exception_message(exc)}")
        return None

if __name__ == "__main__":
    print(fetch_fx_data())
