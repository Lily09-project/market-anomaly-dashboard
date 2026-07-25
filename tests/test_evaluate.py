from __future__ import annotations

import json

from src.evaluate import evaluate_model
from src.train_anomaly_model import train_anomaly_model
from src.utils import load_config, project_path


def test_evaluate_generates_metrics_files() -> None:
    cfg = load_config()
    train_anomaly_model(cfg)
    summary_path = evaluate_model(cfg)
    anomaly_metrics_path = project_path(cfg["reports"]["anomaly_metrics_path"])
    assert summary_path.exists()
    assert anomaly_metrics_path.exists()

    with anomaly_metrics_path.open("r", encoding="utf-8") as f:
        anomaly_metrics = json.load(f)
    assert {"precision", "recall", "f1", "anomaly_rate", "limitation_note"} <= set(anomaly_metrics)
    assert anomaly_metrics["precision"] is not None

    with summary_path.open("r", encoding="utf-8") as f:
        summary = json.load(f)
    assert "model" in summary
    assert "top_anomaly_cases" in summary

