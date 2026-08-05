from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd


SNAPSHOT_SCHEMA_VERSION = "1.0"
HISTORY_COLUMNS = ("date", "open", "high", "low", "close", "volume")
LIMITATIONS = (
    "This snapshot records historical data observations and derived technical evidence.",
    "It does not predict prices, recommend trades, or measure investment performance.",
    "The export excludes raw OHLCV rows; use the history fingerprint to verify its input dataset.",
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    return str(value)


def _canonical_json(value: Mapping[str, Any] | list[dict[str, Any]]) -> bytes:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _normalised_history(history: pd.DataFrame) -> list[dict[str, Any]]:
    if not isinstance(history, pd.DataFrame) or "date" not in history:
        return []

    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for column in HISTORY_COLUMNS[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce") if column in data else pd.NA
    data = data.dropna(subset=["date"]).sort_values("date")
    records: list[dict[str, Any]] = []
    for row in data.loc[:, HISTORY_COLUMNS].to_dict(orient="records"):
        records.append(
            {
                "date": pd.Timestamp(row["date"]).date().isoformat(),
                **{column: _json_value(row[column]) for column in HISTORY_COLUMNS[1:]},
            }
        )
    return records


def _utc_timestamp(value: datetime | pd.Timestamp) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    else:
        timestamp = timestamp.tz_convert(timezone.utc)
    return timestamp.isoformat().replace("+00:00", "Z")


def _asset_payload(asset: Mapping[str, Any]) -> dict[str, str]:
    return {
        "symbol": str(asset.get("symbol", "")).strip(),
        "display_name": str(asset.get("display_name", "")).strip(),
        "industry": str(asset.get("industry", "")).strip(),
        "currency": str(asset.get("currency", "")).strip(),
    }


def build_research_snapshot(
    asset: Mapping[str, Any],
    history: pd.DataFrame,
    source: str,
    brief: Mapping[str, Any],
    captured_at: datetime | pd.Timestamp,
) -> dict[str, Any]:
    """Create a deterministic, JSON-safe research snapshot without I/O."""
    records = _normalised_history(history)
    quality = _json_value(brief.get("data_quality", {}))
    quality_mapping = dict(quality) if isinstance(quality, Mapping) else {}
    quality_mapping["source"] = source or "unavailable"
    as_of_date = str(quality_mapping.get("latest_date", "") or (records[-1]["date"] if records else ""))
    provenance = {
        "source": source or "unavailable",
        "quality_state": str(quality_mapping.get("state", "unavailable")),
        "observations": int(quality_mapping.get("observations", len(records)) or 0),
        "coverage_pct": _json_value(quality_mapping.get("coverage_pct")),
        "warnings": list(quality_mapping.get("warnings", [])),
        "history_start_date": records[0]["date"] if records else "",
        "history_end_date": records[-1]["date"] if records else "",
        "history_fingerprint": hashlib.sha256(_canonical_json(records)).hexdigest(),
    }
    content = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "as_of_date": as_of_date,
        "asset": _asset_payload(asset),
        "provenance": provenance,
        "research": {
            "evidence": _json_value(brief.get("evidence", [])),
            "changes": _json_value(brief.get("changes", {})),
            "peer_context": _json_value(brief.get("peer_context", {})),
        },
        "limitations": list(LIMITATIONS),
    }
    snapshot_id = hashlib.sha256(_canonical_json(content)).hexdigest()
    return {**content, "snapshot_id": snapshot_id, "captured_at_utc": _utc_timestamp(captured_at)}


def snapshot_to_json_bytes(snapshot: Mapping[str, Any]) -> bytes:
    """Serialise a snapshot as UTF-8 JSON without non-finite numeric values."""
    return json.dumps(_json_value(snapshot), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")
