from __future__ import annotations

import numpy as np
import pandas as pd

from src.market_screener import (
    SCORING_PROFILES,
    build_market_candidate,
    build_market_candidates,
    rank_market_candidates,
)


def make_history(direction: float, volatility: float, volume_boost: float = 1.0, rows: int = 120) -> pd.DataFrame:
    index = np.arange(rows, dtype=float)
    close = 120 + direction * index + np.sin(index * 0.65) * volatility
    volume = np.full(rows, 1_000_000.0)
    volume[-5:] *= volume_boost
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=rows),
            "open": close - 0.4,
            "high": close + 1.2,
            "low": close - 1.2,
            "close": close,
            "volume": volume,
            "symbol": "TEST",
        }
    )


def metadata(symbol: str, display: str, category: str = "半導體") -> dict[str, str]:
    return {"symbol": symbol, "display": display, "category": category}


def test_explainable_score_rewards_supported_trend_and_participation() -> None:
    strong = build_market_candidate(
        make_history(0.45, 1.8, volume_boost=1.8),
        metadata("2330.TW", "台積電"),
        "yfinance",
    )
    weak = build_market_candidate(
        make_history(-0.45, 8.0, volume_boost=0.55),
        metadata("TEST.TW", "測試公司"),
        "sample",
    )

    assert strong["data_quality"] == "ready"
    assert strong["total_score"] > weak["total_score"]
    assert set(strong["factor_scores"]) == {"trend", "momentum", "participation", "resilience"}
    assert strong["factor_scores"]["trend"] == 100.0
    assert strong["factor_scores"]["participation"] == 100.0
    assert strong["label"] == "證據完整"
    assert strong["stock_label"] == "2330.TW · 台積電"
    assert strong["source"] == "yfinance"


def test_profiles_change_weights_without_changing_factor_evidence() -> None:
    history = make_history(0.35, 15.0, volume_boost=0.6)
    balanced = build_market_candidate(history, metadata("AAPL", "Apple Inc."), "yfinance", "balanced")
    trend = build_market_candidate(history, metadata("AAPL", "Apple Inc."), "yfinance", "trend")
    defensive = build_market_candidate(history, metadata("AAPL", "Apple Inc."), "yfinance", "defensive")

    assert set(SCORING_PROFILES) == {"balanced", "trend", "momentum", "defensive"}
    assert balanced["factor_scores"] == trend["factor_scores"] == defensive["factor_scores"]
    assert trend["total_score"] > defensive["total_score"]
    assert balanced["profile"] == "balanced"


def test_insufficient_history_does_not_emit_false_precision() -> None:
    candidate = build_market_candidate(
        make_history(0.5, 1.0, rows=18),
        metadata("2330.TW", "台積電"),
        "sample",
    )

    assert candidate["data_quality"] == "unavailable"
    assert candidate["total_score"] is None
    assert candidate["factor_scores"] == {}
    assert candidate["coverage"] < 0.35
    assert "至少 60" in candidate["quality_note"]


def test_ranking_filters_unavailable_and_is_stable_for_ties() -> None:
    candidates = [
        {"symbol": "B", "total_score": 82.0, "data_quality": "ready"},
        {"symbol": "A", "total_score": 82.0, "data_quality": "ready"},
        {"symbol": "C", "total_score": 69.0, "data_quality": "ready"},
        {"symbol": "D", "total_score": None, "data_quality": "unavailable"},
    ]

    ranked = rank_market_candidates(candidates, minimum_score=70)

    assert [item["symbol"] for item in ranked] == ["A", "B"]
    assert [item["rank"] for item in ranked] == [1, 2]
    assert all(item["total_score"] >= 70 for item in ranked)


def test_batch_candidate_builder_preserves_universe_order_and_handles_missing_history() -> None:
    universe = [
        metadata("2330.TW", "台積電"),
        metadata("MISSING", "缺少資料"),
    ]
    histories = {
        "2330.TW": (make_history(0.4, 1.5), "yfinance"),
    }

    candidates = build_market_candidates(universe, histories, profile="trend")

    assert [candidate["symbol"] for candidate in candidates] == ["2330.TW", "MISSING"]
    assert candidates[0]["profile"] == "trend"
    assert candidates[0]["data_quality"] == "ready"
    assert candidates[1]["source"] == "unavailable"
    assert candidates[1]["data_quality"] == "unavailable"


def test_malformed_history_is_reported_as_unavailable_instead_of_crashing() -> None:
    malformed = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=80),
            "close": np.linspace(100, 120, 80),
        }
    )

    candidate = build_market_candidate(
        malformed,
        metadata("BROKEN", "欄位不完整"),
        "yfinance",
    )

    assert candidate["data_quality"] == "unavailable"
    assert candidate["total_score"] is None
    assert candidate["factor_scores"] == {}
    assert "欄位" in candidate["quality_note"]

def test_ranking_does_not_mix_live_and_demo_candidates() -> None:
    candidates = [
        {"symbol": "LIVE", "total_score": 70.0, "data_quality": "ready", "source": "yfinance"},
        {"symbol": "DEMO", "total_score": 95.0, "data_quality": "ready", "source": "sample"},
    ]

    ranked = rank_market_candidates(candidates)

    assert [item["symbol"] for item in ranked] == ["LIVE"]

def test_non_numeric_history_is_reported_as_unavailable() -> None:
    rows = 80
    invalid = pd.DataFrame(
        {
            "date": pd.bdate_range("2026-01-02", periods=rows),
            "high": ["invalid"] * rows,
            "low": ["invalid"] * rows,
            "close": ["invalid"] * rows,
            "volume": ["invalid"] * rows,
        }
    )

    candidate = build_market_candidate(
        invalid,
        metadata("BROKEN", "數值無效"),
        "yfinance",
    )

    assert candidate["data_quality"] == "unavailable"
    assert candidate["observations"] == 0
    assert "有效交易日" in candidate["quality_note"]

def test_duplicate_required_columns_are_reported_as_unavailable() -> None:
    history = make_history(0.4, 1.5)
    duplicated = pd.concat([history, history[["close"]]], axis=1)

    candidate = build_market_candidate(
        duplicated,
        metadata("BROKEN", "重複欄位"),
        "yfinance",
    )

    assert candidate["data_quality"] == "unavailable"
    assert candidate["total_score"] is None
    assert "重複" in candidate["quality_note"]
