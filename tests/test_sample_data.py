from __future__ import annotations

import numpy as np
import pandas as pd

from src.generate_sample_data import CONTROL_SYMBOL, JUMPS_PER_STOCK, REGIMES, STOCKS, generate_sample_data, simulate
from src.utils import load_config


def test_simulation_is_deterministic_and_complete() -> None:
    config = load_config()
    first, truth, jumps = simulate(config)
    again, truth_again, jumps_again = simulate(config)
    pd.testing.assert_frame_equal(first, again)
    pd.testing.assert_frame_equal(truth, truth_again)
    pd.testing.assert_frame_equal(jumps, jumps_again)
    assert sorted(first["symbol"].unique()) == sorted([*STOCKS, CONTROL_SYMBOL])
    assert first.groupby("symbol").size().nunique() == 1
    assert (first["high"] >= first[["open", "close"]].max(axis=1)).all()
    assert (first["low"] <= first[["open", "close"]].min(axis=1)).all()
    assert set(truth["state"]) == {r[0] for r in REGIMES}
    assert len(jumps) == JUMPS_PER_STOCK * len(STOCKS)
    assert set(jumps["symbol"]) == set(STOCKS)


def test_control_series_has_no_drift_and_no_regimes() -> None:
    prices, _, _ = simulate(load_config())
    close = prices.loc[prices["symbol"] == CONTROL_SYMBOL, "close"].to_numpy()
    # Demeaned log returns: the path ends where it started (up to rounding).
    assert abs(np.log(close[-1] / 100.0)) < 1e-3


def test_generate_writes_prices_and_answer_keys(tmp_path) -> None:
    config = load_config()
    config["data"] = {**config["data"], "sample_market_path": str(tmp_path / "sample" / "market.csv")}
    path = generate_sample_data(config)
    assert path.exists()
    assert (tmp_path / "sample" / "regimes_truth.csv").exists()
    assert (tmp_path / "sample" / "injected_events.csv").exists()
    first = path.read_bytes()
    generate_sample_data(config)
    assert path.read_bytes() == first
