from __future__ import annotations

import argparse

from src.evaluate import evaluate_model
from src.features import build_features
from src.fetch_fx_data import fetch_fx_data
from src.fetch_market_data import fetch_market_data
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.smoke_test import run_smoke_test
from src.train_anomaly_model import train_anomaly_model
from src.utils import PROJECT_ROOT, ensure_project_dirs, load_config


def run_pipeline(mode: str = "sample") -> None:
    config = load_config()
    ensure_project_dirs(config)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Run mode: {mode}")
    if mode == "api":
        market_path = fetch_market_data(config)
        fx_path = fetch_fx_data(config)
        if not market_path or not fx_path:
            print("API mode did not fetch both datasets; using API/local cache where available and sample fallback for missing datasets.")
            generate_sample_data(config)
    else:
        generate_sample_data(config)

    cleaned = preprocess_data(config)
    features = build_features(config)
    model = train_anomaly_model(config)
    summary = evaluate_model(config)
    run_smoke_test(config)
    print("Pipeline completed.")
    print(f"Cleaned data: {cleaned}")
    print(f"Features: {features}")
    print(f"Model: {model}")
    print(f"Evaluation: {summary}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run market anomaly dashboard pipeline.")
    parser.add_argument("--mode", choices=["sample", "api"], default="sample")
    args = parser.parse_args()
    run_pipeline(args.mode)


if __name__ == "__main__":
    main()
