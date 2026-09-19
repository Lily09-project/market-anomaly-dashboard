from __future__ import annotations

from src.product_state import (
    PAGE_ROUTES,
    build_data_service_state,
    page_label_from_route,
    query_keys_for_page,
    route_from_page_label,
)


def test_page_routes_are_stable_and_reversible() -> None:
    assert PAGE_ROUTES == {
        "stocks": "股票分析",
        "radar": "市場雷達",
        "anomalies": "異常偵測展示",
        "compare": "快照比較",
    }
    for route, label in PAGE_ROUTES.items():
        assert page_label_from_route(route) == label
        assert route_from_page_label(label) == route
    assert page_label_from_route("unknown") == "股票分析"


def test_data_service_state_distinguishes_live_mixed_and_demo() -> None:
    live = build_data_service_state(
        "twse_openapi",
        [{"source": "yfinance", "latest_date": "2026-08-08"}],
    )
    assert live["mode"] == "live"
    assert live["is_live"] is True
    assert live["as_of_date"] == "2026-08-08"

    mixed = build_data_service_state(
        "local_cache",
        [
            {"source": "yfinance", "latest_date": "2026-08-08"},
            {"source": "sample", "latest_date": "2026-08-10"},
        ],
    )
    assert mixed["mode"] == "mixed"
    assert mixed["is_live"] is False
    assert mixed["as_of_date"] == "2026-08-08"

    demo = build_data_service_state(
        "unavailable",
        [{"source": "sample", "latest_date": "2025-12-31"}],
    )
    assert demo["mode"] == "demo"
    assert demo["is_live"] is False
    assert "非真實行情" in demo["message"]


def test_data_service_state_handles_no_market_cards() -> None:
    state = build_data_service_state("unavailable", [])

    assert state["mode"] == "unavailable"
    assert state["as_of_date"] is None
    assert state["is_live"] is False


def test_query_keys_are_scoped_to_each_page() -> None:
    assert query_keys_for_page("股票分析") == {"page", "symbol"}
    assert query_keys_for_page("市場雷達") == {"page", "industry", "profile", "min_score", "pool_size"}
    assert query_keys_for_page("異常偵測展示") == {"page"}
    assert query_keys_for_page("快照比較") == {"page"}
