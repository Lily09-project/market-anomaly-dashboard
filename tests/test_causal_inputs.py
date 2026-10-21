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
