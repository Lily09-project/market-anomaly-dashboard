from __future__ import annotations

from collections.abc import Mapping
from typing import Any


STEP_STATUS_LABELS = {
    "complete": "已完成",
    "review": "需要覆核",
    "blocked": "先處理",
}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _step(
    identifier: str,
    label: str,
    status: str,
    detail: str,
) -> dict[str, str]:
    normalized_status = status if status in STEP_STATUS_LABELS else "review"
    return {
        "id": identifier,
        "label": label,
        "status": normalized_status,
        "status_label": STEP_STATUS_LABELS[normalized_status],
        "detail": detail,
    }


def build_research_workflow(
    readiness: Mapping[str, Any] | None,
    coherence: Mapping[str, Any] | None,
    peer_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Turn research state into an ordered, user-facing review path.

    This is a navigation aid, not a recommendation engine. It makes the
    existing data-quality and evidence contracts actionable without hiding
    any limitation behind a single score.
    """
    readiness_data = _mapping(readiness)
    coherence_data = _mapping(coherence)
    peer_data = _mapping(peer_context)

    readiness_level = str(readiness_data.get("level", "limited")).strip().lower()
    if readiness_level == "ready":
        data_step = _step("data", "資料條件", "complete", "來源、時效、欄位與樣本已達研究門檻。")
    elif readiness_level == "review":
        data_step = _step("data", "資料條件", "review", "核心資料可用，但請先覆核來源、日期或樣本限制。")
    else:
        data_step = _step("data", "資料條件", "blocked", "先補足資料或重新連線，再解讀技術證據。")

    coherence_status = str(coherence_data.get("status", "incomplete")).strip().lower()
    if coherence_status == "aligned":
        evidence_step = _step("evidence", "技術證據", "complete", "四個證據面向已完成一致性整理，仍應回看原始指標。")
    elif coherence_status == "incomplete":
        evidence_step = _step("evidence", "技術證據", "blocked", "先補足不可用的證據面向，避免用摘要取代缺漏資料。")
    else:
        evidence_step = _step("evidence", "技術證據", "review", "證據方向需要分開覆核，不把單一訊號當成結論。")

    peer_state = str(peer_data.get("state", "unavailable")).strip().lower()
    if peer_state == "ready":
        context_step = _step("context", "同業脈絡", "complete", "同業比較資料可用，可檢查相對位置與產業脈絡。")
    else:
        context_step = _step("context", "同業脈絡", "review", "同業資料不足時，保留個股判讀並標記比較限制。")

    steps = [data_step, evidence_step, context_step]
    if data_step["status"] == "complete" and evidence_step["status"] == "complete":
        record_step = _step("record", "保存研究紀錄", "complete", "可保存含資料來源、方法版本與證據狀態的研究快照。")
    else:
        record_step = _step("record", "保存研究紀錄", "review", "仍可保存快照，但限制與方法指紋會一併保留。")
    steps.append(record_step)

    next_step = next(
        (item for item in steps if item["status"] in {"blocked", "review"}),
        record_step,
    )
    return {
        "steps": steps,
        "next_step": dict(next_step),
        "summary": f"目前先處理：{next_step['label']}。這是研究流程狀態，不是投資建議。",
    }
