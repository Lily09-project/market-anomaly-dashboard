from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.fetch_fx_data import normalize_fx_columns
from src.fetch_market_data import normalize_market_columns
from src.generate_sample_data import generate_sample_data
from src.utils import atomic_write_dataframe, ensure_parent, load_config, project_path


def _candidate_paths(directory: str, pattern: str) -> list[Path]:
    base = project_path(directory)
    return sorted(base.glob(pattern), key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True) if base.exists() else []


def _load_market(config: dict, mode: str = "api", input_path: str | Path | None = None) -> pd.DataFrame:
    raw_paths = _candidate_paths(config["data"]["raw_dir"], "*market*.csv")
    sample_path = project_path(config["data"]["sample_market_path"])
    if input_path is not None:
        raw_paths = [Path(input_path)]
    if raw_paths and mode == "api":
        return normalize_market_columns(pd.read_csv(raw_paths[0], dtype={"symbol": "string", "stock_id": "string", "證券代號": "string", "代號": "string"}))
    if not sample_path.exists():
        generate_sample_data(config)
    return normalize_market_columns(pd.read_csv(sample_path, dtype={"symbol": "string", "stock_id": "string", "證券代號": "string", "代號": "string"}))


def _load_fx(config: dict, mode: str = "api", input_path: str | Path | None = None) -> pd.DataFrame:
    raw_paths = _candidate_paths(config["data"]["raw_dir"], "*fx*.csv")
    sample_path = project_path(config["data"]["sample_fx_path"])
    if input_path is not None:
        raw_paths = [Path(input_path)]
    if raw_paths and mode == "api":
        return normalize_fx_columns(pd.read_csv(raw_paths[0]), config["data"]["currency_pair"])
    if not sample_path.exists():
        generate_sample_data(config)
    return normalize_fx_columns(pd.read_csv(sample_path), config["data"]["currency_pair"])


def merge_market_fx(market: pd.DataFrame, fx: pd.DataFrame, currency_pair: str, max_age_days: int = 7) -> pd.DataFrame:
    """Causal FX alignment: never fill from a future date or another symbol."""
    market = market.copy()
    market["date"] = pd.to_datetime(market["date"], errors="coerce")
    fx = fx.copy()
    fx["date"] = pd.to_datetime(fx["date"], errors="coerce")
    market = market.dropna(subset=["date"]).sort_values("date")
    fx = fx.loc[fx["currency_pair"].eq(currency_pair)].dropna(subset=["date", "exchange_rate"])
    fx = fx.sort_values("date").drop_duplicates("date", keep="last")
    if fx.empty:
        raise ValueError("No usable FX observations for the configured currency pair.")
    if max_age_days < 0:
        raise ValueError("FX maximum age must be non-negative.")
    merged = pd.merge_asof(
        market, fx[["date", "currency_pair", "exchange_rate"]],
        on="date", direction="backward", tolerance=pd.Timedelta(days=max_age_days),
    )
    return merged.dropna(subset=["exchange_rate"]).sort_values(["symbol", "date"]).reset_index(drop=True)


def preprocess_data(
    config: dict | None = None, *, mode: str = "api",
    market_path: str | Path | None = None, fx_path: str | Path | None = None,
) -> Path:
    cfg = config or load_config()
    if mode not in {"sample", "api"}:
        raise ValueError("mode must be sample or api")
    market = _load_market(cfg, mode, market_path).drop_duplicates()
    fx = _load_fx(cfg, mode, fx_path).drop_duplicates()
    merged = merge_market_fx(
        market, fx, cfg["data"]["currency_pair"], int(cfg["data"].get("fx_max_age_days", 7)),
    )
    merged = merged.dropna(subset=["date", "symbol", "open", "high", "low", "close", "volume", "exchange_rate"])
    merged = merged.drop_duplicates(subset=["date", "symbol"])
    if merged.empty:
        raise ValueError("No market rows have a valid historical FX observation.")
    out = ensure_parent(cfg["data"]["cleaned_path"])
    return atomic_write_dataframe(merged, out)


if __name__ == "__main__":
    print(preprocess_data())
