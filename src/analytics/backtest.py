"""Moving-average crossover backtests, and the tools that keep them honest.

* Positions are decided with prices up to day t and earn day t+1's return.
  ``assert_causal`` enforces this by re-running a strategy on truncated data.
* Walk-forward: the best parameters on each training window are scored on
  the next, non-overlapping test window only.
* CSCV (Bailey et al., 2017) estimates the Probability of Backtest
  Overfitting: how often the in-sample winner ranks in the bottom half
  out of sample.
* The Deflated Sharpe Ratio discounts the best Sharpe ratio for the number
  of variants tried and for non-normal returns.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from typing import Callable

import numpy as np

from src.analytics.stats import TRADING_DAYS, kurtosis, normal_cdf, normal_ppf, sharpe, skewness

FAST = (5, 10, 15, 20, 30, 40, 50)
SLOW = (20, 30, 50, 75, 100, 150, 200, 250)
COST_PER_TRADE = 0.001
WALK_FORWARD_TRAIN = 504
WALK_FORWARD_TEST = 126
EULER_GAMMA = 0.5772156649015329

Strategy = Callable[[np.ndarray], np.ndarray]


class LookaheadError(AssertionError):
    """A strategy's past positions changed when future prices were removed."""


def moving_average(prices: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(prices), np.nan)
    if window <= len(prices):
        csum = np.cumsum(np.insert(prices, 0, 0.0))
        out[window - 1 :] = (csum[window:] - csum[:-window]) / window
    return out


def crossover_positions(prices: np.ndarray, fast: int, slow: int) -> np.ndarray:
    """1 (long) when the fast MA is above the slow MA at the close, else 0 (cash)."""
    fast_ma = moving_average(prices, fast)
    slow_ma = moving_average(prices, slow)
    return np.where(np.isnan(slow_ma), 0.0, (fast_ma > slow_ma).astype(float))


def strategy_returns(prices: np.ndarray, positions: np.ndarray, cost: float = COST_PER_TRADE) -> np.ndarray:
    """Daily returns of holding yesterday's position, net of a cost per position change."""
    asset = np.diff(prices) / prices[:-1]
    held = positions[:-1]
    trades = np.abs(np.diff(np.concatenate([[0.0], held])))
    return held * asset - trades * cost


def assert_causal(strategy: Strategy, prices: np.ndarray, checkpoints: int = 8) -> None:
    """Raise LookaheadError if any past position depends on later prices."""
    full = strategy(prices)
    for cut in np.linspace(len(prices) // 4, len(prices) - 1, checkpoints).astype(int):
        partial = strategy(prices[: cut + 1])
        if not np.array_equal(partial, full[: cut + 1]):
            raise LookaheadError(f"positions up to day {cut} change when later prices are removed")


def parameter_grid(fast: tuple[int, ...] = FAST, slow: tuple[int, ...] = SLOW) -> list[tuple[int, int]]:
    return [(f, s) for f in fast for s in slow if f < s]


def returns_matrix(prices: np.ndarray, grid: list[tuple[int, int]]) -> np.ndarray:
    """T × N matrix of daily strategy returns, one column per parameter pair."""
    return np.column_stack([strategy_returns(prices, crossover_positions(prices, f, s)) for f, s in grid])


@dataclass
class Fold:
    train: tuple[int, int]
    test: tuple[int, int]
    chosen: int
    train_sharpe: float
    test_sharpe: float


def walk_forward(
    matrix: np.ndarray,
    train: int = WALK_FORWARD_TRAIN,
    test: int = WALK_FORWARD_TEST,
    *,
    positions: np.ndarray | None = None,
    cost: float = COST_PER_TRADE,
) -> tuple[list[Fold], np.ndarray]:
    """Select on past returns, then stitch OOS holdings with actual boundary costs.

    Positions align with return rows (the holdings earning each row's return).
    Without positions, the caller's matrix is treated as already-accounted returns.
    """
    holdings = None if positions is None else np.asarray(positions, dtype=float)
    if holdings is not None and (
        holdings.shape != matrix.shape or not np.isfinite(holdings).all()
    ):
        raise ValueError("positions must be finite and align with the returns matrix")
    previous_holding = 0.0
    folds: list[Fold] = []
    oos: list[np.ndarray] = []
    start = 0
    while start + train + test <= len(matrix):
        tr = (start, start + train)
        te = (start + train, start + train + test)
        in_sample = [sharpe(matrix[tr[0] : tr[1], j]) for j in range(matrix.shape[1])]
        chosen = int(np.argmax(in_sample))
        test_returns = matrix[te[0] : te[1], chosen].copy()
        if holdings is not None:
            current_holding = float(holdings[te[0], chosen])
            variant_previous = float(holdings[te[0] - 1, chosen]) if te[0] else 0.0
            # Undo the standalone variant's boundary cost, then charge the
            # actual account's entry or switch from the previous OOS fold.
            test_returns[0] += cost * (
                abs(current_holding - variant_previous) - abs(current_holding - previous_holding)
            )
            previous_holding = float(holdings[te[1] - 1, chosen])
        folds.append(Fold(tr, te, chosen, in_sample[chosen], sharpe(test_returns)))
        oos.append(test_returns)
        start += test
    return folds, (np.concatenate(oos) if oos else np.array([]))


def cscv_pbo(matrix: np.ndarray, blocks: int = 10) -> tuple[float, list[float]]:
    """Probability of Backtest Overfitting by combinatorially symmetric cross-validation.

    Returns the PBO and the logit of the in-sample winner's out-of-sample
    relative rank for every split (negative logit = below the median).
    """
    if blocks % 2:
        raise ValueError("blocks must be even")
    n_obs, n_strategies = matrix.shape
    if n_strategies < 2:
        raise ValueError("need at least two strategies")
    usable = n_obs - n_obs % blocks
    chunks = np.array_split(np.arange(usable), blocks)
    logits: list[float] = []
    for combo in itertools.combinations(range(blocks), blocks // 2):
        is_rows = np.concatenate([chunks[i] for i in combo])
        oos_rows = np.concatenate([chunks[i] for i in range(blocks) if i not in combo])
        is_perf = np.array([sharpe(matrix[is_rows, j]) for j in range(n_strategies)])
        oos_perf = np.array([sharpe(matrix[oos_rows, j]) for j in range(n_strategies)])
        best = int(np.argmax(is_perf))
        # Relative rank in (0, 1): average rank of the winner among the OOS results.
        rank = (np.sum(oos_perf < oos_perf[best]) + 0.5 * (np.sum(oos_perf == oos_perf[best]) - 1) + 1) / (n_strategies + 1)
        logits.append(float(math.log(rank / (1 - rank))))
    pbo = float(np.mean(np.array(logits) <= 0))
    return pbo, logits


def expected_max_sharpe(variance_of_sharpes: float, n_trials: int) -> float:
    """Expected maximum of N Sharpe estimates under the null of zero skill (annualised units in, same out)."""
    if n_trials < 2:
        return 0.0
    sd = math.sqrt(max(variance_of_sharpes, 0.0))
    return sd * ((1 - EULER_GAMMA) * normal_ppf(1 - 1 / n_trials) + EULER_GAMMA * normal_ppf(1 - 1 / (n_trials * math.e)))


def deflated_sharpe(best_returns: np.ndarray, trial_sharpes: list[float], periods: int = TRADING_DAYS) -> dict[str, float]:
    """Probability that the best strategy's true Sharpe ratio exceeds what luck alone would produce."""
    r = np.asarray(best_returns, dtype=float)
    n = len(r)
    sr = sharpe(r, periods) / math.sqrt(periods)  # per-period Sharpe for the test statistic
    trials = np.asarray(trial_sharpes, dtype=float) / math.sqrt(periods)
    sr0 = expected_max_sharpe(float(trials.var(ddof=1)) if len(trials) > 1 else 0.0, len(trials))
    g3, g4 = skewness(r), kurtosis(r)
    denominator = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr**2, 1e-12))
    z = (sr - sr0) * math.sqrt(max(n - 1, 1)) / denominator
    return {
        "sharpe": sr * math.sqrt(periods),
        "benchmark_sharpe": sr0 * math.sqrt(periods),
        "dsr": normal_cdf(z),
        "trials": float(len(trials)),
    }
