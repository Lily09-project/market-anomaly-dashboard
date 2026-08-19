from __future__ import annotations

from copy import deepcopy

from src.research_methodology import build_methodology_manifest, methodology_fingerprint


def test_methodology_manifest_records_research_parameters() -> None:
    manifest = build_methodology_manifest()

    assert manifest["version"] == "1.0"
    assert manifest["technical_indicators"] == {
        "moving_average_windows": [5, 20, 60],
        "rsi_period": 14,
        "volatility_window": 20,
        "volume_average_window": 20,
    }
    assert manifest["research_thresholds"]["stock_min_observations"] == 20
    assert manifest["research_thresholds"]["radar_min_observations"] == 60


def test_methodology_fingerprint_is_stable_and_changes_with_parameters() -> None:
    manifest = build_methodology_manifest()
    first = methodology_fingerprint(manifest)
    second = methodology_fingerprint(manifest)
    changed = deepcopy(manifest)
    changed["technical_indicators"]["rsi_period"] = 21

    assert first == second
    assert len(first) == 64
    assert first != methodology_fingerprint(changed)