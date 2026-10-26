"""Load raw or sample prices, normalise the columns and write the cleaned table."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.fetch_market_data import normalize_market_columns
from src.corporate_actions import adjust_finmind_splits
from src.generate_sample_data import generate_sample_data
from src.utils import atomic_write_dataframe, ensure_parent, load_config, project_path

SYMBOL_DTYPES = {"symbol": "string", "stock_id": "string", "證券代號": "string", "代號": "string"}


def _latest_raw(directory: str) -> Path | None:
    base = project_path(directory)
    candidates = sorted((p for p in base.glob("*market*.csv") if p.is_file()), key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True) if base.exists() else []
    return candidates[0] if candidates else None


def load_market(config: dict, mode: str = "sample", input_path: str | Path | None = None) -> tuple[pd.DataFrame, str]:
    """Return the normalised prices and where they came from ("api" or "sample")."""
    # Sample runs never look at raw caches, so a stale download cannot leak in.
    path = Path(input_path) if input_path is not None else (_latest_raw(config["data"]["raw_dir"]) if mode == "api" else None)
    if path is not None and mode == "api":
        return normalize_market_columns(pd.read_csv(path, dtype=SYMBOL_DTYPES)), "api"
    sample_path = project_path(config["data"]["sample_market_path"])
    if not sample_path.exists():
        generate_sample_data(config)
    return normalize_market_columns(pd.read_csv(sample_path, dtype=SYMBOL_DTYPES)), "sample"


def preprocess_data(config: dict | None = None, *, mode: str = "sample", market_path: str | Path | None = None) -> Path:
    cfg = config or load_config()
    if mode not in {"sample", "api"}:
        raise ValueError("mode must be sample or api")
    market, source = load_market(cfg, mode, market_path)
    market = market.dropna(subset=["date", "symbol", "close"])
    market = market[market["close"] > 0]
    market = market.sort_values(["symbol", "date"], kind="stable").drop_duplicates(subset=["date", "symbol"], keep="last")
    if market.empty:
        raise ValueError("No usable market rows after cleaning.")
    if source == "api" and cfg.get("api", {}).get("provider") == "finmind":
        market = adjust_finmind_splits(market)
    market = market.assign(date=pd.to_datetime(market["date"]).dt.strftime("%Y-%m-%d"), data_source=source)
    return atomic_write_dataframe(market.reset_index(drop=True), ensure_parent(cfg["data"]["cleaned_path"]))


if __name__ == "__main__":
    print(preprocess_data())
