from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import load_config, project_path


def safe_load_csv(path: str | Path) -> pd.DataFrame:
    resolved = project_path(path)
    if not resolved.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(resolved, parse_dates=["date"])
    except Exception:
        try:
            return pd.read_csv(resolved)
        except Exception:
            return pd.DataFrame()


def safe_load_json(path: str | Path) -> dict[str, Any]:
    resolved = project_path(path)
    if not resolved.exists():
        return {}
    try:
        with resolved.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_available_symbols(df: pd.DataFrame) -> list[str]:
    if df.empty or "symbol" not in df.columns:
        return []
    return sorted(df["symbol"].dropna().astype(str).unique().tolist())


def filter_by_symbol_and_date(df: pd.DataFrame, symbol: str, start_date, end_date) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    filtered = df[df["symbol"].astype(str) == str(symbol)].copy() if "symbol" in df.columns else df.copy()
    if "date" in filtered.columns:
        filtered["date"] = pd.to_datetime(filtered["date"], errors="coerce")
        if start_date:
            filtered = filtered[filtered["date"] >= pd.Timestamp(start_date)]
        if end_date:
            filtered = filtered[filtered["date"] <= pd.Timestamp(end_date)]
        filtered = filtered.sort_values("date")
    return filtered


def load_metrics(path: str | Path | None = None, config: dict | None = None) -> dict[str, Any]:
    cfg = config or load_config()
    metrics_path = path or cfg["reports"]["evaluation_summary_path"]
    return safe_load_json(metrics_path)


def load_dashboard_data(config: dict | None = None) -> tuple[pd.DataFrame, str | None]:
    cfg = config or load_config()
    path = project_path(cfg["data"]["results_path"])
    df = safe_load_csv(path)
    if df.empty:
        return pd.DataFrame(), f"尚未產生資料，請先執行 python run_all.py --mode sample。找不到或無法讀取：{path}"
    required = {"date", "symbol", "close", "volume", "exchange_rate", "volatility_20", "model_anomaly"}
    missing = sorted(required - set(df.columns))
    if missing:
        return pd.DataFrame(), f"分析結果缺少必要欄位：{missing}。請重新執行 python run_all.py --mode sample"
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values(["symbol", "date"]), None


def filter_data(df: pd.DataFrame, symbol: str, start_date, end_date) -> pd.DataFrame:
    return filter_by_symbol_and_date(df, symbol, start_date, end_date)


def build_kpis(df: pd.DataFrame) -> dict[str, str]:
    if df.empty:
        return {
            "latest_close": "N/A",
            "recent_volatility": "N/A",
            "anomaly_count": "0",
            "average_volume": "N/A",
        }
    latest = df.iloc[-1]
    return {
        "latest_close": f"{latest['close']:.2f}",
        "recent_volatility": f"{latest['volatility_20'] * 100:.2f}%",
        "anomaly_count": str(int(df["model_anomaly"].sum())),
        "average_volume": f"{df['volume'].mean():,.0f}",
    }

