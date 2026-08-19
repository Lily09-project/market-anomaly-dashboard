from __future__ import annotations

from src.research_coherence import build_evidence_coherence


def make_evidence(states: dict[str, str]) -> list[dict[str, str]]:
    return [{"id": identifier, "state": state} for identifier, state in states.items()]


def test_coherence_identifies_aligned_evidence_without_creating_a_stock_score() -> None:
    result = build_evidence_coherence(
        make_evidence(
            {
                "trend": "positive",
                "momentum": "positive",
                "participation": "positive",
                "risk": "neutral",
            }
        )
    )

    assert result["status"] == "aligned"
    assert result["label"] == "多數證據同向"
    assert result["counts"] == {"positive": 3, "neutral": 1, "risk": 0, "unavailable": 0}
    assert "score" not in result


def test_coherence_flags_conflicting_positive_and_risk_evidence() -> None:
    result = build_evidence_coherence(
        make_evidence(
            {
                "trend": "positive",
                "momentum": "risk",
                "participation": "neutral",
                "risk": "risk",
            }
        )
    )

    assert result["status"] == "divergent"
    assert result["label"] == "證據分歧"
    assert "分開閱讀" in result["next_focus"]


def test_coherence_treats_missing_evidence_as_incomplete() -> None:
    result = build_evidence_coherence(make_evidence({"trend": "positive"}))

    assert result["status"] == "incomplete"
    assert result["counts"]["unavailable"] == 3
    assert result["state_by_id"]["risk"] == "unavailable"
    assert "補足" in result["next_focus"]