from __future__ import annotations

from io import StringIO
from pathlib import Path

import pandas as pd
try:
    import requests
except Exception:
    requests = None

from src.utils import atomic_write_dataframe, clean_numeric, ensure_parent, load_config, normalize_http_timeout, parse_date


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
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        normalized = normalize_fx_columns(_parse_response(response), cfg["data"]["currency_pair"])
        out = ensure_parent(Path(cfg["data"]["raw_dir"]) / "fx_raw.csv")
        return atomic_write_dataframe(normalized, out)
    except Exception as exc:
        print(f"FX API failed; fallback will be used. Reason: {exc}")
        return None


if __name__ == "__main__":
    print(fetch_fx_data())
