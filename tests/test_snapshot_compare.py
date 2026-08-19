from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
import pytest

from src.research_snapshot import build_research_snapshot, snapshot_to_json_bytes
from src.snapshot_compare import (
    MAX_SNAPSHOT_BYTES,
    MAX_SNAPSHOT_NESTING,
    SnapshotValidationError,
    compare_snapshots,
    comparison_to_json_bytes,
    parse_snapshot_bytes,
)


def make_snapshot(
    symbol: str = "2330.TW",
    start_date: str = "2026-01-01",
    evidence_state: str = "positive",
) -> dict:
    dates = pd.bdate_range(start_date, periods=30)
    close = pd.Series(range(100, 130), dtype="float64")
    history = pd.DataFrame(
        {
            "date": dates,
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1_000_000,
        }
    )
    brief = {
        "data_quality": {
            "state": "ready",
            "latest_date": dates[-1].date().isoformat(),
            "observations": len(history),
            "coverage_pct": 100.0,
            "warnings": [],
        },
        "evidence": [
            {
                "id": "trend",
                "label": "趨勢",
                "state": evidence_state,
                "headline": "均線狀態",
                "detail": "依目前均線排列判讀。",
                "metrics": ["MA20 120.00"],
            },
            {
                "id": "risk",
                "label": "風險",
                "state": "neutral",
                "headline": "波動穩定",
                "detail": "近期波動未明顯擴大。",
                "metrics": ["20 日波動率 1.20%"],
            },
        ],
        "changes": {"rows": []},
        "peer_context": {"state": "unavailable", "rows": []},
    }
    return build_research_snapshot(
        {"symbol": symbol, "display_name": "台積電", "industry": "半導體業", "currency": "TWD"},
        history,
        "yfinance",
        brief,
        datetime(2026, 8, 9, tzinfo=timezone.utc),
    )


def test_parse_snapshot_bytes_accepts_valid_snapshot() -> None:
    parsed = parse_snapshot_bytes(snapshot_to_json_bytes(make_snapshot()))

    assert parsed["asset"]["symbol"] == "2330.TW"
    assert parsed["schema_version"] == "1.0"


def test_parse_snapshot_bytes_rejects_mismatched_methodology_fingerprint() -> None:
    snapshot = make_snapshot()
    snapshot["research"]["methodology"] = {"version": "1.0", "technical_indicators": {"rsi_period": 21}}
    snapshot["research"]["methodology_fingerprint"] = "0" * 64

    with pytest.raises(SnapshotValidationError, match="方法指紋"):
        parse_snapshot_bytes(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))

def test_parse_snapshot_bytes_rejects_tampered_snapshot_id() -> None:
    snapshot = make_snapshot()
    snapshot["as_of_date"] = "2099-01-01"

    with pytest.raises(SnapshotValidationError, match="完整性"):
        parse_snapshot_bytes(json.dumps(snapshot, ensure_ascii=False).encode("utf-8"))


def test_parse_snapshot_bytes_rejects_invalid_schema_and_oversized_payload() -> None:
    snapshot = make_snapshot()
    snapshot["schema_version"] = "2.0"

    with pytest.raises(SnapshotValidationError, match="版本"):
        parse_snapshot_bytes(json.dumps(snapshot).encode("utf-8"))
    with pytest.raises(SnapshotValidationError, match="2 MiB"):
        parse_snapshot_bytes(b"x" * (MAX_SNAPSHOT_BYTES + 1))


def test_compare_snapshots_joins_evidence_by_id_and_reports_changes() -> None:
    baseline = make_snapshot(start_date="2026-01-01", evidence_state="neutral")
    current = make_snapshot(start_date="2026-03-01", evidence_state="positive")

    result = compare_snapshots(baseline, current)

    assert result["asset"]["symbol"] == "2330.TW"
    assert result["chronology"]["state"] == "forward"
    assert result["chronology"]["elapsed_days"] > 0
    assert result["changed_evidence_count"] == 1
    assert [row["id"] for row in result["evidence"]] == ["trend", "risk"]
    assert result["evidence"][0]["baseline_state"] == "neutral"
    assert result["evidence"][0]["current_state"] == "positive"
    assert result["evidence"][0]["changed"] is True


def test_compare_snapshots_rejects_cross_symbol_inputs() -> None:
    with pytest.raises(SnapshotValidationError, match="同一股票"):
        compare_snapshots(make_snapshot("2330.TW"), make_snapshot("AAPL"))


def test_comparison_json_is_utf8_and_contains_snapshot_ids() -> None:
    baseline = make_snapshot(start_date="2026-01-01")
    current = make_snapshot(start_date="2026-03-01")

    payload = comparison_to_json_bytes(compare_snapshots(baseline, current))
    parsed = json.loads(payload.decode("utf-8"))

    assert parsed["baseline_snapshot_id"] == baseline["snapshot_id"]
    assert parsed["current_snapshot_id"] == current["snapshot_id"]
    assert "台積電" in payload.decode("utf-8")


def test_parse_snapshot_bytes_rejects_duplicate_json_keys() -> None:
    payload = b'{"schema_version":"1.0","schema_version":"1.0"}'

    with pytest.raises(SnapshotValidationError, match="重複"):
        parse_snapshot_bytes(payload)


def test_parse_snapshot_bytes_rejects_non_standard_json_constants() -> None:
    payload = b'{"value": NaN}'

    with pytest.raises(SnapshotValidationError, match="有效的 JSON"):
        parse_snapshot_bytes(payload)


def test_parse_snapshot_bytes_rejects_excessive_json_nesting() -> None:
    payload = ("[" * (MAX_SNAPSHOT_NESTING + 1) + "]" * (MAX_SNAPSHOT_NESTING + 1)).encode("ascii")

    with pytest.raises(SnapshotValidationError, match="巢狀"):
        parse_snapshot_bytes(payload)
