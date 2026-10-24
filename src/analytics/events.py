"""Anomaly days and an event study of what happens after them.

An anomaly day is a return whose robust z-score, measured against the
previous 60 trading days only (median and MAD, so the window is causal), is
beyond the threshold. Abnormal returns use the mean-adjusted model: the
return minus the stock's average return over an estimation window that ends
before the event window starts. Cumulative abnormal returns (CAR) are
averaged across events and given a percentile-bootstrap 95% interval by
resampling events.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LOOKBACK = 60
Z_THRESHOLD = 5.0
MAD_TO_SD = 1.4826
WINDOW = (-5, 10)
ESTIMATION = (-120, -11)
BOOTSTRAP_DRAWS = 2000


def robust_z(returns: pd.Series, lookback: int = LOOKBACK) -> pd.Series:
    """z-score of each return against the median and MAD of the previous `lookback` days."""
    median = returns.rolling(lookback, min_periods=lookback // 3).median().shift(1)
    mad = (returns - median).abs().rolling(lookback, min_periods=lookback // 3).median().shift(1) * MAD_TO_SD
    return (returns - median) / mad.where(mad > 0)


def anomaly_days(returns: pd.Series, threshold: float = Z_THRESHOLD) -> pd.Series:
    """Boolean mask of anomaly days."""
    return robust_z(returns).abs() > threshold


def abnormal_returns(returns: np.ndarray, event_index: int, window: tuple[int, int] = WINDOW, estimation: tuple[int, int] = ESTIMATION) -> np.ndarray | None:
    """Mean-adjusted abnormal returns over the event window, or None if the windows do not fit."""
    start, end = event_index + window[0], event_index + window[1]
    est_start, est_end = event_index + estimation[0], event_index + estimation[1]
    if est_start < 0 or end >= len(returns):
        return None
    baseline = returns[est_start : est_end + 1]
    baseline = baseline[~np.isnan(baseline)]
    if baseline.size < 20:
        return None
    return returns[start : end + 1] - baseline.mean()


@dataclass
class EventStudy:
    offsets: list[int]
    mean_car: list[float]
    low: list[float]
    high: list[float]
    post_offsets: list[int]
    post_car: list[float]
    post_low: list[float]
    post_high: list[float]
    n_events: int


def _bootstrap(paths: np.ndarray, draws: int, rng: np.random.Generator) -> tuple[list[float], list[float], list[float]]:
    picks = rng.integers(0, len(paths), size=(draws, len(paths)))
    boot = paths[picks].mean(axis=1)
    return paths.mean(axis=0).tolist(), np.quantile(boot, 0.025, axis=0).tolist(), np.quantile(boot, 0.975, axis=0).tolist()


def study(abnormal: list[np.ndarray], window: tuple[int, int] = WINDOW, draws: int = BOOTSTRAP_DRAWS, seed: int = 0) -> EventStudy:
    """Average CAR paths with percentile-bootstrap intervals over events.

    ``mean_car`` accumulates from the start of the window (it includes the
    event day itself); ``post_car`` accumulates from the day after the event,
    which is the part an investor could actually have traded on.
    """
    offsets = list(range(window[0], window[1] + 1))
    post_offsets = [o for o in offsets if o > 0]
    if not abnormal:
        nan, post_nan = [float("nan")] * len(offsets), [float("nan")] * len(post_offsets)
        return EventStudy(offsets, nan, nan, nan, post_offsets, post_nan, post_nan, post_nan, 0)
    ar = np.vstack(abnormal)
    rng = np.random.default_rng(seed)
    mean_car, low, high = _bootstrap(np.cumsum(ar, axis=1), draws, rng)
    first_post = offsets.index(1)
    post_car, post_low, post_high = _bootstrap(np.cumsum(ar[:, first_post:], axis=1), draws, rng)
    return EventStudy(offsets, mean_car, low, high, post_offsets, post_car, post_low, post_high, len(ar))
