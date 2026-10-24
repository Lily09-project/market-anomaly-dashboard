"""Optional yfinance adapter for real daily prices (``api.provider: yfinance``).

yfinance is not a runtime dependency of the demo: install it separately
(``pip install yfinance``) to use this adapter. Results are normalised to the
same columns as the sample data and written to ``data/raw`` for preprocess.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils import atomic_write_dataframe, ensure_parent, safe_exception_message

TIMEOUT_SECONDS = 15
RENAME = {"Date": "date", "Datetime": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
REQUIRED = ["date", "open", "high", "low", "close", "volume"]


def to_yfinance_symbol(symbol: str) -> str:
    """Taiwan listings use the ``.TW`` suffix on Yahoo Finance."""
    clean = str(symbol).strip()
    return f"{clean}.TW" if clean.isdigit() and 4 <= len(clean) <= 6 else clean.upper()


def normalize_download(history: pd.DataFrame | None, yf_symbol: str, symbol: str) -> pd.DataFrame:
    """Extract one ticker from a (possibly multi-index) download as clean daily rows."""
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=[*REQUIRED, "symbol"])
    data = history.copy()
    if isinstance(data.columns, pd.MultiIndex):
        first, second = data.columns.get_level_values(0), data.columns.get_level_values(1)
        if yf_symbol in first:
            data = data[yf_symbol].copy()
        elif yf_symbol in second:
            data = data.xs(yf_symbol, axis=1, level=1).copy()
        else:
            data.columns = first
    data = data.reset_index().rename(columns=RENAME)
    if any(column not in data.columns for column in REQUIRED):
        return pd.DataFrame(columns=[*REQUIRED, "symbol"])
    data = data[REQUIRED].copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for column in REQUIRED[1:]:
        data[column] = pd.to_numeric(data[column].astype(str).str.replace(",", "", regex=False), errors="coerce")
    data = data.dropna(subset=REQUIRED).sort_values("date").drop_duplicates(subset=["date"], keep="last")
    return data.assign(symbol=symbol).reset_index(drop=True)


def fetch_yfinance(config: dict[str, Any], symbols: list[str], module: Any = None) -> Path | None:
    """Download daily prices for ``symbols``; return the raw CSV path or None on any failure."""
    if module is None:
        try:
            import yfinance as module  # type: ignore[no-redef]
        except ImportError:
            print("yfinance is not installed; falling back to sample data.")
            return None
    tickers = {to_yfinance_symbol(s): s for s in symbols}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            downloaded = module.download(
                list(tickers),
                start=config["data"]["start_date"],
                end=config["data"]["end_date"],
                interval="1d",
                progress=False,
                auto_adjust=True,
                group_by="ticker",
                timeout=TIMEOUT_SECONDS,
            )
    except Exception as exc:
        print(f"yfinance download failed; falling back to sample data. Reason: {safe_exception_message(exc)}")
        return None
    frames = [normalize_download(downloaded, ticker, symbol) for ticker, symbol in tickers.items()]
    if any(frame.empty for frame in frames):
        print("yfinance returned no rows for at least one symbol; falling back to sample data.")
        return None
    out = ensure_parent(Path(config["data"]["raw_dir"]) / "market_yfinance.csv")
    return atomic_write_dataframe(pd.concat(frames, ignore_index=True), out)
