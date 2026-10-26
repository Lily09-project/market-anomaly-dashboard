from __future__ import annotations

import pandas as pd
import pytest

from src.corporate_actions import adjust_finmind_splits
from src import preprocess
from src.utils import load_config


def prices():
    return pd.DataFrame({
        "date": ["2025-06-10", "2025-06-18", "2025-06-10", "2025-06-18"],
        "symbol": ["0050", "0050", "2330", "2330"],
        "open": [188, 47, 1000, 1001], "high": [190, 48, 1005, 1006],
        "low": [187, 46, 995, 996], "close": [188.65, 47.16, 1001, 1002],
        "volume": [100, 400, 200, 201],
    })


def test_verified_split_preserves_notional_and_other_symbol():
    raw = prices()
    original = raw.copy(deep=True)
    result = adjust_finmind_splits(raw)
    pd.testing.assert_frame_equal(raw, original)
    for column in ("open", "high", "low", "close"):
        assert result.loc[0, column] == pytest.approx(raw.loc[0, column] / 4)
        assert result.loc[1, column] == raw.loc[1, column]
    assert result.loc[0, "volume"] == 400
    assert result.loc[0, "close"] * result.loc[0, "volume"] == pytest.approx(raw.loc[0, "close"] * raw.loc[0, "volume"])
    assert result.loc[1, "close"] / result.loc[0, "close"] - 1 == pytest.approx(47.16 / (188.65 / 4) - 1)
    pd.testing.assert_frame_equal(result.loc[2:].reset_index(drop=True), raw.loc[2:].astype({key: float for key in ("open", "high", "low", "close", "volume")}).reset_index(drop=True))


@pytest.mark.parametrize("positions", [[0], [1], [2, 3]])
def test_one_sided_or_unrelated_history_is_unchanged(positions):
    raw = prices().iloc[positions]
    pd.testing.assert_frame_equal(adjust_finmind_splits(raw), raw)


def test_already_adjusted_input_is_rejected_instead_of_double_adjusted():
    adjusted = adjust_finmind_splits(prices())
    with pytest.raises(ValueError, match="refusing"):
        adjust_finmind_splits(adjusted)


@pytest.mark.parametrize("mode,provider,expected", [("sample", "finmind", 188.65), ("api", "yfinance", 188.65), ("api", "finmind", 47.1625)])
def test_pipeline_applies_split_only_to_raw_finmind(tmp_path, mode, provider, expected):
    config = load_config()
    config["api"]["provider"] = provider
    config["data"]["sample_market_path"] = str(tmp_path / "sample.csv")
    config["data"]["cleaned_path"] = str(tmp_path / "cleaned.csv")
    raw = tmp_path / "raw.csv"
    prices().to_csv(raw, index=False)
    prices().to_csv(config["data"]["sample_market_path"], index=False)
    output = preprocess.preprocess_data(config, mode=mode, market_path=raw if mode == "api" else None)
    cleaned = pd.read_csv(output, dtype={"symbol": "string"})
    close = cleaned.loc[(cleaned["symbol"] == "0050") & (cleaned["date"] == "2025-06-10"), "close"].iloc[0]
    assert close == pytest.approx(expected)
