from __future__ import annotations

import pandas as pd
import pytest

import run_all
from src import evaluate, preprocess


def test_fx_alignment_never_crosses_symbols_or_looks_forward():
    market = pd.DataFrame({"symbol": ["A", "A", "B", "B", "B"],
                           "date": pd.to_datetime(["2026-01-01", "2026-01-03", "2025-12-31", "2026-01-02", "2026-02-01"])})
    fx = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-01-03", "2026-01-03"]),
                       "currency_pair": ["USD_TWD", "USD_TWD", "ZZZ"], "exchange_rate": [31., 33., 999.]})
    actual = preprocess.merge_market_fx(market, fx, "USD_TWD")
    assert actual.loc[actual["symbol"].eq("B"), "exchange_rate"].tolist() == [31.]
    assert actual["date"].min() == pd.Timestamp("2026-01-01")
    prefix = preprocess.merge_market_fx(market, fx.iloc[:1], "USD_TWD")
    assert prefix.loc[prefix["date"].eq("2026-01-02"), "exchange_rate"].tolist() == [31.]
    with pytest.raises(ValueError, match="currency pair"):
        preprocess.merge_market_fx(market, fx, "EUR_TWD")


def test_sample_loaders_ignore_existing_raw(monkeypatch, tmp_path):
    market = tmp_path / "sample_market.csv"
    fx = tmp_path / "sample_fx.csv"
    market.write_text("date,symbol,open,high,low,close,volume\n2026-01-01,0050,1,2,1,2,3\n", encoding="utf-8")
    fx.write_text("date,currency_pair,exchange_rate\n2026-01-01,USD_TWD,31\n", encoding="utf-8")
    raw = tmp_path / "cached.csv"
    raw.write_text("invalid raw must not be read", encoding="utf-8")
    monkeypatch.setattr(preprocess, "_candidate_paths", lambda *args: [raw])
    cfg = {"data": {"raw_dir": str(tmp_path), "sample_market_path": str(market),
                    "sample_fx_path": str(fx), "currency_pair": "USD_TWD"}}
    assert preprocess._load_market(cfg, mode="sample")["symbol"].tolist() == ["0050"]
    assert preprocess._load_fx(cfg, mode="sample")["exchange_rate"].tolist() == [31.]


def test_pipeline_passes_explicit_fetch_paths(monkeypatch):
    calls = []
    monkeypatch.setattr(run_all, "load_config", lambda: {})
    monkeypatch.setattr(run_all, "ensure_project_dirs", lambda config: None)
    monkeypatch.setattr(run_all, "fetch_market_data", lambda config: "new-market.csv")
    monkeypatch.setattr(run_all, "fetch_fx_data", lambda config: "new-fx.csv")
    monkeypatch.setattr(run_all, "preprocess_data", lambda config, **kwargs: calls.append(kwargs))
    for name in ("build_features", "train_anomaly_model", "evaluate_model", "run_smoke_test"):
        monkeypatch.setattr(run_all, name, lambda config: None)
    run_all.run_pipeline("api")
    assert calls == [{"mode": "api", "market_path": "new-market.csv", "fx_path": "new-fx.csv"}]


@pytest.mark.parametrize("renderer", [evaluate._save_price_trend, evaluate._save_volatility_trend, evaluate._save_anomaly_cases])
def test_missing_plotter_fails_without_fabricated_image(monkeypatch, tmp_path, renderer):
    monkeypatch.setattr(evaluate, "plt", None)
    target = tmp_path / "report.png"
    with pytest.raises(RuntimeError, match="Chart rendering is unavailable"):
        renderer(pd.DataFrame(), target)
    assert not target.exists()


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_failed_render_invalidates_old_and_partial_outputs(monkeypatch, tmp_path, failed_index):
    figures = tmp_path / "figures"
    figures.mkdir()
    names = ("price_trend.png", "volatility_trend.png", "anomaly_cases.png")
    for name in names:
        (figures / name).write_bytes(b"previous-run")
    unrelated = figures / "user-notes.txt"
    unrelated.write_text("keep", encoding="utf-8")
    summary = tmp_path / "summary.json"
    summary.write_text('{"rows":999}', encoding="utf-8")
    source = tmp_path / "results.csv"
    pd.DataFrame({
        "date": ["2026-01-01"], "symbol": ["0050"], "close": [100.],
        "daily_return": [0.], "volume_zscore_20": [0.],
        "risk_score_baseline": [0.], "anomaly_score": [0.],
        "pseudo_anomaly": [0], "model_anomaly": [0], "zscore_baseline_anomaly": [0],
    }).to_csv(source, index=False)

    def renderer(index):
        def render(frame, path):
            path.write_bytes(b"this-run")
            if index == failed_index:
                raise RuntimeError("forced render failure")
        return render

    for index, name in enumerate(("_save_price_trend", "_save_volatility_trend", "_save_anomaly_cases")):
        monkeypatch.setattr(evaluate, name, renderer(index))
    config = {"data": {"results_path": str(source)},
              "reports": {"figures_dir": str(figures), "evaluation_summary_path": str(summary)}}
    with pytest.raises(RuntimeError, match="forced render failure"):
        evaluate.evaluate_model(config)
    assert all(not (figures / name).exists() for name in names)
    assert not summary.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"
