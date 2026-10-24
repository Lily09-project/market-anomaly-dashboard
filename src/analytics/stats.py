"""Small statistical helpers shared by the analytics modules."""
from __future__ import annotations

import math

import numpy as np

TRADING_DAYS = 252


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation, |error| < 1.2e-9)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = (-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02, 1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00)
    b = (-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02, 6.680131188771972e01, -1.328068155288572e01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00, -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00)
    d = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00)
    low = 0.02425
    if p < low:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - low:
        return -normal_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def sharpe(returns: np.ndarray, periods: int = TRADING_DAYS) -> float:
    """Annualised Sharpe ratio of daily returns (risk-free rate taken as zero)."""
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd * math.sqrt(periods)) if sd > 0 else 0.0


def max_drawdown(returns: np.ndarray) -> float:
    """Largest peak-to-trough fall of the compounded equity curve, as a positive fraction."""
    equity = np.cumprod(1 + np.asarray(returns, dtype=float))
    if equity.size == 0:
        return 0.0
    peaks = np.maximum.accumulate(np.concatenate([[1.0], equity]))[1:]
    return float(np.max(1 - equity / peaks))


def skewness(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    sd = x.std()
    return float(np.mean((x - x.mean()) ** 3) / sd**3) if sd > 0 else 0.0


def kurtosis(x: np.ndarray) -> float:
    """Non-excess kurtosis (3 for a normal distribution)."""
    x = np.asarray(x, dtype=float)
    sd = x.std()
    return float(np.mean((x - x.mean()) ** 4) / sd**4) if sd > 0 else 3.0
