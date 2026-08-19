from __future__ import annotations

from src.research_workflow import build_research_workflow


def test_limited_data_stops_workflow_before_evidence_interpretation() -> None:
    workflow = build_research_workflow(
        {"level": "limited"},
        {"status": "incomplete"},
        {"state": "unavailable"},
    )

    assert workflow["next_step"]["id"] == "data"
    assert workflow["steps"][0]["status"] == "blocked"
    assert workflow["steps"][1]["status"] == "blocked"
    assert "不是投資建議" in workflow["summary"]


def test_divergent_evidence_is_a_review_step_after_ready_data() -> None:
    workflow = build_research_workflow(
        {"level": "ready"},
        {"status": "divergent"},
        {"state": "ready"},
    )

    assert workflow["steps"][0]["status"] == "complete"
    assert workflow["next_step"]["id"] == "evidence"
    assert workflow["next_step"]["status_label"] == "需要覆核"


def test_complete_workflow_surfaces_research_record_as_final_step() -> None:
    workflow = build_research_workflow(
        {"level": "ready"},
        {"status": "aligned"},
        {"state": "ready"},
    )

    assert all(item["status"] == "complete" for item in workflow["steps"])
    assert workflow["next_step"]["id"] == "record"
