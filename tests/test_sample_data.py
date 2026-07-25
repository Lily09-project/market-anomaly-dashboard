from __future__ import annotations

import pandas as pd

from src.generate_sample_data import generate_sample_data
from src.utils import load_config


def test_sample_data_can_be_generated() -> None:
    cfg = load_config()
    market_path, fx_path = generate_sample_data(cfg)
    assert market_path.exists()
    assert fx_path.exists()

    market = pd.read_csv(market_path)
    fx = pd.read_csv(fx_path)
    assert {"date", "symbol", "open", "high", "low", "close", "volume"} <= set(market.columns)
    assert {"date", "currency_pair", "exchange_rate"} <= set(fx.columns)
    assert len(market) > 0
    assert len(fx) > 0
    assert pd.to_datetime(market["date"], errors="coerce").notna().all()
    assert pd.to_numeric(market["close"], errors="coerce").notna().all()
    assert pd.to_numeric(market["volume"], errors="coerce").notna().all()
    assert pd.to_numeric(fx["exchange_rate"], errors="coerce").notna().all()

