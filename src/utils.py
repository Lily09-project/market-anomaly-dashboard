from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "name": "Taiwan Stock and Exchange Rate Anomaly Detection Dashboard",
        "short_name": "market-anomaly-dashboard",
        "random_state": 42,
        "sample_mode": True,
        "disclaimer": "本專案僅供資料分析與技術展示，不構成任何投資建議。",
    },
    "data": {
        "stock_symbols": ["0050", "2330", "2317"],
        "currency_pair": "USD_TWD",
        "start_date": "2021-01-01",
        "end_date": "2025-12-31",
        "raw_dir": "data/raw",
        "sample_dir": "data/sample",
        "processed_dir": "data/processed",
        "sample_market_path": "data/sample/sample_market.csv",
        "sample_fx_path": "data/sample/sample_fx.csv",
        "cleaned_path": "data/processed/market_cleaned.csv",
        "features_path": "data/processed/market_features.csv",
        "results_path": "data/processed/market_anomaly_results.csv",
    },
    "model": {
        "path": "models/market_anomaly_detector.joblib",
        "anomaly_contamination": 0.06,
        "random_state": 42,
    },
    "reports": {
        "metrics_dir": "reports/metrics",
        "figures_dir": "reports/figures",
        "anomaly_metrics_path": "reports/metrics/anomaly_metrics.json",
        "evaluation_summary_path": "reports/metrics/evaluation_summary.json",
    },
    "api": {
        "timeout_seconds": 15,
        "market_url": "",
        "fx_url": "",
        "twse_company_profile_url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
        "twse_esg_legal_url": "https://openapi.twse.com.tw/v1/opendata/t187ap46_L_20",
    },
    "dashboard": {
        "theme_name": "charcoal_orange",
        "dark_theme_name": "charcoal_orange",
        "light_theme_name": "paper_orange",
    },
}


def load_config(config_path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    if yaml is None:
        return copy.deepcopy(DEFAULT_CONFIG)
    with Path(config_path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def ensure_parent(path: str | Path) -> Path:
    resolved = project_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def ensure_project_dirs(config: dict[str, Any] | None = None) -> None:
    cfg = config or load_config()
    for key in ["raw_dir", "sample_dir", "processed_dir"]:
        project_path(cfg["data"][key]).mkdir(parents=True, exist_ok=True)
    project_path("models").mkdir(parents=True, exist_ok=True)
    project_path(cfg["reports"]["metrics_dir"]).mkdir(parents=True, exist_ok=True)
    project_path(cfg["reports"]["figures_dir"]).mkdir(parents=True, exist_ok=True)


def clean_numeric(value: Any) -> float | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text in {"--", "-", "NA", "N/A", "null", "None"}:
        return None
    text = re.sub(r"[,，$％%]", "", text)
    text = re.sub(r"[^\d.\-]", "", text)
    if text in {"", "-", "."}:
        return None
    return float(text)


def parse_date(value: Any) -> pd.Timestamp | pd.NaT:
    if pd.isna(value):
        return pd.NaT
    text = str(value).strip()
    if not text:
        return pd.NaT
    roc_match = re.match(r"^(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})$", text)
    if roc_match:
        year, month, day = map(int, roc_match.groups())
        if year < 1911:
            return pd.Timestamp(year + 1911, month, day)
    return pd.to_datetime(text, errors="coerce")


def write_json(data: dict[str, Any], path: str | Path) -> Path:
    out = ensure_parent(path)
    with out.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return out


def read_existing_csv(paths: list[Path]) -> pd.DataFrame | None:
    for path in paths:
        if path.exists() and path.stat().st_size > 0:
            return pd.read_csv(path)
    return None
