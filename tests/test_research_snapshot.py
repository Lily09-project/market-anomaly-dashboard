from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.research_methodology import build_methodology_manifest
from src.snapshot_compare import parse_snapshot_bytes
from src.research_snapshot import build_research_snapshot, render_snapshot_html, snapshot_to_json_bytes


CAPTURED_AT = datetime(2026, 8, 5, 9, 30, tzinfo=timezone.utc)
ASSET = {
    "symbol": "2330.TW",
    "display_name": "TSMC",
    "industry": "Semiconductors",
    "currency": "TWD",
}
BRIEF = {
    "data_quality": {
        "state": "ready",
        "source": "yfinance",
        "latest_date": "2025-01-31",
        "observations": 25,
        "coverage_pct": 100.0,
        "warnings": [],
    },
    "evidence": [{"id": "trend", "state": "positive", "headline": "Trend intact", "metrics": ["MA20 100.00"]}],
    "changes": {"rows": [{"metric": "Close", "change": "+1.00%"}]},
    "coherence": {"status": "aligned", "label": "多數證據同向", "summary": "證據一致", "counts": {"positive": 3, "neutral": 1, "risk": 0, "unavailable": 0}},
    "peer_context": {"state": "ready", "industry": "Semiconductors", "rows": []},
}


def make_history() -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=25, freq="B")
    close = np.linspace(100.0, 124.0, len(dates))
    return pd.DataFrame(
        {
            "date": dates,
            "open": close - 1,
            "high": close + 1,
            "low": close - 2,
            "close": close,
            "volume": np.arange(1_000, 1_000 + len(dates)),
        }
    )


def test_snapshot_id_is_stable_when_capture_time_changes() -> None:
    history = make_history()

    first = build_research_snapshot(ASSET, history, "yfinance", BRIEF, CAPTURED_AT)
    second = build_research_snapshot(
        ASSET,
        history,
        "yfinance",
        BRIEF,
        datetime(2026, 8, 5, 10, 30, tzinfo=timezone.utc),
    )

    assert first["snapshot_id"] == second["snapshot_id"]
    assert first["as_of_date"] == "2025-01-31"
    assert first["provenance"]["history_fingerprint"]
    assert first["research"]["coherence"]["status"] == "aligned"
    assert first["research"]["methodology"]["version"] == "1.0"
    assert len(first["research"]["methodology_fingerprint"]) == 64
    assert parse_snapshot_bytes(snapshot_to_json_bytes(first))["research"]["methodology"]["version"] == "1.0"


def test_snapshot_id_changes_when_methodology_changes() -> None:
    manifest = build_methodology_manifest()
    changed_manifest = build_methodology_manifest()
    changed_manifest["technical_indicators"]["rsi_period"] = 21

    baseline = build_research_snapshot(ASSET, make_history(), "yfinance", {**BRIEF, "methodology": manifest}, CAPTURED_AT)
    changed = build_research_snapshot(ASSET, make_history(), "yfinance", {**BRIEF, "methodology": changed_manifest}, CAPTURED_AT)

    assert baseline["research"]["methodology_fingerprint"] != changed["research"]["methodology_fingerprint"]
    assert baseline["snapshot_id"] != changed["snapshot_id"]

def test_json_export_is_utf8_and_sanitizes_non_finite_values() -> None:
    brief = {**BRIEF, "changes": {"rows": [{"metric": "Close", "change": float("nan")} ]}}

    snapshot = build_research_snapshot(ASSET, make_history(), "sample", brief, CAPTURED_AT)
    payload = snapshot_to_json_bytes(snapshot)
    parsed = json.loads(payload.decode("utf-8"))

    assert parsed["provenance"]["source"] == "sample"
    assert parsed["research"]["changes"]["rows"][0]["change"] is None
    assert "NaN" not in payload.decode("utf-8")


def test_html_export_escapes_dynamic_asset_values() -> None:
    asset = {**ASSET, "display_name": "<script>alert(1)</script>"}
    snapshot = build_research_snapshot(asset, make_history(), "sample", BRIEF, CAPTURED_AT)

    document = render_snapshot_html(snapshot).decode("utf-8")

    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document
    assert "<script>alert(1)</script>" not in document
    assert "sample" in document
    assert snapshot["snapshot_id"] in document
    assert "Evidence coherence" in document
    assert "Methodology" in document

def test_history_fingerprint_normalizes_missing_numeric_values() -> None:
    missing_column = make_history().drop(columns="volume")
    explicit_nulls = make_history()
    explicit_nulls["volume"] = np.nan

    missing_snapshot = build_research_snapshot(ASSET, missing_column, "sample", BRIEF, CAPTURED_AT)
    null_snapshot = build_research_snapshot(ASSET, explicit_nulls, "sample", BRIEF, CAPTURED_AT)

    assert missing_snapshot["provenance"]["history_fingerprint"] == null_snapshot["provenance"]["history_fingerprint"]
