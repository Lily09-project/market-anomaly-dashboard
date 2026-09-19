from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.utils import atomic_write_dataframe, ensure_parent, ensure_project_dirs, load_config


def generate_sample_data(config: dict | None = None) -> tuple[Path, Path]:
    cfg = config or load_config()
    ensure_project_dirs(cfg)
    rng = np.random.default_rng(cfg["project"]["random_state"])
    dates = pd.bdate_range(cfg["data"]["start_date"], cfg["data"]["end_date"])
    symbols = cfg["data"]["stock_symbols"]
    market_frames: list[pd.DataFrame] = []
    date_strings = dates.strftime("%Y-%m-%d")
    sample_count = len(dates)

    fx_rate = 30.8
    fx_shocks = set(rng.choice(np.arange(40, max(45, len(dates) - 20)), size=8, replace=False))
    fx_daily_changes = rng.normal(0, 0.0018, sample_count)
    fx_shock_values = rng.normal(0, 0.18, len(fx_shocks))
    for position, shock in zip(sorted(fx_shocks), fx_shock_values, strict=True):
        fx_daily_changes[position] += shock / 100
    fx_rates: list[float] = []
    for daily_change in fx_daily_changes:
        fx_rate = max(26.0, fx_rate * (1 + float(daily_change)))
        fx_rates.append(round(fx_rate, 4))
    fx_frame = pd.DataFrame(
        {
            "date": date_strings,
            "currency_pair": cfg["data"]["currency_pair"],
            "exchange_rate": fx_rates,
        }
    )

    anomaly_positions = set(rng.choice(np.arange(60, max(65, len(dates) - 30)), size=18, replace=False))
    base_prices = {"0050": 120.0, "2330": 580.0, "2317": 105.0}
    for symbol in symbols:
        price = base_prices.get(symbol, float(rng.uniform(80, 300)))
        base_volume = rng.integers(1_800_000, 9_000_000)
        positions = np.arange(sample_count)
        seasonal_volume = 1 + 0.18 * np.sin(positions / 18)
        daily_returns = rng.normal(0.00025, 0.012, sample_count)
        anomaly_indexes = np.array(sorted(anomaly_positions), dtype=int)
        daily_returns[anomaly_indexes] += rng.normal(0, 0.055, len(anomaly_indexes))
        open_noise = rng.normal(0, 0.004, sample_count)
        high_noise = np.abs(rng.normal(0.006, 0.004, sample_count))
        low_noise = np.abs(rng.normal(0.006, 0.004, sample_count))
        volume_noise = rng.lognormal(0, 0.18, sample_count)
        opens: list[float] = []
        highs: list[float] = []
        lows: list[float] = []
        closes: list[float] = []
        for i, daily_return in enumerate(daily_returns):
            previous_close = price
            close = max(5.0, previous_close * (1 + daily_return))
            open_price = max(5.0, previous_close * (1 + open_noise[i]))
            opens.append(round(open_price, 2))
            highs.append(round(max(open_price, close) * (1 + high_noise[i]), 2))
            lows.append(round(min(open_price, close) * (1 - low_noise[i]), 2))
            closes.append(round(close, 2))
            price = close
        volume_multiplier = np.where(np.isin(positions, anomaly_indexes), 3.5, 1.0)
        volumes = np.maximum(10_000, base_volume * seasonal_volume * volume_multiplier * volume_noise).astype(int)
        market_frames.append(
            pd.DataFrame(
                {
                    "date": date_strings,
                    "symbol": symbol,
                    "open": opens,
                    "high": highs,
                    "low": lows,
                    "close": closes,
                    "volume": volumes,
                }
            )
        )

    market_path = ensure_parent(cfg["data"]["sample_market_path"])
    fx_path = ensure_parent(cfg["data"]["sample_fx_path"])
    atomic_write_dataframe(pd.concat(market_frames, ignore_index=True), market_path)
    atomic_write_dataframe(fx_frame, fx_path)
    return market_path, fx_path


if __name__ == "__main__":
    market, fx = generate_sample_data()
    print(f"Generated {market}")
    print(f"Generated {fx}")
