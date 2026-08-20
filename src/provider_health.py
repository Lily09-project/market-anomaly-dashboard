from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    status: str
    source: str
    records: int = 0
    latest_date: str = ""
    detail: str = ""
    source_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _latest_date(cards: Iterable[Mapping[str, Any]]) -> str:
    dates = {
        str(card.get("latest_date") or "").strip()
        for card in cards
        if str(card.get("latest_date") or "").strip()
    }
    return max(dates) if dates else ""


def build_provider_health(
    company_source: str,
    cards: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize source health without treating fallback values as live quotes."""
    card_list = list(cards)
    source_counts = Counter(str(card.get("source") or "unavailable").strip() for card in card_list)
    live_count = source_counts.get("yfinance", 0)
    sample_count = source_counts.get("sample", 0)
    unknown_count = len(card_list) - live_count - sample_count
    sorted_source_counts = dict(sorted(source_counts.items()))
    if unknown_count:
        market = ProviderHealth(
            "yfinance",
            "degraded",
            "mixed",
            len(card_list),
            _latest_date(card_list),
            "部分標的使用本機示範資料或無法辨識來源。"
            if live_count or sample_count
            else "行情資料來源標籤無法辨識。",
            sorted_source_counts,
        )
    elif live_count and sample_count:
        market = ProviderHealth(
            "yfinance",
            "degraded",
            "mixed",
            len(card_list),
            _latest_date(card_list),
            "部分標的使用本機示範資料。",
            sorted_source_counts,
        )
    elif live_count:
        market = ProviderHealth(
            "yfinance",
            "healthy",
            "yfinance",
            live_count,
            _latest_date(card_list),
            "行情資料已取得。",
            sorted_source_counts,
        )
    elif sample_count:
        market = ProviderHealth(
            "yfinance",
            "fallback",
            "sample",
            sample_count,
            _latest_date(card_list),
            "外部行情不可用，使用本機示範資料。",
            sorted_source_counts,
        )
    else:
        market = ProviderHealth(
            "yfinance",
            "unavailable",
            "unavailable",
            0,
            "",
            "目前沒有可用行情資料。",
            sorted_source_counts,
        )

    company_source = str(company_source or "unavailable").strip()
    company_status = {
        "twse_openapi": "healthy",
        "local_cache": "cached",
        "unavailable": "unavailable",
    }.get(company_source, "degraded")
    company_detail = {
        "twse_openapi": "公司清單已由 TWSE OpenAPI 更新。",
        "local_cache": "使用本機快取的公司清單。",
        "unavailable": "目前沒有公司清單來源。",
    }.get(company_source, "公司清單來源狀態未知。")
    company = ProviderHealth(
        "TWSE OpenAPI",
        company_status,
        company_source,
        1 if company_source not in {"unavailable", ""} else 0,
        "",
        company_detail,
        {company_source: 1} if company_source not in {"unavailable", ""} else {},
    )
    return [market.to_dict(), company.to_dict()]
