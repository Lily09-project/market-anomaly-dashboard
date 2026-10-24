"""Reproducible synthetic market data with known answers.

Every series is driven by one market-wide regime chain (calm / choppy /
turbulent) so the HMM has a ground truth to recover. Each stock also gets
injected jump days; after a negative jump the price partly rebounds over the
next days, which the event study should find. A pure random walk is included
as a control series: any strategy that "works" on it is overfitting.

Nothing reads the wall clock, so the files are byte-for-byte identical on
every run.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.utils import atomic_write_dataframe, ensure_parent, load_config

# (label, daily mean, daily volatility, probability of staying)
REGIMES: tuple[tuple[str, float, float, float], ...] = (
    ("calm", 0.0008, 0.006, 0.985),
    ("choppy", 0.0, 0.013, 0.97),
    ("turbulent", -0.002, 0.028, 0.95),
)
# symbol: (beta to the market, idiosyncratic volatility, starting price)
STOCKS: dict[str, tuple[float, float, float]] = {
    "0050": (1.0, 0.002, 120.0),
    "2330": (1.25, 0.005, 580.0),
    "2317": (0.9, 0.003, 105.0),
}
CONTROL_SYMBOL = "RANDOM"
CONTROL_PARAMS = (0.0, 0.012, 100.0)  # (mean, volatility, starting price)
JUMPS_PER_STOCK = 20
JUMP_SIGMAS = 9.0
REBOUND_DAYS = 3
REBOUND_PER_DAY = 0.004


def _regime_path(rng: np.random.Generator, n: int) -> np.ndarray:
    k = len(REGIMES)
    states = np.empty(n, dtype=int)
    states[0] = 0
    for t in range(1, n):
        stay = REGIMES[states[t - 1]][3]
        if rng.random() < stay:
            states[t] = states[t - 1]
        else:
            others = [s for s in range(k) if s != states[t - 1]]
            states[t] = others[int(rng.integers(len(others)))]
    return states


def _ohlcv(rng: np.random.Generator, returns: np.ndarray, start: float) -> dict[str, np.ndarray]:
    close = start * np.exp(np.cumsum(returns))
    previous = np.concatenate([[start], close[:-1]])
    open_ = previous * np.exp(rng.normal(0, 0.002, len(returns)))
    spread = np.abs(rng.normal(0.004, 0.002, len(returns)))
    high = np.maximum(open_, close) * (1 + spread)
    low = np.minimum(open_, close) * (1 - spread)
    volume = (3_000_000 * np.exp(rng.normal(0, 0.25, len(returns))) * (1 + 40 * np.abs(returns))).astype(int)
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def simulate(config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (prices, regime truth, injected jumps)."""
    rng = np.random.default_rng(int(config["project"]["random_state"]))
    dates = pd.bdate_range(config["data"]["start_date"], config["data"]["end_date"])
    n = len(dates)
    states = _regime_path(rng, n)
    mu = np.array([r[1] for r in REGIMES])[states]
    sigma = np.array([r[2] for r in REGIMES])[states]
    market = rng.normal(mu, sigma)

    frames: list[pd.DataFrame] = []
    jumps: list[dict[str, object]] = []
    for symbol, (beta, idio, start) in STOCKS.items():
        returns = beta * market + rng.normal(0, idio, n)
        # Jumps avoid the first year (estimation window) and the last weeks (event window).
        candidates = np.arange(260, n - 15)
        days = np.sort(rng.choice(candidates, size=JUMPS_PER_STOCK, replace=False))
        for day in days:
            direction = 1 if rng.random() < 0.5 else -1
            size = direction * JUMP_SIGMAS * float(sigma[day]) * beta
            returns[day] += size
            if direction < 0:
                returns[day + 1 : day + 1 + REBOUND_DAYS] += REBOUND_PER_DAY
            jumps.append({"date": dates[day].strftime("%Y-%m-%d"), "symbol": symbol, "direction": direction, "size": round(size, 6)})
        frames.append(pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "symbol": symbol, **_ohlcv(rng, returns, start)}))

    # The control is demeaned so its realised drift is exactly zero: there is no trend to find.
    drift, vol, start = CONTROL_PARAMS
    control = rng.normal(drift, vol, n)
    control -= control.mean()
    frames.append(pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "symbol": CONTROL_SYMBOL, **_ohlcv(rng, control, start)}))

    prices = pd.concat(frames, ignore_index=True)
    for column in ("open", "high", "low", "close"):
        prices[column] = prices[column].round(4)
    truth = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "state": [REGIMES[s][0] for s in states]})
    return prices, truth, pd.DataFrame(jumps).sort_values(["date", "symbol"]).reset_index(drop=True)


def generate_sample_data(config: dict | None = None) -> Path:
    cfg = config or load_config()
    prices, truth, jumps = simulate(cfg)
    market_path = ensure_parent(cfg["data"]["sample_market_path"])
    sample_dir = market_path.parent
    atomic_write_dataframe(prices, market_path)
    atomic_write_dataframe(truth, sample_dir / "regimes_truth.csv")
    atomic_write_dataframe(jumps, sample_dir / "injected_events.csv")
    return market_path


if __name__ == "__main__":
    print(f"Generated {generate_sample_data()}")
