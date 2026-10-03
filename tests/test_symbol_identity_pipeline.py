"""CSV ticker identities must survive every stage, including leading zeros."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from src.app_helpers import safe_load_csv
from src.evaluate import evaluate_model
from src.features import build_features
from src.fetch_market_data import _parse_response_payload, normalize_market_columns
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.train_anomaly_model import train_anomaly_model
from src.utils import load_config


@pytest.mark.parametrize("alias", ["symbol", "stock_id", "證券代號", "代號"])
def test_csv_response_preserves_ticker_alias_and_leading_zero(alias):
    csv = f"date,{alias},open,high,low,close,volume\n2025-01-02,0050,100,102,99,101,2000\n"
    frame = normalize_market_columns(_parse_response_payload(csv.encode("utf-8"), "text/csv"))
    assert frame["symbol"].tolist() == ["0050"]


def test_symbol_identity_survives_sample_to_model_and_application(tmp_path):
    cfg = copy.deepcopy(load_config())
    for section in ("data", "model", "reports"):
        for key, value in list(cfg[section].items()):
            if key.endswith(("_dir", "_path")) or (section == "model" and key == "path"):
                cfg[section][key] = str(tmp_path / value)
    cfg["data"]["start_date"] = "2025-01-01"
    cfg["data"]["end_date"] = "2025-06-30"
    expected = {"0050", "2330", "2317", "AAPL"}
    cfg["data"]["stock_symbols"] = sorted(expected)
    generate_sample_data(cfg)
    cleaned = preprocess_data(cfg)
    featured = build_features(cfg)
    train_anomaly_model(cfg)
    evaluate_model(cfg)
    for path in (cleaned, featured, cfg["data"]["results_path"]):
        assert set(pd.read_csv(path, dtype={"symbol": "string"})["symbol"]) == expected
        assert set(safe_load_csv(path)["symbol"]) == expected
    metrics = json.loads(Path(cfg["reports"]["anomaly_metrics_path"]).read_text(encoding="utf-8"))
    summary = json.loads(Path(cfg["reports"]["evaluation_summary_path"]).read_text(encoding="utf-8"))
    assert set(metrics["symbols"]) == set(summary["symbols"]) == expected
