from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.fetch_fx_data import normalize_fx_columns
from src.fetch_market_data import normalize_market_columns
from src.generate_sample_data import generate_sample_data
from src.utils import ensure_parent, load_config, project_path


def _candidate_paths(directory: str, pattern: str) -> list[Path]:
    base = project_path(directory)
    return sorted(base.glob(pattern)) if base.exists() else []


def _load_market(config: dict) -> pd.DataFrame:
    raw_paths = _candidate_paths(config["data"]["raw_dir"], "*market*.csv")
    sample_path = project_path(config["data"]["sample_market_path"])
    if raw_paths:
        return normalize_market_columns(pd.read_csv(raw_paths[0]))
    if not sample_path.exists():
        generate_sample_data(config)
    return normalize_market_columns(pd.read_csv(sample_path))


def _load_fx(config: dict) -> pd.DataFrame:
    raw_paths = _candidate_paths(config["data"]["raw_dir"], "*fx*.csv")
    sample_path = project_path(config["data"]["sample_fx_path"])
    if raw_paths:
        return normalize_fx_columns(pd.read_csv(raw_paths[0]), config["data"]["currency_pair"])
    if not sample_path.exists():
        generate_sample_data(config)
    return normalize_fx_columns(pd.read_csv(sample_path), config["data"]["currency_pair"])


def preprocess_data(config: dict | None = None) -> Path:
    cfg = config or load_config()
    market = _load_market(cfg).drop_duplicates()
    fx = _load_fx(cfg).drop_duplicates()

    market = market.sort_values(["symbol", "date"]).reset_index(drop=True)
    fx = fx.sort_values(["date", "currency_pair"]).drop_duplicates(subset=["date"], keep="last")

    merged = market.merge(fx[["date", "currency_pair", "exchange_rate"]], on="date", how="left")
    merged["exchange_rate"] = merged["exchange_rate"].ffill().bfill()
    merged["currency_pair"] = merged["currency_pair"].fillna(cfg["data"]["currency_pair"])
    merged = merged.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume", "exchange_rate"])
    merged = merged.sort_values(["symbol", "date"]).drop_duplicates(subset=["date", "symbol"])

    out = ensure_parent(cfg["data"]["cleaned_path"])
    merged.to_csv(out, index=False, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(preprocess_data())

