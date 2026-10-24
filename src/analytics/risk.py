"""Value at Risk, Expected Shortfall and the block bootstrap stress test.

The browser runs the same block bootstrap in a Web Worker. Both sides use
the mulberry32 generator and the same draw order, so the exported parity
cases let the TypeScript tests check the browser engine against this
reference implementation.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

MASK = 0xFFFFFFFF
FAN_QUANTILES = (0.05, 0.25, 0.5, 0.75, 0.95)


def mulberry32(seed: int) -> Callable[[], float]:
    """Bit-for-bit port of the JavaScript mulberry32 generator."""
    state = seed & MASK

    def imul(a: int, b: int) -> int:
        return (a * b) & MASK

    def draw() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & MASK
        t = state
        t = imul(t ^ (t >> 15), t | 1)
        t = (t ^ ((t + imul(t ^ (t >> 7), t | 61)) & MASK)) & MASK
        return ((t ^ (t >> 14)) & MASK) / 4294967296

    return draw


def var_cvar(losses: np.ndarray, level: float) -> tuple[float, float]:
    """Historical VaR (loss quantile) and CVaR (mean loss at or beyond it); losses are positive."""
    x = np.asarray(losses, dtype=float)
    if x.size == 0:
        raise ValueError("no losses")
    var = float(np.quantile(x, level))
    tail = x[x >= var]
    return var, float(tail.mean())


def block_bootstrap(returns: np.ndarray, horizon: int, block: int, paths: int, seed: int) -> np.ndarray:
    """Simulated cumulative log returns, shape (paths, horizon)."""
    r = np.asarray(returns, dtype=float)
    n = len(r)
    if not 1 <= block <= n:
        raise ValueError("block length must be between 1 and the number of returns")
    rng = mulberry32(seed)
    out = np.empty((paths, horizon))
    for p in range(paths):
        total = 0.0
        filled = 0
        while filled < horizon:
            start = math.floor(rng() * (n - block + 1))
            for offset in range(min(block, horizon - filled)):
                total += r[start + offset]
                out[p, filled] = total
                filled += 1
    return out


def summarise(paths: np.ndarray) -> dict[str, object]:
    """Fan-chart quantiles of simple returns per day plus terminal VaR / CVaR."""
    simple = np.exp(paths) - 1
    losses = -simple[:, -1]
    var95, cvar95 = var_cvar(losses, 0.95)
    var99, cvar99 = var_cvar(losses, 0.99)
    return {
        "fan": {str(q): np.quantile(simple, q, axis=0).tolist() for q in FAN_QUANTILES},
        "var95": var95,
        "cvar95": cvar95,
        "var99": var99,
        "cvar99": cvar99,
    }
