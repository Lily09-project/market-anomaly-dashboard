from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analytics import backtest as bt
from src.analytics import events, hmm, risk, stats
from src.generate_sample_data import REGIMES, STOCKS, simulate
from src.utils import load_config


# ---------------------------------------------------------------- stats

def test_normal_ppf_inverts_the_cdf() -> None:
    for p in (1e-6, 0.01, 0.025, 0.3, 0.5, 0.8, 0.975, 0.999):
        assert stats.normal_cdf(stats.normal_ppf(p)) == pytest.approx(p, abs=1e-8)
    assert stats.normal_ppf(0.975) == pytest.approx(1.959964, abs=1e-6)
    with pytest.raises(ValueError):
        stats.normal_ppf(1.0)


def test_sharpe_drawdown_and_moments() -> None:
    assert stats.sharpe(np.array([0.01, 0.01])) == 0.0  # zero volatility
    assert stats.sharpe(np.array([0.01])) == 0.0
    r = np.array([0.01, -0.02, 0.03, 0.0])
    assert stats.sharpe(r) == pytest.approx(r.mean() / r.std(ddof=1) * math.sqrt(252))
    # 1.0 → 1.1 → 0.88 (−20% from the peak) → 0.968
    assert stats.max_drawdown(np.array([0.1, -0.2, 0.1])) == pytest.approx(0.2)
    assert stats.max_drawdown(np.array([])) == 0.0
    z = np.random.default_rng(0).normal(size=200_000)
    assert stats.skewness(z) == pytest.approx(0.0, abs=0.02)
    assert stats.kurtosis(z) == pytest.approx(3.0, abs=0.05)
    assert stats.skewness(np.ones(5)) == 0.0 and stats.kurtosis(np.ones(5)) == 3.0


# ---------------------------------------------------------------- HMM

def _two_state(seed: int = 3, n: int = 1500) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    states = np.zeros(n, dtype=int)
    for t in range(1, n):
        states[t] = states[t - 1] if rng.random() < 0.97 else 1 - states[t - 1]
    return rng.normal(0, np.where(states == 0, 0.01, 0.03)), states


def test_hmm_fit_is_a_valid_model_with_monotone_likelihood() -> None:
    x, truth = _two_state()
    result = hmm.fit(x, k=2, seed=1)
    assert np.allclose(result.transition.sum(axis=1), 1.0)
    assert np.all(result.transition >= 0)
    assert result.initial.sum() == pytest.approx(1.0)
    assert np.all(np.diff(result.history) >= -1e-6)  # EM never decreases the likelihood
    assert result.variances[0] < result.variances[1]  # states ordered calm → turbulent
    assert np.sqrt(result.variances) == pytest.approx([0.01, 0.03], rel=0.15)
    path = hmm.viterbi(x, result)
    accuracy, _ = hmm.aligned_accuracy(path, truth, 2)
    assert accuracy >= 0.9
    assert result.expected_durations[0] == pytest.approx(1 / (1 - result.transition[0, 0]))
    gamma = hmm.posterior(x, result)
    assert np.allclose(gamma.sum(axis=1), 1.0)


def test_hmm_recovers_the_known_regimes_of_the_sample_data() -> None:
    prices, truth, _ = simulate(load_config())
    order = {r[0]: i for i, r in enumerate(REGIMES)}
    states = truth["state"].map(order).to_numpy()[1:]
    for symbol in STOCKS:
        close = prices.loc[prices["symbol"] == symbol, "close"].to_numpy()
        r = np.diff(np.log(close))
        r[events.anomaly_days(pd.Series(r)).to_numpy()] = np.nan
        result = hmm.fit(r, k=3, seed=3)
        accuracy, _ = hmm.aligned_accuracy(hmm.viterbi(r, result), states, 3)
        assert accuracy >= 0.8, (symbol, accuracy)


def test_hmm_handles_missing_days_and_rejects_short_series() -> None:
    x, _ = _two_state(n=400)
    x[::17] = np.nan
    result = hmm.fit(x, k=2, seed=0)
    assert len(hmm.viterbi(x, result)) == len(x)
    z = hmm.predictive_z(x, result)
    assert np.isnan(z[0]) and np.isnan(z[17])
    with pytest.raises(ValueError):
        hmm.fit(np.ones(5), k=2)
    with pytest.raises(ValueError):
        hmm.fit(np.ones((20, 2)), k=2)
    with pytest.raises(ValueError, match="n_init"):
        hmm.fit(x, k=2, n_init=0)


def test_predictive_z_flags_a_jump_relative_to_the_current_regime() -> None:
    x, _ = _two_state(n=800)
    result = hmm.fit(x, k=2, seed=0)
    calm_day = int(np.flatnonzero(hmm.viterbi(x, result) == 0)[200])
    y = x.copy()
    y[calm_day] = 0.09  # 9σ for the calm regime, 3σ for the turbulent one
    z = hmm.predictive_z(y, result)
    assert abs(z[calm_day]) > 5
    # Only the past is used: changing day t leaves z before t untouched.
    assert np.allclose(z[:calm_day], hmm.predictive_z(x, result)[:calm_day])


def test_aligned_accuracy_ignores_label_names() -> None:
    truth = np.array([0, 0, 1, 1, 2, 2])
    assert hmm.aligned_accuracy(np.array([2, 2, 0, 0, 1, 1]), truth, 3) == (1.0, (1, 2, 0))


# ---------------------------------------------------------------- events

def test_robust_z_is_causal_and_ignores_outliers_in_the_window() -> None:
    r = pd.Series(np.random.default_rng(1).normal(0, 0.01, 300))
    z = events.robust_z(r)
    changed = r.copy()
    changed.iloc[250:] = 1.0
    assert np.allclose(events.robust_z(changed).iloc[:250].fillna(0), z.iloc[:250].fillna(0))
    r.iloc[200] = 0.2
    assert bool(events.anomaly_days(r).iloc[200])


def test_abnormal_returns_by_hand() -> None:
    returns = np.full(200, 0.001)
    returns[150] = 0.05
    ar = events.abnormal_returns(returns, 150)
    assert ar is not None and len(ar) == 16
    assert ar[5] == pytest.approx(0.049)  # offset 0
    assert np.allclose(np.delete(ar, 5), 0.0)
    assert events.abnormal_returns(returns, 50) is None  # estimation window does not fit
    assert events.abnormal_returns(returns, 195) is None  # event window runs past the end
    gappy = returns.copy()
    gappy[30:140] = np.nan
    assert events.abnormal_returns(gappy, 150) is None  # too few clean baseline days


def test_event_study_on_pure_noise_contains_zero() -> None:
    rng = np.random.default_rng(5)
    abnormal = [rng.normal(0, 0.01, 16) for _ in range(60)]
    s = events.study(abnormal)
    assert s.n_events == 60
    assert all(lo <= 0 <= hi for lo, hi in zip(s.post_low, s.post_high))
    assert s.post_offsets[0] == 1 and s.offsets[0] == -5
    # Hand check of the averaging: CAR at the last offset is the mean of row sums.
    assert s.mean_car[-1] == pytest.approx(np.mean([a.sum() for a in abnormal]))
    assert events.study(abnormal) == s  # seeded bootstrap
    empty = events.study([])
    assert empty.n_events == 0 and math.isnan(empty.post_car[0])


def test_event_study_finds_a_real_drift() -> None:
    rng = np.random.default_rng(6)
    abnormal = []
    for _ in range(80):
        a = rng.normal(0, 0.01, 16)
        a[6:9] += 0.004
        abnormal.append(a)
    s = events.study(abnormal)
    assert s.post_low[2] > 0  # CAR(+1..+3) is significantly positive


# ---------------------------------------------------------------- backtest

def test_moving_average_and_crossover_positions() -> None:
    prices = np.array([1.0, 2, 3, 4, 5])
    assert np.allclose(bt.moving_average(prices, 2)[1:], [1.5, 2.5, 3.5, 4.5])
    assert np.isnan(bt.moving_average(prices, 2)[0])
    assert np.isnan(bt.moving_average(prices, 9)).all()
    assert bt.crossover_positions(prices, 1, 3).tolist() == [0, 0, 1, 1, 1]


def test_strategy_returns_use_yesterdays_position_and_pay_costs() -> None:
    prices = np.array([100.0, 110, 99, 99])
    positions = np.array([1.0, 0, 1, 1])
    r = bt.strategy_returns(prices, positions, cost=0.01)
    # Day 1 earns the 10% move held from day 0 minus the entry cost; day 2 is in cash
    # but pays the exit cost; day 3 re-enters (cost) and earns 0%.
    assert r == pytest.approx([0.10 - 0.01, -0.01, -0.01])


def test_lookahead_is_detected_and_honest_strategies_pass() -> None:
    prices = 100 * np.exp(np.cumsum(np.random.default_rng(2).normal(0, 0.01, 600)))
    bt.assert_causal(lambda p: bt.crossover_positions(p, 10, 50), prices)

    def cheat(p: np.ndarray) -> np.ndarray:
        # Uses tomorrow's price to decide today: classic look-ahead bias.
        tomorrow = np.concatenate([p[1:], p[-1:]])
        return (tomorrow > p).astype(float)

    with pytest.raises(bt.LookaheadError):
        bt.assert_causal(cheat, prices)


def test_walk_forward_windows_do_not_overlap_and_test_follows_train() -> None:
    matrix = np.random.default_rng(3).normal(0, 0.01, (1300, 5))
    folds, oos = bt.walk_forward(matrix, train=500, test=100)
    assert len(folds) == 8
    for a, b in zip(folds, folds[1:]):
        assert a.test[1] == b.test[0]  # consecutive, non-overlapping test windows
    for f in folds:
        assert f.train[1] == f.test[0]
    assert len(oos) == 8 * 100
    assert bt.walk_forward(matrix[:300], train=500, test=100)[0] == []


def _random_walk(seed: int) -> np.ndarray:
    return 100 * np.exp(np.cumsum(np.random.default_rng(seed).normal(0, 0.012, 1300)))


def _trending(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    drift = 0.003 * np.sign(np.sin(np.arange(1300) / 40))
    return 100 * np.exp(np.cumsum(drift + rng.normal(0, 0.012, 1300)))


def test_pbo_is_high_on_random_walks_and_low_with_a_real_signal() -> None:
    grid = bt.parameter_grid()
    noise = [bt.cscv_pbo(bt.returns_matrix(_random_walk(s), grid))[0] for s in range(6)]
    signal = [bt.cscv_pbo(bt.returns_matrix(_trending(s), grid))[0] for s in range(6)]
    assert np.mean(noise) >= 0.4
    assert np.mean(signal) <= np.mean(noise) - 0.25


def test_cscv_validation_and_logit_shape() -> None:
    matrix = np.random.default_rng(4).normal(0, 0.01, (400, 6))
    pbo, logits = bt.cscv_pbo(matrix, blocks=6)
    assert len(logits) == math.comb(6, 3)
    assert 0 <= pbo <= 1
    with pytest.raises(ValueError):
        bt.cscv_pbo(matrix, blocks=5)
    with pytest.raises(ValueError):
        bt.cscv_pbo(matrix[:, :1])


def test_deflated_sharpe_penalises_many_trials() -> None:
    rng = np.random.default_rng(8)
    best = rng.normal(0.0008, 0.01, 1000)
    few = bt.deflated_sharpe(best, list(rng.normal(0, 0.3, 3)))
    many = bt.deflated_sharpe(best, list(rng.normal(0, 0.3, 300)))
    assert many["benchmark_sharpe"] > few["benchmark_sharpe"]
    assert many["dsr"] < few["dsr"]
    assert 0 <= many["dsr"] <= 1
    assert bt.expected_max_sharpe(1.0, 1) == 0.0
    assert bt.expected_max_sharpe(1.0, 100) == pytest.approx(2.5, abs=0.2)


# ---------------------------------------------------------------- risk

def test_mulberry32_matches_the_javascript_reference() -> None:
    draw = risk.mulberry32(20261024)
    assert [draw() for _ in range(3)] == [0.28407089272513986, 0.5368913877755404, 0.6360740626696497]
    zero = risk.mulberry32(0)
    assert zero() == 0.26642920868471265


def test_var_and_cvar_on_a_known_distribution() -> None:
    losses = np.arange(1, 101, dtype=float) / 100  # uniform 0.01 … 1.00
    var, cvar = risk.var_cvar(losses, 0.95)
    assert var == pytest.approx(np.quantile(losses, 0.95))
    assert cvar == pytest.approx(losses[losses >= var].mean())
    assert cvar >= var
    normal = np.random.default_rng(9).normal(0, 1, 400_000)
    var99, cvar99 = risk.var_cvar(normal, 0.99)
    assert var99 == pytest.approx(2.326, abs=0.02)
    assert cvar99 == pytest.approx(2.665, abs=0.03)  # φ(2.326) / 0.01
    with pytest.raises(ValueError):
        risk.var_cvar(np.array([]), 0.95)


def test_block_bootstrap_is_reproducible_and_uses_whole_blocks() -> None:
    returns = np.arange(10, dtype=float)
    paths = risk.block_bootstrap(returns, horizon=7, block=3, paths=4, seed=1)
    assert paths.shape == (4, 7)
    assert np.array_equal(paths, risk.block_bootstrap(returns, 7, 3, 4, 1))
    steps = np.diff(np.concatenate([np.zeros((4, 1)), paths], axis=1), axis=1)
    for row in steps:
        # Within a block the drawn returns are consecutive integers.
        assert row[1] - row[0] == 1 and row[2] - row[1] == 1
    with pytest.raises(ValueError):
        risk.block_bootstrap(returns, 5, 11, 2, 0)
    summary = risk.summarise(risk.block_bootstrap(np.random.default_rng(0).normal(0, 0.01, 500), 20, 5, 500, 3))
    assert summary["cvar95"] >= summary["var95"] and summary["cvar99"] >= summary["var99"]
    assert summary["var99"] >= summary["var95"]
    assert list(summary["fan"]) == ["0.05", "0.25", "0.5", "0.75", "0.95"]
