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
    market_rows: list[dict] = []
    fx_rows: list[dict] = []

    fx_rate = 30.8
    fx_shocks = set(rng.choice(np.arange(40, max(45, len(dates) - 20)), size=8, replace=False))
    for i, date in enumerate(dates):
        shock = rng.normal(0, 0.18) if i in fx_shocks else 0
        fx_rate = max(26.0, fx_rate * (1 + rng.normal(0, 0.0018) + shock / 100))
        fx_rows.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "currency_pair": cfg["data"]["currency_pair"],
                "exchange_rate": round(fx_rate, 4),
            }
        )

    anomaly_positions = set(rng.choice(np.arange(60, max(65, len(dates) - 30)), size=18, replace=False))
    base_prices = {"0050": 120.0, "2330": 580.0, "2317": 105.0}
    for symbol in symbols:
        price = base_prices.get(symbol, float(rng.uniform(80, 300)))
        base_volume = rng.integers(1_800_000, 9_000_000)
        for i, date in enumerate(dates):
            seasonal_volume = 1 + 0.18 * np.sin(i / 18)
            shock_return = rng.normal(0, 0.055) if i in anomaly_positions else 0
            daily_return = rng.normal(0.00025, 0.012) + shock_return
            previous_close = price
            close = max(5.0, previous_close * (1 + daily_return))
            open_price = max(5.0, previous_close * (1 + rng.normal(0, 0.004)))
            high = max(open_price, close) * (1 + abs(rng.normal(0.006, 0.004)))
            low = min(open_price, close) * (1 - abs(rng.normal(0.006, 0.004)))
            volume_multiplier = 3.5 if i in anomaly_positions else 1.0
            volume = int(max(10_000, base_volume * seasonal_volume * volume_multiplier * rng.lognormal(0, 0.18)))
            market_rows.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "open": round(open_price, 2),
                    "high": round(high, 2),
                    "low": round(low, 2),
                    "close": round(close, 2),
                    "volume": volume,
                }
            )
            price = close

    market_path = ensure_parent(cfg["data"]["sample_market_path"])
    fx_path = ensure_parent(cfg["data"]["sample_fx_path"])
    atomic_write_dataframe(pd.DataFrame(market_rows), market_path)
    atomic_write_dataframe(pd.DataFrame(fx_rows), fx_path)
    return market_path, fx_path


if __name__ == "__main__":
    market, fx = generate_sample_data()
    print(f"Generated {market}")
    print(f"Generated {fx}")
