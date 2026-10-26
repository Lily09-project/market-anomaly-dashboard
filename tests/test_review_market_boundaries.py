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


def test_walk_forward_first_fold_enters_from_cash(monkeypatch):
    count = 800
    prices = 100 * np.power(1.001, np.arange(count))
    dates = pd.bdate_range("2020-01-01", periods=count).strftime("%Y-%m-%d").tolist()
    # Controlled causal signals guarantee a long position at the first OOS boundary.
    # The earlier random-market ledger test can legitimately select cash there.
    monkeypatch.setattr(backtest, "crossover_positions",
                        lambda values, fast, slow: np.ones(len(values)) if fast == 5 else np.zeros(len(values)))
    result = export_web.analyse_backtest(dates, prices)
    first = dates.index(result["walk_forward"][0]["test_start"]) - 1
    stop = dates.index(result["walk_forward"][-1]["test_end"])
    earned = prices[first + 1:stop + 1] / prices[first:stop] - 1
    earned[0] -= result["cost_per_trade"]
    expected = np.round(np.cumprod(1 + earned)[::5], 4)
    np.testing.assert_allclose(result["equity"]["walk_forward"], expected, atol=1e-4, rtol=0)


def test_walk_forward_switch_cost_uses_previous_selected_holdings():
    asset = np.array([0.10, -0.02, 0.03, 0.04, -0.05, 0.06, -0.07, 0.02, 0.01, -0.03, 0.01, 0.02])
    a = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 1, 1], dtype=float)
    positions = np.column_stack([a, 1-a])
    cost = 0.01
    matrix = positions * asset[:, None] - np.abs(np.diff(np.vstack([np.zeros(2), positions]), axis=0)) * cost
    folds, actual = backtest.walk_forward(matrix, train=4, test=2, positions=positions, cost=cost)
    assert len({fold.chosen for fold in folds}) > 1
    held = np.concatenate([positions[fold.test[0]:fold.test[1], fold.chosen] for fold in folds])
    gross = np.concatenate([asset[fold.test[0]:fold.test[1]] for fold in folds])
    expected = held * gross - np.abs(np.diff(np.r_[0.0, held])) * cost
    np.testing.assert_allclose(actual, expected, atol=1e-12)
    assert [fold.test_sharpe for fold in folds] == pytest.approx([
        expected[i:i+2].mean() / expected[i:i+2].std(ddof=1) * np.sqrt(252)
        if expected[i:i+2].std(ddof=1) else 0.0 for i in range(0, len(expected), 2)
    ])
