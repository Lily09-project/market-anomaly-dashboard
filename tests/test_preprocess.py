from __future__ import annotations

import pandas as pd

from src.fetch_market_data import normalize_market_columns
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.utils import load_config


def test_preprocess_outputs_cleaned_data() -> None:
    cfg = load_config()
    generate_sample_data(cfg)
    cleaned_path = preprocess_data(cfg)
    cleaned = pd.read_csv(cleaned_path, parse_dates=["date"])
    assert {"date", "symbol", "open", "high", "low", "close", "volume", "exchange_rate"} <= set(cleaned.columns)
    assert pd.api.types.is_datetime64_any_dtype(cleaned["date"])
    assert pd.api.types.is_numeric_dtype(cleaned["close"])
    assert pd.api.types.is_numeric_dtype(cleaned["volume"])
    assert cleaned["close"].notna().all()


def test_market_alias_mapping_handles_chinese_columns() -> None:
    raw = pd.DataFrame(
        {
            "日期": ["113/01/02"],
            "證券代號": ["2330"],
            "開盤價": ["590.0"],
            "最高價": ["596.0"],
            "最低價": ["588.0"],
            "收盤價": ["593.0"],
            "成交股數": ["1,234,567"],
        }
    )
    normalized = normalize_market_columns(raw)
    assert normalized.loc[0, "date"].year == 2024
    assert normalized.loc[0, "volume"] == 1234567

