from __future__ import annotations

from src.product_state import build_data_service_state
from src.provider_health import build_provider_health


def test_provider_health_distinguishes_live_and_fallback_sources() -> None:
    health = build_provider_health(
        "local_cache",
        [
            {"source": "yfinance", "latest_date": "2026-08-19"},
            {"source": "sample", "latest_date": "2026-08-20"},
        ],
    )

    assert health[0]["provider"] == "yfinance"
    assert health[0]["status"] == "degraded"
    assert health[1]["status"] == "cached"


def test_data_service_state_exposes_provider_health_contract() -> None:
    state = build_data_service_state(
        "twse_openapi",
        [{"source": "yfinance", "latest_date": "2026-08-19"}],
    )

    assert {item["provider"] for item in state["provider_health"]} == {
        "yfinance",
        "TWSE OpenAPI",
    }


def test_provider_health_exposes_source_counts_and_unknown_source_state() -> None:
    health = build_provider_health(
        "unavailable",
        [
            {"source": "yfinance", "latest_date": "2026-08-19"},
            {"source": "sample", "latest_date": "2026-08-18"},
            {"source": "unexpected", "latest_date": "2026-08-17"},
        ],
    )

    market = health[0]
    assert market["status"] == "degraded"
    assert market["source"] == "mixed"
    assert market["source_counts"] == {"sample": 1, "unexpected": 1, "yfinance": 1}
    assert "無法辨識" in market["detail"]


def test_data_service_state_exposes_quality_summary() -> None:
    state = build_data_service_state(
        "local_cache",
        [
            {"source": "yfinance", "latest_date": "2026-08-19"},
            {"source": "sample", "latest_date": "2026-08-18"},
        ],
    )

    assert state["data_quality"] == {
        "card_count": 2,
        "live_card_count": 1,
        "demo_card_count": 1,
        "unclassified_card_count": 0,
        "source_counts": {"sample": 1, "yfinance": 1},
        "latest_live_date": "2026-08-19",
    }
