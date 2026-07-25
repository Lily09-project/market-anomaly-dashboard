from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
try:
    import requests
except Exception:
    requests = None

from src.utils import clean_numeric, ensure_parent, load_config, parse_date


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


def _parse_response(response) -> pd.DataFrame:
    content_type = response.headers.get("content-type", "").lower()
    text = response.text
    if "json" in content_type or text.lstrip().startswith(("{", "[")):
        payload = response.json()
        if isinstance(payload, dict):
            for key in ["data", "records", "result"]:
                if key in payload and isinstance(payload[key], list):
                    return pd.DataFrame(payload[key])
        return pd.DataFrame(payload)
    return pd.read_csv(StringIO(text))


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
        response = requests.get(url, timeout=cfg["api"].get("timeout_seconds", 15))
        response.raise_for_status()
        normalized = normalize_market_columns(_parse_response(response))
        out = ensure_parent(Path(cfg["data"]["raw_dir"]) / "market_raw.csv")
        normalized.to_csv(out, index=False, encoding="utf-8")
        return out
    except Exception as exc:
        print(f"Market API failed; fallback will be used. Reason: {exc}")
        return None


if __name__ == "__main__":
    print(fetch_market_data())
