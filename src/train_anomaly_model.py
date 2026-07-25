from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
try:
    from sklearn.ensemble import IsolationForest
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
except Exception:
    IsolationForest = None
    Pipeline = None
    StandardScaler = None

from src.features import FEATURE_COLUMNS, build_features
from src import joblib_compat
from src.utils import ensure_parent, load_config, project_path, write_json


MODEL_FEATURES = [
    "daily_return",
    "abs_return",
    "log_return",
    "volume_change_rate",
    "volatility_5",
    "volatility_20",
    "price_ma_gap",
    "volume_zscore_20",
    "fx_return",
    "fx_rolling_volatility_5",
    "risk_score_baseline",
]


def precision_recall_f1(y_true: pd.Series, y_pred: pd.Series) -> tuple[float, float, float]:
    true_positive = int(((y_true == 1) & (y_pred == 1)).sum())
    false_positive = int(((y_true == 0) & (y_pred == 1)).sum())
    false_negative = int(((y_true == 1) & (y_pred == 0)).sum())
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


class QuantileAnomalyModel:
    def __init__(self, feature_columns: list[str], contamination: float = 0.06):
        self.feature_columns = feature_columns
        self.contamination = contamination
        self.center_: pd.Series | None = None
        self.scale_: pd.Series | None = None
        self.threshold_: float = 0.0

    def fit(self, X: pd.DataFrame) -> "QuantileAnomalyModel":
        self.center_ = X.median()
        self.scale_ = X.std().replace(0, 1).fillna(1)
        scores = self._score(X)
        self.threshold_ = float(np.quantile(scores, max(0.0, min(1.0, 1 - self.contamination))))
        return self

    def _score(self, X: pd.DataFrame) -> np.ndarray:
        if self.center_ is None or self.scale_ is None:
            raise RuntimeError("Model is not fitted.")
        z_values = ((X[self.feature_columns] - self.center_) / self.scale_).abs()
        return z_values.mean(axis=1).to_numpy()

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.where(self._score(X) >= self.threshold_, -1, 1)

    def decision_function(self, X: pd.DataFrame) -> np.ndarray:
        return self.threshold_ - self._score(X)


def add_pseudo_labels(df: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, group in df.groupby("symbol", sort=False):
        g = group.sort_values("date").copy()
        return_mean = g["abs_return"].rolling(20, min_periods=10).mean().shift(1)
        return_std = g["abs_return"].rolling(20, min_periods=10).std().shift(1)
        fx_std = g["fx_return"].abs().rolling(20, min_periods=10).std().shift(1)
        return_event = g["abs_return"] > (return_mean + 2.5 * return_std)
        volume_event = g["volume_zscore_20"] > 2.5
        fx_event = g["fx_return"].abs() > (2.5 * fx_std)
        g["pseudo_anomaly"] = (return_event | volume_event | fx_event).fillna(False).astype(int)
        z_score = (g["abs_return"] - return_mean) / return_std.replace(0, np.nan)
        g["zscore_baseline_anomaly"] = ((z_score > 2.5) | volume_event).fillna(False).astype(int)
        frames.append(g)
    return pd.concat(frames, ignore_index=True)


def train_anomaly_model(config: dict | None = None) -> Path:
    cfg = config or load_config()
    features_path = project_path(cfg["data"]["features_path"])
    if not features_path.exists():
        build_features(cfg)
    df = pd.read_csv(features_path, parse_dates=["date"]).sort_values(["symbol", "date"])
    df = add_pseudo_labels(df)
    X = df[MODEL_FEATURES].replace([np.inf, -np.inf], np.nan).fillna(0)

    if IsolationForest is not None and Pipeline is not None and StandardScaler is not None:
        model = Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                (
                    "isolation_forest",
                    IsolationForest(
                        n_estimators=200,
                        contamination=cfg["model"]["anomaly_contamination"],
                        random_state=cfg["model"]["random_state"],
                    ),
                ),
            ]
        )
        model_type = "IsolationForest"
    else:
        model = QuantileAnomalyModel(MODEL_FEATURES, cfg["model"]["anomaly_contamination"])
        model_type = "QuantileAnomalyModel fallback"
    model.fit(X)
    raw_prediction = model.predict(X)
    scores = model.decision_function(X)
    df["model_anomaly"] = (raw_prediction == -1).astype(int)
    df["anomaly_score"] = (-scores).round(6)
    df["risk_level"] = pd.cut(
        df["risk_score_baseline"],
        bins=[-0.01, 35, 70, 100],
        labels=["low", "medium", "high"],
    ).astype(str)

    y_true = df["pseudo_anomaly"]
    y_pred = df["model_anomaly"]
    precision, recall, f1 = precision_recall_f1(y_true, y_pred)
    metrics = {
        "rows": int(len(df)),
        "symbols": sorted(df["symbol"].astype(str).unique().tolist()),
        "model_type": model_type,
        "pseudo_anomaly_count": int(y_true.sum()),
        "model_anomaly_count": int(y_pred.sum()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "anomaly_rate": float(y_pred.mean()),
        "pseudo_label_positive_rate": float(y_true.mean()),
        "limitation_note": "Pseudo-labels are heuristic volatility flags, not ground-truth market labels.",
        "model_anomaly_rate": float(y_pred.mean()),
        "precision_vs_pseudo_label": float(precision),
        "recall_vs_pseudo_label": float(recall),
        "f1_vs_pseudo_label": float(f1),
        "baseline_anomaly_count": int(df["zscore_baseline_anomaly"].sum()),
        "limitation": "Pseudo-labels are heuristic volatility flags, not ground-truth market labels.",
        "feature_columns": MODEL_FEATURES,
    }

    model_path = ensure_parent(cfg["model"]["path"])
    joblib_compat.dump({"model": model, "features": MODEL_FEATURES, "metrics": metrics}, model_path)
    results_path = ensure_parent(cfg["data"]["results_path"])
    df.to_csv(results_path, index=False, encoding="utf-8")
    write_json(metrics, cfg["reports"]["anomaly_metrics_path"])
    return model_path


if __name__ == "__main__":
    print(train_anomaly_model())
