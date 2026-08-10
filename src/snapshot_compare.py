from __future__ import annotations

import hmac
import json
from collections.abc import Mapping
from datetime import date
from typing import Any

from src.research_snapshot import SNAPSHOT_SCHEMA_VERSION, calculate_snapshot_id


MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
COMPARISON_SCHEMA_VERSION = "1.0"
EVIDENCE_ORDER = ("trend", "momentum", "participation", "risk")


class SnapshotValidationError(ValueError):
    """Raised when an uploaded Research Snapshot cannot be trusted or compared."""


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise SnapshotValidationError(f"\u5feb\u7167\u7f3a\u5c11\u6709\u6548\u7684{label}\u8cc7\u6599\u3002")
    return dict(value)


def _required_text(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise SnapshotValidationError(f"\u5feb\u7167\u7f3a\u5c11{label}\u3002")
    return text


def _snapshot_date(value: object, label: str) -> date:
    text = _required_text(value, label)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise SnapshotValidationError(f"{label}\u5fc5\u9808\u4f7f\u7528 YYYY-MM-DD \u683c\u5f0f\u3002") from exc


def _validate_snapshot(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    data = dict(snapshot)
    version = _required_text(data.get("schema_version"), "schema \u7248\u672c")
    if version != SNAPSHOT_SCHEMA_VERSION:
        raise SnapshotValidationError(
            f"\u4e0d\u652f\u63f4\u7684\u5feb\u7167\u7248\u672c\uff1a{version}\uff1b\u76ee\u524d\u50c5\u63a5\u53d7 {SNAPSHOT_SCHEMA_VERSION}\u3002"
        )

    asset = _mapping(data.get("asset"), "\u80a1\u7968")
    provenance = _mapping(data.get("provenance"), "\u4f86\u6e90")
    research = _mapping(data.get("research"), "\u7814\u7a76")
    _required_text(asset.get("symbol"), "\u80a1\u7968\u4ee3\u865f")
    _snapshot_date(data.get("as_of_date"), "\u5e02\u5834\u8cc7\u6599\u65e5\u671f")
    _required_text(data.get("captured_at_utc"), "\u64f7\u53d6\u6642\u9593")
    fingerprint = _required_text(provenance.get("history_fingerprint"), "\u6b77\u53f2\u8cc7\u6599\u6307\u7d0b")
    if len(fingerprint) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in fingerprint
    ):
        raise SnapshotValidationError("\u6b77\u53f2\u8cc7\u6599\u6307\u7d0b\u683c\u5f0f\u7121\u6548\u3002")
    if not isinstance(research.get("evidence", []), list):
        raise SnapshotValidationError("\u7814\u7a76\u8b49\u64da\u5fc5\u9808\u662f\u9663\u5217\u683c\u5f0f\u3002")

    snapshot_id = _required_text(data.get("snapshot_id"), "snapshot_id")
    if len(snapshot_id) != 64 or any(
        character not in "0123456789abcdefABCDEF" for character in snapshot_id
    ):
        raise SnapshotValidationError("snapshot_id \u683c\u5f0f\u7121\u6548\u3002")
    expected_id = calculate_snapshot_id(data)
    if not hmac.compare_digest(snapshot_id.lower(), expected_id.lower()):
        raise SnapshotValidationError("\u5feb\u7167\u5b8c\u6574\u6027\u9a57\u8b49\u5931\u6557\uff1b\u5167\u5bb9\u53ef\u80fd\u5df2\u88ab\u4fee\u6539\u3002")
    return data


def parse_snapshot_bytes(payload: bytes) -> dict[str, Any]:
    """Parse and validate one in-memory Research Snapshot JSON payload."""
    if not isinstance(payload, bytes) or not payload:
        raise SnapshotValidationError("\u5feb\u7167\u6a94\u6848\u662f\u7a7a\u7684\u3002")
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SnapshotValidationError("\u5feb\u7167\u6a94\u6848\u4e0d\u53ef\u8d85\u904e 2 MiB\u3002")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SnapshotValidationError("\u5feb\u7167\u5fc5\u9808\u662f UTF-8 JSON \u6a94\u6848\u3002") from exc
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SnapshotValidationError("\u5feb\u7167\u4e0d\u662f\u6709\u6548\u7684 JSON \u6a94\u6848\u3002") from exc
    if not isinstance(value, Mapping):
        raise SnapshotValidationError("\u5feb\u7167 JSON \u6839\u7bc0\u9ede\u5fc5\u9808\u662f\u7269\u4ef6\u3002")
    return _validate_snapshot(value)


def _evidence_map(snapshot: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    research = snapshot.get("research", {})
    evidence = research.get("evidence", []) if isinstance(research, Mapping) else []
    result: dict[str, dict[str, Any]] = {}
    for item in evidence if isinstance(evidence, list) else []:
        if not isinstance(item, Mapping):
            continue
        identifier = str(item.get("id", "")).strip()
        if identifier:
            result[identifier] = dict(item)
    return result


def _evidence_sort_key(identifier: str) -> tuple[int, str]:
    try:
        return EVIDENCE_ORDER.index(identifier), identifier
    except ValueError:
        return len(EVIDENCE_ORDER), identifier


def _evidence_text(item: Mapping[str, Any] | None, key: str, fallback: str) -> str:
    if item is None:
        return fallback
    return str(item.get(key) or fallback)


def _evidence_metrics(item: Mapping[str, Any] | None) -> list[str]:
    if item is None:
        return []
    metrics = item.get("metrics", [])
    if not isinstance(metrics, list):
        return []
    return [str(metric) for metric in metrics]


def compare_snapshots(
    baseline: Mapping[str, Any],
    current: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare two validated snapshots for the same stock symbol."""
    baseline_data = _validate_snapshot(baseline)
    current_data = _validate_snapshot(current)
    baseline_asset = _mapping(baseline_data.get("asset"), "\u80a1\u7968")
    current_asset = _mapping(current_data.get("asset"), "\u80a1\u7968")
    baseline_symbol = _required_text(baseline_asset.get("symbol"), "\u80a1\u7968\u4ee3\u865f").upper()
    current_symbol = _required_text(current_asset.get("symbol"), "\u80a1\u7968\u4ee3\u865f").upper()
    if baseline_symbol != current_symbol:
        raise SnapshotValidationError("\u5feb\u7167\u6bd4\u8f03\u50c5\u652f\u63f4\u540c\u4e00\u80a1\u7968\u4ee3\u865f\u3002")

    baseline_date = _snapshot_date(
        baseline_data.get("as_of_date"), "\u57fa\u6e96\u5e02\u5834\u8cc7\u6599\u65e5\u671f"
    )
    current_date = _snapshot_date(current_data.get("as_of_date"), "\u76ee\u524d\u5e02\u5834\u8cc7\u6599\u65e5\u671f")
    elapsed_days = (current_date - baseline_date).days
    chronology_state = (
        "forward" if elapsed_days > 0 else "same" if elapsed_days == 0 else "reverse"
    )

    baseline_evidence = _evidence_map(baseline_data)
    current_evidence = _evidence_map(current_data)
    evidence_rows: list[dict[str, Any]] = []
    identifiers = sorted(
        set(baseline_evidence) | set(current_evidence),
        key=_evidence_sort_key,
    )
    for identifier in identifiers:
        before = baseline_evidence.get(identifier)
        after = current_evidence.get(identifier)
        baseline_state = _evidence_text(before, "state", "unavailable")
        current_state = _evidence_text(after, "state", "unavailable")
        baseline_headline = _evidence_text(before, "headline", "\u7121\u53ef\u7528\u8cc7\u6599")
        current_headline = _evidence_text(after, "headline", "\u7121\u53ef\u7528\u8cc7\u6599")
        baseline_metrics = _evidence_metrics(before)
        current_metrics = _evidence_metrics(after)
        evidence_rows.append(
            {
                "id": identifier,
                "label": _evidence_text(after or before, "label", identifier),
                "baseline_state": baseline_state,
                "current_state": current_state,
                "baseline_headline": baseline_headline,
                "current_headline": current_headline,
                "baseline_metrics": baseline_metrics,
                "current_metrics": current_metrics,
                "changed": (
                    baseline_state,
                    baseline_headline,
                    baseline_metrics,
                )
                != (
                    current_state,
                    current_headline,
                    current_metrics,
                ),
            }
        )

    baseline_provenance = _mapping(baseline_data.get("provenance"), "\u4f86\u6e90")
    current_provenance = _mapping(current_data.get("provenance"), "\u4f86\u6e90")
    provenance_fields = (
        ("source", "\u8cc7\u6599\u4f86\u6e90"),
        ("quality_state", "\u8cc7\u6599\u54c1\u8cea"),
        ("observations", "\u89c0\u6e2c\u7b46\u6578"),
        ("coverage_pct", "\u6b04\u4f4d\u8986\u84cb\u7387"),
        ("history_fingerprint", "\u6b77\u53f2\u8cc7\u6599\u6307\u7d0b"),
    )
    provenance_rows = [
        {
            "field": label,
            "baseline": baseline_provenance.get(key),
            "current": current_provenance.get(key),
            "changed": baseline_provenance.get(key)
            != current_provenance.get(key),
        }
        for key, label in provenance_fields
    ]

    return {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "comparison_type": "research_snapshot_diff",
        "asset": {
            "symbol": current_symbol,
            "display_name": str(
                current_asset.get("display_name")
                or baseline_asset.get("display_name")
                or ""
            ),
            "industry": str(
                current_asset.get("industry") or baseline_asset.get("industry") or ""
            ),
            "currency": str(
                current_asset.get("currency") or baseline_asset.get("currency") or ""
            ),
        },
        "baseline_as_of_date": baseline_date.isoformat(),
        "current_as_of_date": current_date.isoformat(),
        "chronology": {
            "state": chronology_state,
            "elapsed_days": elapsed_days,
        },
        "baseline_snapshot_id": str(baseline_data["snapshot_id"]),
        "current_snapshot_id": str(current_data["snapshot_id"]),
        "provenance": provenance_rows,
        "baseline_warnings": list(baseline_provenance.get("warnings", [])),
        "current_warnings": list(current_provenance.get("warnings", [])),
        "evidence": evidence_rows,
        "changed_evidence_count": sum(
            1 for row in evidence_rows if row["changed"]
        ),
    }


def comparison_to_json_bytes(comparison: Mapping[str, Any]) -> bytes:
    """Serialise a comparison contract as readable UTF-8 JSON."""
    return json.dumps(
        dict(comparison),
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8")
