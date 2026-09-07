from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import jsonschema


ROOT = Path(__file__).resolve().parents[1]
QUALITY = ROOT / "quality"
MANIFEST = QUALITY / "test-manifest.json"
RUNNER = QUALITY / "run_acceptance.py"
PERFORMANCE_MANIFEST = QUALITY / "performance-manifest.json"
BENCHMARK_RUNNER = QUALITY / "run_benchmarks.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("project_acceptance_runner", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quality_json_contracts_are_parseable_and_versioned() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest_schema = json.loads(
        (QUALITY / "test-manifest.schema.json").read_text(encoding="utf-8")
    )
    report_schema = json.loads(
        (QUALITY / "acceptance-report.schema.json").read_text(encoding="utf-8")
    )

    assert manifest["schema_version"] == "1.0"
    assert manifest["project"] == ROOT.name
    assert manifest_schema["$schema"].endswith("2020-12/schema")
    assert report_schema["properties"]["schema_version"]["const"] == "1.0"
    jsonschema.Draft202012Validator.check_schema(manifest_schema)
    jsonschema.Draft202012Validator.check_schema(report_schema)
    jsonschema.validate(manifest, manifest_schema)


def test_manifest_validator_is_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = load_runner()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    runner.validate_manifest(manifest)

    broken = json.loads(json.dumps(manifest))
    broken["gates"][1]["id"] = broken["gates"][0]["id"]
    with pytest.raises(runner.ManifestError, match="unique"):
        runner.validate_manifest(broken)

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    evidence, failure = runner.collect_required_evidence(
        {"evidence": ["missing-report.json"]}
    )
    assert evidence == [{"path": "missing-report.json", "exists": False}]
    assert failure == "required evidence missing: missing-report.json"

    stale = tmp_path / "stale-report.json"
    stale.write_text("{}", encoding="utf-8")
    evidence, failure = runner.collect_required_evidence(
        {"evidence": [stale.name], "evidence_freshness": "generated"},
        {stale.name: stale.stat().st_mtime_ns},
    )
    assert evidence[0]["fresh"] is False
    assert evidence[0]["sha256"]
    assert failure == "required evidence not refreshed: stale-report.json"


def test_list_mode_has_no_report_side_effect() -> None:
    report_root = ROOT / "reports" / "acceptance"
    before = set(report_root.glob("*")) if report_root.exists() else set()
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    after = set(report_root.glob("*")) if report_root.exists() else set()

    assert result.returncode == 0, result.stderr
    assert "profiles:" in result.stdout
    assert "launcher_help:" in result.stdout
    assert after == before


def test_performance_manifest_requires_three_runs_and_strict_thresholds() -> None:
    manifest = json.loads(PERFORMANCE_MANIFEST.read_text(encoding="utf-8"))
    assert manifest["project"] == ROOT.name
    assert manifest["repetitions"] >= 3
    assert manifest["thresholds"] == {
        "warning_regression_percent": 20,
        "blocker_regression_percent": 50,
    }
    ids = [item["id"] for item in manifest["benchmarks"]]
    assert ids and len(ids) == len(set(ids))
    assert all(item["timeout_seconds"] > 0 and item["command"] for item in manifest["benchmarks"])


def test_benchmark_list_mode_has_no_measurement_side_effect() -> None:
    report = ROOT / "reports" / "metrics" / "performance_latest.json"
    modified = report.stat().st_mtime_ns if report.exists() else None
    result = subprocess.run(
        [sys.executable, str(BENCHMARK_RUNNER), "--list"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "browser_qa:" in result.stdout
    assert (report.stat().st_mtime_ns if report.exists() else None) == modified
