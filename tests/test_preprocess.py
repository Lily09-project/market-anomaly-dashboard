from __future__ import annotations

import pandas as pd
import pytest

from src import preprocess
from src.utils import load_config


def _config(tmp_path):
    config = load_config()
    config["data"] = {
        **config["data"],
        "raw_dir": str(tmp_path / "raw"),
        "sample_market_path": str(tmp_path / "sample" / "market.csv"),
        "cleaned_path": str(tmp_path / "processed" / "clean.csv"),
    }
    (tmp_path / "raw").mkdir()
    (tmp_path / "sample").mkdir()
    return config


ROWS = "date,symbol,open,high,low,close,volume\n2026-01-02,0050,1,2,1,2,3\n2026-01-02,0050,1,2,1,2.5,3\n2026-01-05,0050,1,2,1,-1,3\n"


def test_sample_mode_never_reads_raw_caches(tmp_path) -> None:
    config = _config(tmp_path)
    (tmp_path / "sample" / "market.csv").write_text(ROWS, encoding="utf-8")
    (tmp_path / "raw" / "market_raw.csv").write_text("not,a,valid,file\n", encoding="utf-8")
    cleaned = pd.read_csv(preprocess.preprocess_data(config, mode="sample"), dtype={"symbol": "string"})
    # Duplicate dates keep the last row; non-positive prices are dropped.
    assert cleaned[["date", "symbol", "close"]].values.tolist() == [["2026-01-02", "0050", 2.5]]
    assert cleaned["data_source"].tolist() == ["sample"]


def test_api_mode_uses_the_newest_raw_file_and_labels_it(tmp_path) -> None:
    config = _config(tmp_path)
    (tmp_path / "raw" / "market_raw.csv").write_text("日期,證券代號,開盤價,最高價,最低價,收盤價,成交股數\n2026-01-02,2330,1,2,1,1.5,\"1,000\"\n", encoding="utf-8")
    cleaned = pd.read_csv(preprocess.preprocess_data(config, mode="api"), dtype={"symbol": "string"})
    assert cleaned["symbol"].tolist() == ["2330"]
    assert cleaned["data_source"].tolist() == ["api"]


def test_api_mode_without_raw_falls_back_to_generated_sample(tmp_path) -> None:
    config = _config(tmp_path)
    cleaned = pd.read_csv(preprocess.preprocess_data(config, mode="api"))
    assert set(cleaned["data_source"]) == {"sample"}
    assert len(cleaned) > 1000


def test_invalid_mode_and_empty_input_fail(tmp_path) -> None:
    config = _config(tmp_path)
    with pytest.raises(ValueError, match="mode"):
        preprocess.preprocess_data(config, mode="live")
    (tmp_path / "sample" / "market.csv").write_text("date,symbol,open,high,low,close,volume\n2026-01-02,0050,1,2,1,0,3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="No usable"):
        preprocess.preprocess_data(config, mode="sample")
