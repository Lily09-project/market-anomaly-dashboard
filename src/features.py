from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.preprocess import preprocess_data
from src.utils import ensure_parent, load_config, project_path


FEATURE_COLUMNS = [
    "daily_return",
    "abs_return",
    "log_return",
    "volume_change_rate",
    "moving_avg_5",
    "moving_avg_20",
    "volatility_5",
    "volatility_20",
    "price_ma_gap",
    "volume_zscore_20",
    "fx_return",
    "fx_rolling_volatility_5",
    "risk_score_baseline",
]


def build_features(config: dict | None = None) -> Path:
    cfg = config or load_config()
    cleaned_path = project_path(cfg["data"]["cleaned_path"])
    if not cleaned_path.exists():
        preprocess_data(cfg)
    df = pd.read_csv(cleaned_path, parse_dates=["date"]).sort_values(["symbol", "date"])

    frames = []
    for _, group in df.groupby("symbol", sort=False):
        g = group.copy().sort_values("date")
        g["daily_return"] = g["close"].pct_change()
        g["abs_return"] = g["daily_return"].abs()
        g["log_return"] = np.log(g["close"] / g["close"].shift(1))
        g["volume_change_rate"] = g["volume"].pct_change()
        g["moving_avg_5"] = g["close"].rolling(5, min_periods=5).mean()
        g["moving_avg_20"] = g["close"].rolling(20, min_periods=20).mean()
        g["volatility_5"] = g["daily_return"].rolling(5, min_periods=5).std()
        g["volatility_20"] = g["daily_return"].rolling(20, min_periods=20).std()
        g["price_ma_gap"] = (g["close"] - g["moving_avg_20"]) / g["moving_avg_20"]
        volume_mean = g["volume"].rolling(20, min_periods=20).mean()
        volume_std = g["volume"].rolling(20, min_periods=20).std().replace(0, np.nan)
        g["volume_zscore_20"] = (g["volume"] - volume_mean) / volume_std
        frames.append(g)

    featured = pd.concat(frames, ignore_index=True)
    fx_by_date = featured[["date", "exchange_rate"]].drop_duplicates("date").sort_values("date")
    fx_by_date["fx_return"] = fx_by_date["exchange_rate"].pct_change()
    fx_by_date["fx_rolling_volatility_5"] = fx_by_date["fx_return"].rolling(5, min_periods=5).std()
    featured = featured.drop(columns=["fx_return", "fx_rolling_volatility_5"], errors="ignore")
    featured = featured.merge(fx_by_date[["date", "fx_return", "fx_rolling_volatility_5"]], on="date", how="left")

    vol_component = (featured["volatility_20"].rank(pct=True) * 40).fillna(0)
    return_component = (featured["abs_return"].rank(pct=True) * 35).fillna(0)
    volume_component = (featured["volume_zscore_20"].clip(lower=0).rank(pct=True) * 25).fillna(0)
    featured["risk_score_baseline"] = (vol_component + return_component + volume_component).clip(0, 100).round(2)

    featured = featured.replace([np.inf, -np.inf], np.nan)
    featured = featured.dropna(subset=FEATURE_COLUMNS + ["close", "volume", "exchange_rate"])
    out = ensure_parent(cfg["data"]["features_path"])
    featured.to_csv(out, index=False, encoding="utf-8")
    return out


if __name__ == "__main__":
    print(build_features())

