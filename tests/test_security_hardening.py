from __future__ import annotations

import pandas as pd

from src.market_radar_page import _score_markup
from src.research_snapshot import render_snapshot_html
from src.utils import clean_numeric, parse_date


def test_parse_date_rejects_malformed_roc_dates_without_crashing() -> None:
    for value in ("113/99/99", "000/00/00", "999/13/40", "114/2/31"):
        assert pd.isna(parse_date(value))


def test_clean_numeric_rejects_invalid_and_non_finite_values() -> None:
    assert clean_numeric("-" * 100_000) is None
    assert clean_numeric("9" * 100_000) is None
    assert clean_numeric("1e309") is None
    assert clean_numeric(["not", "a", "scalar"]) is None


def test_radar_markup_escapes_untrusted_source_text() -> None:
    candidate = {
        "rank": 1,
        "symbol": "2330.TW",
        "stock_label": "2330.TW · <img src=x onerror=alert(1)>",
        "category": "ETF",
        "source": "<script>alert(1)</script>",
        "latest_date": "2026-01-01",
        "ranking_reason": "safe",
        "total_score": 80,
        "label": "可研究",
        "factor_scores": {"trend": 1, "momentum": 2, "participation": 3, "resilience": 4},
        "metrics": {},
    }

    markup = _score_markup(candidate)

    assert "<script>" not in markup
    assert "&lt;script&gt;" in markup


def test_exported_snapshot_html_escapes_untrusted_asset_text() -> None:
    snapshot = {
        "asset": {"symbol": "2330.TW", "display_name": "<img src=x onerror=alert(1)>"},
        "provenance": {},
        "research": {"evidence": []},
        "limitations": [],
        "snapshot_id": "a" * 64,
    }

    document = render_snapshot_html(snapshot).decode("utf-8")

    assert "<img src=x" not in document
    assert "&lt;img src=x" in document