from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


PAGE_ROUTES = {
    "stocks": "股票分析",
    "anomalies": "異常偵測展示",
    "compare": "快照比較",
}


def page_label_from_route(route: object) -> str:
    """Resolve a public URL route to a supported dashboard page."""
    return PAGE_ROUTES.get(str(route or "").strip().lower(), PAGE_ROUTES["stocks"])


def route_from_page_label(label: object) -> str:
    """Return the stable public route for a dashboard page label."""
    clean_label = str(label or "").strip()
    return next(
        (route for route, page_label in PAGE_ROUTES.items() if page_label == clean_label),
        "stocks",
    )


def _latest_date(cards: Iterable[Mapping[str, Any]]) -> str | None:
    dates = {
        str(card.get("latest_date") or "").strip()
        for card in cards
        if str(card.get("latest_date") or "").strip()
    }
    return max(dates) if dates else None


def build_data_service_state(
    company_source: str,
    cards: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Describe market-data availability without presenting demo values as quotes."""
    card_list = list(cards)
    sources = {str(card.get("source") or "").strip() for card in card_list}
    has_live_market = "yfinance" in sources
    has_demo_market = "sample" in sources
    has_live_company = company_source == "twse_openapi"
    live_cards = [card for card in card_list if card.get("source") == "yfinance"]
    as_of_date = _latest_date(live_cards or card_list)

    if has_live_market and not has_demo_market:
        company_note = "TWSE 即時來源" if has_live_company else "TWSE 快取或內建清單"
        return {
            "mode": "live",
            "label": "LIVE",
            "message": f"行情使用 yfinance；公司資料使用 {company_note}。",
            "as_of_date": as_of_date,
            "is_live": True,
        }
    if has_live_market and has_demo_market:
        return {
            "mode": "mixed",
            "label": "部分連線",
            "message": "部分行情無法取得並以示範資料替代；請逐卡確認資料標籤。",
            "as_of_date": as_of_date,
            "is_live": False,
        }
    if has_demo_market:
        return {
            "mode": "demo",
            "label": "DEMO",
            "message": "目前顯示示範資料，所有價格與漲跌均非真實行情。",
            "as_of_date": as_of_date,
            "is_live": False,
        }
    return {
        "mode": "unavailable",
        "label": "離線",
        "message": "目前無法取得行情資料；請重新連線或稍後再試。",
        "as_of_date": as_of_date,
        "is_live": False,
    }
