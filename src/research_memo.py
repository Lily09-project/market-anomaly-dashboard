from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any


MEMO_SCHEMA_VERSION = "1.0"
MEMO_STATUSES = ("draft", "monitoring", "reviewed")
MEMO_STATUS_LABELS = {
    "draft": "草稿",
    "monitoring": "持續觀察",
    "reviewed": "已覆核",
}
MEMO_FIELD_LABELS = {
    "status": "紀錄狀態",
    "hypothesis": "研究假設／核心問題",
    "supporting_evidence": "支持證據",
    "counter_evidence": "反向證據／尚未解釋",
    "risks_unknowns": "風險與未知",
    "next_question": "下一個要驗證的問題",
    "next_review_date": "下次檢查日期",
}
MEMO_FIELDS = (
    "status",
    "hypothesis",
    "supporting_evidence",
    "counter_evidence",
    "risks_unknowns",
    "next_question",
    "next_review_date",
)
MEMO_LIMITS = {
    "hypothesis": 1000,
    "supporting_evidence": 2000,
    "counter_evidence": 2000,
    "risks_unknowns": 2000,
    "next_question": 800,
}


def empty_research_memo() -> dict[str, str]:
    """Return the stable, JSON-safe shape used by the research memo UI."""
    return {
        "schema_version": MEMO_SCHEMA_VERSION,
        "status": "draft",
        "hypothesis": "",
        "supporting_evidence": "",
        "counter_evidence": "",
        "risks_unknowns": "",
        "next_question": "",
        "next_review_date": "",
    }


def _clean_text(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    limit = MEMO_LIMITS.get(field)
    if limit is not None:
        text = text[:limit]
    return text


def normalize_research_memo(value: Mapping[str, Any] | None) -> dict[str, str]:
    """Normalize user-entered memo content without making an investment conclusion."""
    raw = value if isinstance(value, Mapping) else {}
    memo = empty_research_memo()
    status = str(raw.get("status", memo["status"])).strip().lower()
    memo["status"] = status if status in MEMO_STATUSES else "draft"
    for field in MEMO_LIMITS:
        memo[field] = _clean_text(raw.get(field, ""), field=field)

    review_date = _clean_text(raw.get("next_review_date", ""), field="next_review_date")
    if review_date:
        try:
            review_date = date.fromisoformat(review_date).isoformat()
        except ValueError:
            review_date = ""
    memo["next_review_date"] = review_date
    return memo


def validate_research_memo(value: object, *, allow_missing: bool = True) -> dict[str, str]:
    """Validate a memo embedded in a snapshot and return its normalized shape."""
    if value is None and allow_missing:
        return empty_research_memo()
    if not isinstance(value, Mapping):
        raise ValueError("研究備忘錄格式無效。")
    version = str(value.get("schema_version", MEMO_SCHEMA_VERSION)).strip()
    if version != MEMO_SCHEMA_VERSION:
        raise ValueError(f"不支援的研究備忘錄版本：{version}。")
    normalized = normalize_research_memo(value)
    for field, limit in MEMO_LIMITS.items():
        original = str(value.get(field, "") or "")
        if len(original) > limit:
            raise ValueError(f"研究備忘錄欄位 {field} 不可超過 {limit} 字。")
    supplied_date = str(value.get("next_review_date", "") or "").strip()
    if supplied_date and not normalized["next_review_date"]:
        raise ValueError("研究備忘錄的下次檢查日期格式無效。")
    return normalized


def compare_research_memos(
    baseline: Mapping[str, Any] | None,
    current: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Compare memo fields while keeping the comparison explicit and auditable."""
    before = normalize_research_memo(baseline)
    after = normalize_research_memo(current)
    fields = []
    for field in MEMO_FIELDS:
        old_value = before.get(field, "")
        new_value = after.get(field, "")
        fields.append(
            {
                "field": field,
                "baseline": old_value,
                "current": new_value,
                "changed": old_value != new_value,
            }
        )
    return {
        "changed": any(item["changed"] for item in fields),
        "changed_field_count": sum(1 for item in fields if item["changed"]),
        "fields": fields,
    }
