from __future__ import annotations

import json

import pytest

from src.research_memo import (
    compare_research_memos,
    empty_research_memo,
    normalize_research_memo,
    validate_research_memo,
)
from src.research_snapshot import render_snapshot_html
from tests.test_snapshot_compare import make_snapshot


def test_normalize_research_memo_returns_stable_safe_shape() -> None:
    memo = normalize_research_memo(
        {
            "status": "MONITORING",
            "hypothesis": "  price remains above MA20  ",
            "next_review_date": "2026-08-20",
            "unexpected": "ignored",
        }
    )

    assert memo["status"] == "monitoring"
    assert memo["hypothesis"] == "price remains above MA20"
    assert memo["next_review_date"] == "2026-08-20"
    assert "unexpected" not in memo
    assert memo["schema_version"] == "1.0"


def test_validate_research_memo_rejects_invalid_date_and_oversized_text() -> None:
    with pytest.raises(ValueError, match="日期格式無效"):
        validate_research_memo({"next_review_date": "2026/08/20"})
    with pytest.raises(ValueError, match="不可超過 1000"):
        validate_research_memo({"hypothesis": "x" * 1001})
    with pytest.raises(ValueError, match="版本"):
        validate_research_memo({"schema_version": "2.0"})


def test_memo_comparison_reports_changed_fields() -> None:
    result = compare_research_memos(
        empty_research_memo(),
        {"status": "reviewed", "hypothesis": "check earnings"},
    )

    assert result["changed"] is True
    assert result["changed_field_count"] == 2
    changed = {row["field"] for row in result["fields"] if row["changed"]}
    assert changed == {"status", "hypothesis"}


def test_snapshot_memo_changes_id_and_survives_html_escape() -> None:
    baseline = make_snapshot()
    current = make_snapshot()
    current["research"]["memo"] = {
        "schema_version": "1.0",
        "status": "monitoring",
        "hypothesis": "<script>alert(1)</script>",
        "supporting_evidence": "MA20",
        "counter_evidence": "",
        "risks_unknowns": "",
        "next_question": "",
        "next_review_date": "",
    }
    current["snapshot_id"] = "".join("0" for _ in range(64))

    html = render_snapshot_html(current).decode("utf-8")
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html
    assert json.loads(json.dumps(current, ensure_ascii=False))["research"]["memo"]["status"] == "monitoring"
