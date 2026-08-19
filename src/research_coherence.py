from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


EVIDENCE_ORDER = ("trend", "momentum", "participation", "risk")
VALID_STATES = ("positive", "neutral", "risk", "unavailable")


def build_evidence_coherence(evidence: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize agreement and conflict across technical evidence dimensions."""
    observed: dict[str, str] = {}
    for item in evidence:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id", "")).strip()
        if identifier not in EVIDENCE_ORDER or identifier in observed:
            continue
        state = str(item.get("state", "unavailable")).strip().lower()
        observed[identifier] = state if state in VALID_STATES else "unavailable"

    state_by_id = {identifier: observed.get(identifier, "unavailable") for identifier in EVIDENCE_ORDER}
    counts = {state: sum(value == state for value in state_by_id.values()) for state in VALID_STATES}

    if counts["unavailable"]:
        status = "incomplete"
        label = "證據尚不完整"
        summary = f"目前有 {counts['unavailable']} 個證據面向不可用，不能用整體方向取代缺漏資料。"
        next_focus = "先補足缺少的技術證據，再解讀各面向之間的關係。"
    elif counts["positive"] and counts["risk"]:
        status = "divergent"
        label = "證據分歧"
        summary = "正向與風險證據同時存在，四個面向沒有形成單一方向。"
        next_focus = "分開閱讀趨勢、動能、量能與風險，不將單一正向訊號視為結論。"
    elif counts["risk"] >= 2:
        status = "risk-heavy"
        label = "風險證據偏多"
        summary = f"四個面向中有 {counts['risk']} 個呈現風險狀態，應優先確認波動與量能。"
        next_focus = "優先檢查波動與成交量，再觀察趨勢是否延續。"
    elif counts["positive"] >= 3:
        status = "aligned"
        label = "多數證據同向"
        summary = f"四個面向中有 {counts['positive']} 個呈現正向狀態，但仍需回到原始指標確認。"
        next_focus = "確認資料日期與原始指標；證據同向不代表投資價值或報酬保證。"
    else:
        status = "mixed"
        label = "證據方向混合"
        summary = "證據面向沒有形成明顯共識，應逐項查看原始指標與資料限制。"
        next_focus = "逐項查看四個證據卡，不使用單一摘要取代判讀。"

    return {
        "status": status,
        "label": label,
        "summary": summary,
        "next_focus": next_focus,
        "counts": counts,
        "state_by_id": state_by_id,
    }