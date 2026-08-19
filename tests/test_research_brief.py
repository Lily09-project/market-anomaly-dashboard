from __future__ import annotations

from datetime import date

import pandas as pd

from src.research_brief import build_research_brief


def make_history(rows: int = 60, include_volume: bool = True) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=rows)
    close = pd.Series(range(100, 100 + rows), dtype="float64")
    data = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "symbol": "2330.TW",
        }
    )
    if include_volume:
        data["volume"] = 1_000_000
    return data


def test_complete_history_exposes_quality_and_four_evidence_sections() -> None:
    brief = build_research_brief(make_history(), "yfinance", [], "半導體")

    assert brief["data_quality"]["state"] == "ready"
    assert brief["data_quality"]["latest_date"] == "2026-03-25"
    assert [item["id"] for item in brief["evidence"]] == ["trend", "momentum", "participation", "risk"]
    assert all(item["state"] != "unavailable" for item in brief["evidence"])
    assert brief["coherence"]["status"] in {"aligned", "mixed", "divergent", "risk-heavy"}


def test_short_history_marks_technical_evidence_unavailable() -> None:
    brief = build_research_brief(make_history(rows=12), "sample", [], "半導體")

    assert brief["data_quality"]["state"] == "caution"
    assert any("DEMO 示範資料" in warning for warning in brief["data_quality"]["warnings"])
    assert all(item["state"] == "unavailable" for item in brief["evidence"])


def test_missing_volume_keeps_other_evidence_and_marks_participation_unavailable() -> None:
    brief = build_research_brief(make_history(include_volume=False), "yfinance", [], "半導體")
    evidence = {item["id"]: item for item in brief["evidence"]}

    assert evidence["trend"]["state"] != "unavailable"
    assert evidence["participation"]["state"] == "unavailable"


def test_peer_context_requires_two_comparable_cards() -> None:
    brief = build_research_brief(make_history(), "yfinance", [{"symbol": "2330.TW"}], "半導體")

    assert brief["peer_context"]["state"] == "unavailable"


def test_peer_context_reports_rank_when_cards_are_comparable() -> None:
    peers = [
        {
            "symbol": "2330.TW",
            "change_pct": 2.0,
            "latest_close": 110.0,
            "high_52w": 120.0,
            "low_52w": 80.0,
            "volume": 200.0,
            "avg_volume": 100.0,
        },
        {
            "symbol": "2454.TW",
            "change_pct": 1.0,
            "latest_close": 90.0,
            "high_52w": 120.0,
            "low_52w": 80.0,
            "volume": 100.0,
            "avg_volume": 100.0,
        },
        {
            "symbol": "2303.TW",
            "change_pct": -1.0,
            "latest_close": 85.0,
            "high_52w": 120.0,
            "low_52w": 80.0,
            "volume": 50.0,
            "avg_volume": 100.0,
        },
    ]
    brief = build_research_brief(make_history(), "yfinance", peers, "半導體")

    assert brief["peer_context"]["state"] == "ready"
    assert brief["peer_context"]["sample_size"] == 3
    assert brief["peer_context"]["ranks"]["daily_change"] == {"rank": 1, "total": 3}

def test_fresh_live_history_is_research_ready() -> None:
    brief = build_research_brief(
        make_history(),
        "yfinance",
        [],
        "半導體",
        reference_date=date(2026, 3, 26),
    )

    readiness = brief["readiness"]
    assert readiness["score"] == 100
    assert readiness["level"] == "ready"
    assert readiness["label"] == "資料條件完整"
    assert [item["id"] for item in readiness["dimensions"]] == [
        "provenance",
        "freshness",
        "coverage",
        "depth",
    ]


def test_demo_history_is_capped_below_research_ready() -> None:
    brief = build_research_brief(
        make_history(),
        "sample",
        [],
        "半導體",
        reference_date=date(2026, 3, 26),
    )

    readiness = brief["readiness"]
    assert readiness["score"] <= 59
    assert readiness["level"] == "limited"
    assert any("yfinance" in action for action in readiness["actions"])


def test_stale_live_history_is_capped_and_explains_refresh_action() -> None:
    brief = build_research_brief(
        make_history(),
        "yfinance",
        [],
        "半導體",
        reference_date=date(2026, 4, 20),
    )

    readiness = brief["readiness"]
    assert readiness["score"] <= 59
    assert readiness["level"] == "limited"
    assert any("資料日期" in action for action in readiness["actions"])
