from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src import export_web
from src.analytics import backtest
from src.fetch_finmind import normalize_finmind_payload


@pytest.mark.parametrize("column,value", [
    ("open", "broken99"),
    ("max", "101oops"),
    ("min", "98missing"),
    ("close", "invalid100"),
    ("Trading_Volume", "1000shares"),
])
def test_strict_finmind_does_not_repair_malformed_numeric_values(column, value):
    record = {"date": "2026-01-02", "stock_id": "2330", "open": 99, "max": 101,
              "min": 98, "close": 100, "Trading_Volume": 1000}
    record[column] = value
    with pytest.raises(ValueError):
        normalize_finmind_payload({"status": 200, "data": [record]},
                                  "2330", "2026-01-01", "2026-01-05")


@pytest.mark.parametrize("size", [400, 630])
def test_backtest_refuses_history_that_cannot_form_one_complete_oos_fold(size):
    dates = pd.bdate_range("2020-01-01", periods=size).strftime("%Y-%m-%d").tolist()
    prices = 100 * np.exp(np.cumsum(np.random.default_rng(73).normal(0, 0.01, size)))
    with pytest.raises(export_web.InsufficientHistoryError):
        export_web.analyse_backtest(dates, prices)


def test_exported_walk_forward_pays_actual_entry_and_switch_costs():
    count = 1400
    days = np.arange(count)
    rng = np.random.default_rng(42)
    prices = 100 * np.exp(np.cumsum(0.003 * np.sign(np.sin(days / 40)) + rng.normal(0, 0.012, count)))
    dates = pd.bdate_range("2020-01-01", periods=count).strftime("%Y-%m-%d").tolist()
    result = export_web.analyse_backtest(dates, prices)
    asset_returns = prices[1:] / prices[:-1] - 1
    held = []
    observations = []
    for fold in result["walk_forward"]:
        start = dates.index(fold["test_start"]) - 1
        stop = dates.index(fold["test_end"])
        fast, slow = fold["params"]
        positions = backtest.crossover_positions(prices, fast, slow)[:-1]
        held.extend(positions[start:stop])
        observations.extend(asset_returns[start:stop])
    held = np.asarray(held)
    actual = held * np.asarray(observations) - np.abs(np.diff(np.r_[0.0, held])) * result["cost_per_trade"]
    # Independent account ledger: start in cash and charge every actual holdings change.
    expected = np.round(np.cumprod(1 + actual)[::5], 4)
    np.testing.assert_allclose(result["equity"]["walk_forward"], expected, atol=1e-4, rtol=0)
    expected_sharpe = actual.mean() / actual.std(ddof=1) * np.sqrt(252) if actual.std(ddof=1) else 0.0
    assert result["oos_sharpe_stitched"] == pytest.approx(expected_sharpe, abs=0.00051)
