"""Build data files consumed by the static website.

    python run_all.py --mode sample                 # reproducible test fixtures
    python run_all.py --mode api --require-api      # public historical data; fail closed
"""
from __future__ import annotations

import argparse
from pathlib import Path

from src.export_web import DEFAULT_OUT, export
from src.fetch_finmind import fetch_finmind
from src.fetch_market_data import fetch_market_data
from src.fetch_twse import fetch_twse
from src.fetch_yfinance import fetch_yfinance
from src.generate_sample_data import generate_sample_data
from src.preprocess import preprocess_data
from src.utils import ensure_project_dirs, load_config, project_path


def run(mode: str = "sample", out_dir: Path | None = None, *, require_api: bool = False) -> dict[str, str]:
    if require_api and mode != "api":
        raise ValueError("--require-api can only be used with --mode api")
    config = load_config()
    ensure_project_dirs(config)
    market_path = None
    twse_path = None
    if mode == "api":
        api = config.get("api", {})
        provider = api.get("provider", "url")
        if provider == "finmind":
            market_path = fetch_finmind(config)
            if market_path is not None:
                twse_path = fetch_twse(config)
        elif provider == "yfinance":
            market_path = fetch_yfinance(config, list(api.get("symbols", [])))
        else:
            market_path = fetch_market_data(config)
        if market_path is None:
            if require_api:
                raise RuntimeError("Required market API data is unavailable; refusing to build a sample-data release.")
            print("API mode could not fetch prices; falling back to sample data.")
    if market_path is None:
        generate_sample_data(config)
    effective = "api" if market_path is not None else "sample"
    cleaned = preprocess_data(config, mode=effective, market_path=market_path)
    target = out_dir or project_path(DEFAULT_OUT)
    hashes = export(target, cleaned_path=cleaned, twse_path=twse_path)
    print(f"Pipeline finished ({effective} data). Web data written to {target}")
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["sample", "api"], default="sample")
    parser.add_argument("--require-api", action="store_true", help="fail instead of falling back when API data is unavailable")
    args = parser.parse_args()
    if args.require_api:
        run(args.mode, require_api=True)
    else:
        run(args.mode)


if __name__ == "__main__":
    main()
