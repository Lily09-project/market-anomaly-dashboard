from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


METHODOLOGY_VERSION = "1.0"


def build_methodology_manifest() -> dict[str, Any]:
    """Return the versioned parameters that define the research interpretation."""
    return {
        "version": METHODOLOGY_VERSION,
        "technical_indicators": {
            "moving_average_windows": [5, 20, 60],
            "rsi_period": 14,
            "volatility_window": 20,
            "volume_average_window": 20,
        },
        "research_thresholds": {
            "stock_min_observations": 20,
            "radar_min_observations": 60,
            "readiness_min_coverage_pct": 80.0,
        },
        "evidence_dimensions": ["trend", "momentum", "participation", "risk"],
        "coherence_states": ["aligned", "divergent", "risk-heavy", "mixed", "incomplete"],
    }


def _canonical_manifest(manifest: Mapping[str, Any]) -> bytes:
    return json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def methodology_fingerprint(manifest: Mapping[str, Any] | None = None) -> str:
    """Return a deterministic fingerprint for the research methodology."""
    payload = manifest if manifest is not None else build_methodology_manifest()
    return hashlib.sha256(_canonical_manifest(payload)).hexdigest()