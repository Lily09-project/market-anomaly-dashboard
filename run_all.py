"""One command from data to the files the web app reads.

    python run_all.py --mode sample   # reproducible synthetic data (default)
    python run_all.py --mode api      # api.provider (url or yfinance), falls back to sample data
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.export_web import DEFAULT_OUT, export
from src.fetch_market_data import fetch_market_data
from src.fetch_yfinance import fetch_yfinance
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.utils import ensure_project_dirs, load_config, project_path


def run(mode: str = "sample", out_dir: Path | None = None) -> dict[str, str]:
    config = load_config()
    ensure_project_dirs(config)
    market_path = None
    if mode == "api":
        api = config.get("api", {})
        if api.get("provider") == "yfinance":
            market_path = fetch_yfinance(config, list(api.get("symbols", [])))
        else:
            market_path = fetch_market_data(config)
        if market_path is None:
            print("API mode could not fetch prices; falling back to sample data.")
    if market_path is None:
        generate_sample_data(config)
    effective = "api" if market_path is not None else "sample"
    cleaned = preprocess_data(config, mode=effective, market_path=market_path)
    target = out_dir or project_path(DEFAULT_OUT)
    hashes = export(target, cleaned_path=cleaned)
    print(f"Pipeline finished ({effective} data). Web data written to {target}")
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["sample", "api"], default="sample")
    args = parser.parse_args()
    run(args.mode)


if __name__ == "__main__":
    main()
