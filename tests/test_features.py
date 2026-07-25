from __future__ import annotations

import pandas as pd

from src.features import FEATURE_COLUMNS, build_features
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.utils import load_config


def test_feature_engineering_outputs_required_features() -> None:
    cfg = load_config()
    generate_sample_data(cfg)
    preprocess_data(cfg)
    features_path = build_features(cfg)
    features = pd.read_csv(features_path)
    assert set(FEATURE_COLUMNS) <= set(features.columns)
    assert len(features) > 0
    assert features[FEATURE_COLUMNS].replace([float("inf"), float("-inf")], pd.NA).notna().all().all()
    assert features["risk_score_baseline"].between(0, 100).all()


def test_symbol_rolling_does_not_cross_contaminate() -> None:
    cfg = load_config()
    features_path = build_features(cfg)
    features = pd.read_csv(features_path, parse_dates=["date"]).sort_values(["symbol", "date"])
    counts = features.groupby("symbol").size()
    assert len(counts) >= 2
    assert (counts > 20).all()
    assert features.groupby("symbol")["daily_return"].first().notna().all()
