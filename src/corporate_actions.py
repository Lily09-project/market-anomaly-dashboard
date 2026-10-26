"""Verified corporate-action normalization for the raw FinMind price dataset.

Keep downloaded OHLCV unchanged. Analysis uses split-adjusted prices and
reciprocal volumes; cash dividends are not reinvested.
"""
from __future__ import annotations

import pandas as pd

SPLIT_SOURCE = "https://api.yuantafunds.com/ECImage/ECBackstage/file/2025-06-17/ca6610a73d444bc09bc2035df79bfd25.pdf"
SPLIT_DATE = pd.Timestamp("2025-06-18")
PRICE_BASIS = {
    "kind": "known_split_adjusted",
    "cash_dividends_reinvested": False,
    "splits": [{"symbol": "0050", "effective_date": "2025-06-18", "new_units_per_old": 4, "source": SPLIT_SOURCE}],
}


def adjust_finmind_splits(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply only the verified 0050 1:4 split, once, to raw input.

    Reject an unexpected/already-adjusted boundary instead of guessing a
    corporate action from an outlier. Other symbols and sample data are untouched.
    """
    adjusted = frame.copy(deep=True)
    dates = pd.to_datetime(adjusted["date"])
    symbol = adjusted["symbol"].astype(str).eq("0050")
    before = symbol & dates.lt(SPLIT_DATE)
    after = symbol & dates.ge(SPLIT_DATE)
    if not before.any() or not after.any():
        return adjusted
    previous = adjusted.loc[before].assign(_date=dates[before]).sort_values("_date").iloc[-1]
    following = adjusted.loc[after].assign(_date=dates[after]).sort_values("_date").iloc[0]
    boundary_ratio = float(previous["close"]) / float(following["close"])
    if not 2.5 < boundary_ratio < 6.0:
        raise ValueError("0050 split boundary is inconsistent with raw FinMind prices; refusing to double-adjust or guess.")
    for column in ("open", "high", "low", "close"):
        adjusted[column] = adjusted[column].astype(float)
        adjusted.loc[before, column] = adjusted.loc[before, column] / 4.0
    adjusted["volume"] = adjusted["volume"].astype(float)
    adjusted.loc[before, "volume"] = adjusted.loc[before, "volume"] * 4.0
    return adjusted
