from __future__ import annotations

import pandas as pd

from src import joblib_compat
from src.features import build_features
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.train_anomaly_model import MODEL_FEATURES, train_anomaly_model
from src.utils import load_config, project_path


def test_model_training_generates_loadable_model() -> None:
    cfg = load_config()
    generate_sample_data(cfg)
    preprocess_data(cfg)
    build_features(cfg)
    model_path = train_anomaly_model(cfg)
    artifact = joblib_compat.load(model_path)
    results = pd.read_csv(project_path(cfg["data"]["results_path"]))
    sample = results[MODEL_FEATURES].head(10).fillna(0)
    prediction = artifact["model"].predict(sample)
    assert model_path.exists()
    assert len(prediction) == len(sample)
    assert {"model_anomaly", "pseudo_anomaly", "anomaly_score"} <= set(results.columns)
