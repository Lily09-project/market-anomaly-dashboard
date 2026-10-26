"""Run every analysis and write the JSON the static site reads.

Deterministic by construction: no wall-clock time, sorted keys, fixed
seeds and rounded floats, so two runs produce byte-identical files and the
manifest hashes can be checked in the browser.
"""
from __future__ import annotations

from src.corporate_actions import PRICE_BASIS

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.analytics import backtest, events, hmm, risk, stats
from src.generate_sample_data import CONTROL_SYMBOL, JUMPS_PER_STOCK, REBOUND_DAYS, REBOUND_PER_DAY, REGIMES
from src.utils import load_config, project_path

SCHEMA_VERSION = "2.1"
DEFAULT_OUT = Path("web/public/data")
N_STATES = 3
STATE_LABELS = ("平穩", "震盪", "高波動")
EVENT_Z = 5.0
IS_SHARE = 0.6
MIN_HISTORY_DAYS = backtest.WALK_FORWARD_TRAIN + backtest.WALK_FORWARD_TEST + 1
STRESS_DEFAULTS = {"horizon": 60, "block": 10, "paths": 2000, "seed": 20261024}
NAMES = {"0050": "元大台灣50", "2330": "台積電", "2317": "鴻海", CONTROL_SYMBOL: "隨機漫步對照組"}


class InsufficientHistoryError(ValueError):
    """Raised when a series is too short to fit, backtest and test honestly."""


def _num(value: float | None, digits: int = 6) -> float | None:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return None
    return round(float(value), digits)


def _nums(values, digits: int = 6) -> list[float | None]:
    return [_num(float(v), digits) for v in values]


def _write_json(path: Path, payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    path.write_text(text + "\n", encoding="utf-8", newline="\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _segments(states: np.ndarray) -> list[list[int]]:
    """Run-length encode a state path as [start, end, state] (inclusive)."""
    out: list[list[int]] = []
    start = 0
    for i in range(1, len(states) + 1):
        if i == len(states) or states[i] != states[start]:
            out.append([start, i - 1, int(states[start])])
            start = i
    return out


def _bic(log_likelihood: float, k: int, n: int) -> float:
    params = 2 * k + k * (k - 1) + (k - 1)
    return -2 * log_likelihood + params * math.log(n)


def _single_state_loglik(x: np.ndarray) -> float:
    var = max(float(x.var()), 1e-12)
    return float(np.sum(-0.5 * np.log(2 * math.pi * var) - 0.5 * (x - x.mean()) ** 2 / var))


def analyse_regimes(returns: np.ndarray, truth: np.ndarray | None) -> tuple[dict[str, Any], hmm.HMMResult, np.ndarray]:
    """Fit 1–3 state HMMs, keep the 3-state model for display and report BIC and accuracy."""
    prefilter = events.anomaly_days(pd.Series(returns)).to_numpy()
    x = returns.copy()
    x[prefilter] = np.nan  # jumps are studied separately; they would otherwise become a "state"
    observed = x[~np.isnan(x)]
    fits = {k: hmm.fit(x, k, seed=k) for k in (2, 3)}
    bic = {1: _bic(_single_state_loglik(observed), 1, len(observed))} | {k: _bic(f.log_likelihood, k, len(observed)) for k, f in fits.items()}
    chosen = min(bic, key=bic.get)
    model = fits[N_STATES]
    path = hmm.viterbi(x, model)
    probabilities = hmm.posterior(x, model)
    payload: dict[str, Any] = {
        "labels": list(STATE_LABELS),
        "means_annual": _nums(model.means * stats.TRADING_DAYS, 4),
        "vol_annual": _nums(np.sqrt(model.variances * stats.TRADING_DAYS), 4),
        "transition": [_nums(row, 4) for row in model.transition],
        "expected_days": _nums(model.expected_durations, 1),
        "share": _nums(np.bincount(path, minlength=N_STATES) / len(path), 4),
        "log_likelihood": [_num(v, 2) for v in model.history],
        "segments": _segments(path),
        "current": {"state": int(path[-1]), "probability": _num(float(probabilities[-1, path[-1]]), 3)},
        "bic": {str(k): _num(v, 1) for k, v in bic.items()},
        "bic_choice": int(chosen),
        "excluded_jump_days": int(prefilter.sum()),
        "accuracy": None,
        "confusion": None,
        "truth_segments": None,
    }
    if truth is not None:
        accuracy, perm = hmm.aligned_accuracy(path, truth, N_STATES)
        mapped = np.array(perm)[path]
        confusion = np.zeros((N_STATES, N_STATES), dtype=int)
        for t, p in zip(truth, mapped):
            confusion[t, p] += 1
        payload.update(accuracy=_num(accuracy, 4), confusion=confusion.tolist(), truth_segments=_segments(truth))
    return payload, model, x



EVENT_WARMUP = 252
EVENT_REFIT = 63
EVENT_LOOKBACK = 504


def causal_event_scores(returns: np.ndarray, warmup: int = EVENT_WARMUP) -> tuple[np.ndarray, np.ndarray]:
    """Quarterly refits use only prior returns; each scored block is held out."""
    values = np.asarray(returns, dtype=float)
    z = np.full(len(values), np.nan)
    states = np.zeros(len(values), dtype=int)
    for origin in range(warmup, len(values), EVENT_REFIT):
        history_start = max(0, origin-EVENT_LOOKBACK)
        end = min(origin+EVENT_REFIT, len(values))
        training = values[history_start:origin].copy()
        training[events.anomaly_days(pd.Series(training)).to_numpy()] = np.nan
        model = hmm.fit(training, N_STATES, n_init=2, max_iter=100, seed=31)
        block = values[history_start:end]
        block_z = hmm.predictive_z(block, model)
        offset = origin-history_start
        z[origin:end] = block_z[offset:]
        filtered = model.initial.copy()
        for index, value in enumerate(block):
            predicted = filtered if index == 0 else filtered @ model.transition
            if index >= offset:
                states[history_start+index] = int(np.argmax(predicted))
            likelihood = np.ones(N_STATES) if np.isnan(value) else np.maximum(
                np.exp(-0.5 * (value-model.means)**2/model.variances) / np.sqrt(2*np.pi*model.variances), 1e-300,
            )
            filtered = predicted * likelihood
            filtered /= filtered.sum()
    return z, states


def analyse_events(dates: list[str], returns: np.ndarray, model: hmm.HMMResult, path_states: list[list[int]], truth_dates: set[str] | None) -> tuple[dict[str, Any], list[np.ndarray], list[np.ndarray]]:
    # Retrospective display parameters and smoothed paths are not scoring inputs.
    z, state_at = causal_event_scores(returns)
    found, negatives, positives = [], [], []
    for i in np.flatnonzero(np.abs(np.nan_to_num(z)) > EVENT_Z):
        date = dates[i + 1]
        abnormal = events.abnormal_returns(returns, int(i))
        if abnormal is not None:
            (negatives if returns[i] < 0 else positives).append(abnormal)
        found.append(
            {
                "date": date,
                "return": _num(returns[i], 5),
                "z": _num(z[i], 2),
                "state": int(state_at[i]),
                "injected": (date in truth_dates) if truth_dates is not None else None,
                "car_post": _nums(np.cumsum(abnormal[1 - events.WINDOW[0] :]), 5) if abnormal is not None else None,
            }
        )
    return {"events": found}, negatives, positives


def _study_payload(abnormal: list[np.ndarray]) -> dict[str, Any]:
    s = events.study(abnormal)
    return {
        "n": s.n_events,
        "offsets": s.offsets,
        "car": _nums(s.mean_car, 5),
        "low": _nums(s.low, 5),
        "high": _nums(s.high, 5),
        "post_offsets": s.post_offsets,
        "post_car": _nums(s.post_car, 5),
        "post_low": _nums(s.post_low, 5),
        "post_high": _nums(s.post_high, 5),
    }


def _equity(returns: np.ndarray, step: int = 5) -> list[float | None]:
    curve = np.cumprod(1 + returns)
    return _nums(curve[::step], 4)


def analyse_backtest(dates: list[str], prices: np.ndarray) -> dict[str, Any]:
    if len(prices) < MIN_HISTORY_DAYS:
        raise InsufficientHistoryError(
            f"Need at least {MIN_HISTORY_DAYS} prices for a complete walk-forward test fold; got {len(prices)}."
        )
    grid = backtest.parameter_grid()
    matrix = backtest.returns_matrix(prices, grid)
    split = int(len(matrix) * IS_SHARE)
    in_sample = [stats.sharpe(matrix[:split, j]) for j in range(len(grid))]
    out_sample = [stats.sharpe(matrix[split:, j]) for j in range(len(grid))]
    full = [stats.sharpe(matrix[:, j]) for j in range(len(grid))]
    best_is = int(np.argmax(in_sample))
    best_full = int(np.argmax(full))
    fast, slow = grid[best_full]
    backtest.assert_causal(lambda p: backtest.crossover_positions(p, fast, slow), prices)
    positions = np.column_stack([backtest.crossover_positions(prices, f, s)[:-1] for f, s in grid])
    folds, oos = backtest.walk_forward(matrix, positions=positions)
    pbo, logits = backtest.cscv_pbo(matrix)
    dsr = backtest.deflated_sharpe(matrix[:, best_full], full)
    asset = np.diff(prices) / prices[:-1]
    first_oos = folds[0].test[0] if folds else len(asset)
    return {
        "fast": list(backtest.FAST),
        "slow": list(backtest.SLOW),
        "grid": [list(g) for g in grid],
        "cost_per_trade": backtest.COST_PER_TRADE,
        "split_date": dates[split + 1],
        "is_sharpe": _nums(in_sample, 3),
        "oos_sharpe": _nums(out_sample, 3),
        "full_sharpe": _nums(full, 3),
        "best_is": best_is,
        "best_full": best_full,
        "best_is_oos_rank": int(np.sum(np.array(out_sample) > out_sample[best_is])) + 1,
        "walk_forward": [
            {
                "train_start": dates[f.train[0] + 1],
                "test_start": dates[f.test[0] + 1],
                "test_end": dates[f.test[1]],
                "params": list(grid[f.chosen]),
                "train_sharpe": _num(f.train_sharpe, 3),
                "test_sharpe": _num(f.test_sharpe, 3),
            }
            for f in folds
        ],
        "oos_sharpe_stitched": _num(stats.sharpe(oos), 3),
        "buy_hold_sharpe_oos": _num(stats.sharpe(asset[first_oos : first_oos + len(oos)]), 3),
        "equity": {
            "start": dates[first_oos + 1],
            "step": 5,
            "walk_forward": _equity(oos),
            "buy_hold": _equity(asset[first_oos : first_oos + len(oos)]),
        },
        "pbo": _num(pbo, 3),
        "logits": _nums(logits, 3),
        "dsr": {k: _num(v, 4) for k, v in dsr.items()},
        "max_drawdown_best": _num(stats.max_drawdown(matrix[:, best_full]), 4),
        "causal_check": "passed",
    }


# Rounded so BLAS/SIMD last-bit differences between platforms cannot change the export.
PARITY_DIGITS = 12


def stress_parity(symbol: str, returns: np.ndarray) -> list[dict[str, Any]]:
    """Reference results the browser engine must reproduce."""
    cases = []
    for horizon, block, paths, seed in ((20, 5, 200, 7), (60, 10, 300, 11)):
        summary = risk.summarise(risk.block_bootstrap(returns, horizon, block, paths, seed))
        cases.append(
            {
                "symbol": symbol,
                "horizon": horizon,
                "block": block,
                "paths": paths,
                "seed": seed,
                "var95": _num(summary["var95"], PARITY_DIGITS),
                "cvar95": _num(summary["cvar95"], PARITY_DIGITS),
                "var99": _num(summary["var99"], PARITY_DIGITS),
                "cvar99": _num(summary["cvar99"], PARITY_DIGITS),
                "median_last": _num(summary["fan"]["0.5"][-1], PARITY_DIGITS),
            }
        )
    return cases


def _finmind_source_quality(config: dict[str, Any], provider: str, simulated: bool) -> dict[str, int] | None:
    """Bind public provenance to the validated raw FinMind snapshot and its exclusions."""
    if simulated or provider != "finmind":
        return None
    metadata_path = project_path(config["data"].get("source_metadata_path", "reports/metrics/source_metadata.json"))
    raw_path = project_path(Path(config["data"]["raw_dir"]) / "market_finmind.csv")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        raw_digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("FinMind source quality metadata is missing or unreadable.") from exc
    if not isinstance(metadata, dict) or metadata.get("provider") != "finmind" or metadata.get("status") != "success":
        raise ValueError("FinMind source quality metadata is invalid.")
    if metadata.get("is_simulated_data") is not False or metadata.get("data_source") != "API Data":
        raise ValueError("FinMind metadata does not identify a real public API source.")
    if metadata.get("data_file_sha256") != raw_digest:
        raise ValueError("FinMind source quality metadata does not match the raw data file.")
    counts = ("row_count", "source_row_count", "excluded_no_trade_rows")
    values: dict[str, int] = {}
    for key in counts:
        value = metadata.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("FinMind source quality metadata contains invalid row counts.")
        values[key] = value
    if values["row_count"] <= 0 or values["source_row_count"] != values["row_count"] + values["excluded_no_trade_rows"]:
        raise ValueError("FinMind source quality row counts are inconsistent.")
    return {
        "source_row_count": values["source_row_count"],
        "usable_price_rows": values["row_count"],
        "excluded_no_trade_rows": values["excluded_no_trade_rows"],
    }


def export(out_dir: Path, cleaned_path: Path | None = None) -> dict[str, str]:
    config = load_config()
    cleaned = pd.read_csv(cleaned_path or project_path(config["data"]["cleaned_path"]), dtype={"symbol": "string"})
    cleaned = cleaned.sort_values(["symbol", "date"], kind="stable")
    wide = cleaned.pivot(index="date", columns="symbol", values="close").sort_index().dropna()
    if len(wide) < MIN_HISTORY_DAYS:
        raise InsufficientHistoryError(f"Need at least {MIN_HISTORY_DAYS} common trading days; got {len(wide)}.")
    dates = list(wide.index)
    simulated = bool((cleaned.get("data_source", pd.Series(["sample"])) == "sample").all())
    provider = str(config.get("api", {}).get("provider", "unknown"))
    source_quality = _finmind_source_quality(config, provider, simulated)
    sample_dir = project_path(config["data"]["sample_market_path"]).parent
    truth_states = None
    truth_jumps: pd.DataFrame | None = None
    if simulated and (sample_dir / "regimes_truth.csv").exists():
        truth_frame = pd.read_csv(sample_dir / "regimes_truth.csv").set_index("date").reindex(dates)
        order = {r[0]: i for i, r in enumerate(REGIMES)}
        truth_states = truth_frame["state"].map(order).to_numpy()[1:].astype(int)
        truth_jumps = pd.read_csv(sample_dir / "injected_events.csv", dtype={"symbol": "string"})

    overview: dict[str, Any] = {"dates": dates, "symbols": []}
    regimes_payload: dict[str, Any] = {"labels": list(STATE_LABELS), "symbols": {}}
    events_payload: dict[str, Any] = {"threshold": EVENT_Z, "window": list(events.WINDOW), "symbols": {}}
    backtest_payload: dict[str, Any] = {"symbols": {}}
    stress_payload: dict[str, Any] = {"defaults": STRESS_DEFAULTS, "parity": []}
    pooled_negative: list[np.ndarray] = []
    pooled_positive: list[np.ndarray] = []
    control_events: list[np.ndarray] = []
    matched = injected_total = detected_total = 0

    for symbol in wide.columns:
        prices = wide[symbol].to_numpy(dtype=float)
        returns = np.diff(np.log(prices))
        is_control = symbol == CONTROL_SYMBOL
        truth = truth_states if truth_states is not None and not is_control else None
        regime, model, _ = analyse_regimes(returns, truth)
        jump_dates = set(truth_jumps.loc[truth_jumps["symbol"] == symbol, "date"]) if truth_jumps is not None else None
        event_info, negatives, positives = analyse_events(dates, returns, model, regime["segments"], jump_dates)
        if is_control:
            control_events += negatives + positives
        else:
            pooled_negative += negatives
            pooled_positive += positives
        if jump_dates is not None:
            matched += sum(1 for e in event_info["events"] if e["injected"])
            injected_total += len(jump_dates)
            detected_total += len(event_info["events"])
        losses = -(np.exp(returns) - 1)
        var95, cvar95 = risk.var_cvar(losses, 0.95)
        overview["symbols"].append(
            {
                "symbol": symbol,
                "name": NAMES.get(symbol, symbol),
                "is_control": is_control,
                "close": _nums(prices, 4),
                "total_return": _num(prices[-1] / prices[0] - 1, 4),
                "vol_annual": _num(returns.std(ddof=1) * math.sqrt(stats.TRADING_DAYS), 4),
                "sharpe": _num(stats.sharpe(np.exp(returns) - 1), 3),
                "max_drawdown": _num(stats.max_drawdown(np.exp(returns) - 1), 4),
                "var95_daily": _num(var95, 5),
                "cvar95_daily": _num(cvar95, 5),
            }
        )
        regimes_payload["symbols"][symbol] = regime
        events_payload["symbols"][symbol] = event_info
        backtest_payload["symbols"][symbol] = analyse_backtest(dates, prices)
        if symbol in ("0050", CONTROL_SYMBOL):
            stress_payload["parity"] += stress_parity(symbol, returns)

    events_payload["study"] = {"negative": _study_payload(pooled_negative), "positive": _study_payload(pooled_positive)}
    events_payload["control_events"] = len(control_events)
    events_payload["validation"] = (
        {
            "injected": injected_total,
            "detected": detected_total,
            "matched": matched,
            "recall": _num(matched / injected_total, 3) if injected_total else None,
            "precision": _num(matched / detected_total, 3) if detected_total else None,
            "truth_rebound": {"days": REBOUND_DAYS, "per_day": REBOUND_PER_DAY, "jumps_per_stock": JUMPS_PER_STOCK},
        }
        if truth_jumps is not None
        else None
    )

    input_bytes = Path(cleaned_path or project_path(config["data"]["cleaned_path"])).read_bytes()
    if simulated:
        source_label = "Reproducible synthetic test data"
        market_sources = [{"label": "Synthetic data generator (test fixture)", "url": "https://github.com/Lily09-project/market-anomaly-dashboard"}]
    elif provider == "finmind":
        source_label = "FinMind public historical daily prices"
        market_sources = [
            {"label": "FinMind API documentation (no-token public access)", "url": "https://finmind.github.io/quickstart/"},
            {"label": "0050 official 1:4 split reference (2025-06-18)", "url": "https://api.yuantafunds.com/ECImage/ECBackstage/file/2025-06-17/ca6610a73d444bc09bc2035df79bfd25.pdf"},
            {"label": "TaiwanStockPrice dataset fields and coverage", "url": "https://finmind.github.io/tutor/TaiwanMarket/Technical/"},
            {"label": "TWSE daily transaction dataset and open-data terms", "url": "https://data.gov.tw/dataset/11549"},
            {"label": "Government Open Data License 1.0", "url": "https://data.gov.tw/license"},
        ]
    else:
        source_label = "Configured market data API"
        market_sources = []
    provenance = {
        "data_source": source_label,
        "provider": provider,
        "is_simulated": simulated,
        "seed": int(config["project"]["random_state"]),
        "range": {"start": dates[0], "end": dates[-1]},
        "trading_days": len(dates),
        "symbols": list(wide.columns),
        "source_quality": source_quality,
        "price_basis": PRICE_BASIS if not simulated and provider == "finmind" else None,
        "input_sha256": hashlib.sha256(input_bytes).hexdigest(),
        "truth": {"regimes": truth_states is not None, "injected_events": truth_jumps is not None},
        "disclaimer": config["project"]["disclaimer"],
        "sources": market_sources + [
            {"label": "Bailey et al. (2017) The Probability of Backtest Overfitting", "url": "https://doi.org/10.21314/JCF.2016.322"},
            {"label": "Bailey & López de Prado (2014) The Deflated Sharpe Ratio", "url": "https://doi.org/10.3905/jpm.2014.40.5.094"},
        ],
    }

    files = {
        "overview.json": overview,
        "regimes.json": regimes_payload,
        "events.json": events_payload,
        "backtest.json": backtest_payload,
        "stress.json": stress_payload,
        "provenance.json": provenance,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    hashes = {name: _write_json(out_dir / name, payload) for name, payload in files.items()}
    _write_json(out_dir / "manifest.json", {"schema_version": SCHEMA_VERSION, "files": hashes})
    return hashes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    for name, digest in export(project_path(args.out)).items():
        print(f"{name} {digest}")


if __name__ == "__main__":
    main()
