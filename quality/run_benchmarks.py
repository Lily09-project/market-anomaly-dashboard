#!/usr/bin/env python3
"""Run three-repeat project benchmarks and compare same-environment medians."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any

from run_acceptance import ROOT, expand_command, run_process


MANIFEST_PATH = ROOT / "quality" / "performance-manifest.json"
BASELINE_PATH = ROOT / "quality" / "performance-baseline.json"
REPORT_PATH = ROOT / "reports" / "metrics" / "performance_latest.json"
LOG_ROOT = ROOT / "reports" / "performance"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def environment() -> dict[str, Any]:
    value = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "cpu_count": os.cpu_count(),
    }
    value["fingerprint"] = hashlib.sha256(
        json.dumps(value, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return value


def validate_manifest(value: dict[str, Any]) -> None:
    if value.get("schema_version") != "1.0":
        raise ValueError("schema_version must be 1.0")
    if value.get("project") != ROOT.name:
        raise ValueError(f"project must be {ROOT.name}")
    repetitions = value.get("repetitions")
    if not isinstance(repetitions, int) or repetitions < 3 or repetitions > 9:
        raise ValueError("repetitions must be between 3 and 9")
    thresholds = value.get("thresholds", {})
    warning = thresholds.get("warning_regression_percent")
    blocker = thresholds.get("blocker_regression_percent")
    if not isinstance(warning, (int, float)) or not isinstance(blocker, (int, float)):
        raise ValueError("performance thresholds must be numeric")
    if warning <= 0 or blocker <= warning:
        raise ValueError("blocker threshold must exceed the positive warning threshold")
    ids: set[str] = set()
    for item in value.get("benchmarks", []):
        benchmark_id = item.get("id")
        if not isinstance(benchmark_id, str) or not benchmark_id or benchmark_id in ids:
            raise ValueError("benchmark ids must be unique and non-empty")
        ids.add(benchmark_id)
        command = item.get("command")
        if not isinstance(command, list) or not command or not all(
            isinstance(part, str) and part for part in command
        ):
            raise ValueError(f"benchmark {benchmark_id} command must be a string array")
        timeout = item.get("timeout_seconds")
        if not isinstance(timeout, int) or timeout < 1 or timeout > 1800:
            raise ValueError(f"benchmark {benchmark_id} timeout must be 1..1800")
    if not ids:
        raise ValueError("at least one benchmark is required")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args()
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        validate_manifest(manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"PERFORMANCE MANIFEST ERROR: {exc}", file=sys.stderr)
        return 2
    if args.list:
        for item in manifest["benchmarks"]:
            print(f"{item['id']}: {item['description']}")
        return 0

    current_environment = environment()
    baseline: dict[str, Any] | None = None
    if BASELINE_PATH.exists():
        try:
            baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"INVALID BASELINE: {exc}", file=sys.stderr)
            return 2
        if baseline.get("environment", {}).get("fingerprint") != current_environment["fingerprint"] and not args.write_baseline:
            print("BASELINE ENVIRONMENT MISMATCH: rerun with --write-baseline on this machine", file=sys.stderr)
            return 2

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"
    log_dir = LOG_ROOT / run_id
    log_dir.mkdir(parents=True, exist_ok=False)
    results: list[dict[str, Any]] = []
    overall_failed = False
    for benchmark in manifest["benchmarks"]:
        samples: list[float] = []
        runs: list[dict[str, Any]] = []
        for index in range(1, manifest["repetitions"] + 1):
            temp_dir = Path(tempfile.mkdtemp(prefix=f"{ROOT.name}-{benchmark['id']}-{index}-"))
            stdout_path = log_dir / f"{benchmark['id']}.{index}.stdout.log"
            stderr_path = log_dir / f"{benchmark['id']}.{index}.stderr.log"
            started = monotonic()
            try:
                exit_code, timed_out, failure = run_process(
                    expand_command(benchmark["command"], temp_dir),
                    benchmark["timeout_seconds"], stdout_path, stderr_path,
                )
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)
            elapsed = round(monotonic() - started, 3)
            if failure is None and exit_code != 0:
                failure = f"command exited with code {exit_code}"
            runs.append({
                "iteration": index, "seconds": elapsed, "exit_code": exit_code,
                "timed_out": timed_out, "failure_reason": failure,
                "stdout_log": str(stdout_path.relative_to(ROOT)),
                "stderr_log": str(stderr_path.relative_to(ROOT)),
            })
            if failure is not None:
                overall_failed = True
                break
            samples.append(elapsed)
        median_seconds = round(statistics.median(samples), 3) if samples else None
        baseline_seconds = None
        regression_percent = None
        classification = "measured"
        if baseline and median_seconds is not None:
            baseline_seconds = baseline.get("benchmarks", {}).get(benchmark["id"])
            if isinstance(baseline_seconds, (int, float)) and baseline_seconds > 0:
                regression_percent = round((median_seconds / baseline_seconds - 1) * 100, 2)
                if regression_percent > manifest["thresholds"]["blocker_regression_percent"]:
                    classification = "blocker"
                    overall_failed = True
                elif regression_percent > manifest["thresholds"]["warning_regression_percent"]:
                    classification = "warning"
                else:
                    classification = "within_baseline"
        results.append({
            "id": benchmark["id"], "description": benchmark["description"],
            "median_seconds": median_seconds, "baseline_seconds": baseline_seconds,
            "regression_percent": regression_percent, "classification": classification,
            "runs": runs,
        })
        label = "FAILED" if not samples or len(samples) != manifest["repetitions"] else classification.upper()
        print(f"[{label}] {benchmark['id']} median={median_seconds}s")

    report = {
        "schema_version": "1.0", "project": manifest["project"], "created_at": utc_now(),
        "status": "failed" if overall_failed else "passed", "environment": current_environment,
        "repetitions": manifest["repetitions"], "thresholds": manifest["thresholds"], "benchmarks": results,
    }
    write_json(REPORT_PATH, report)
    if args.write_baseline and not overall_failed:
        write_json(BASELINE_PATH, {
            "schema_version": "1.0", "project": manifest["project"], "created_at": utc_now(),
            "environment": current_environment,
            "benchmarks": {item["id"]: item["median_seconds"] for item in results},
        })
        print(f"baseline: {BASELINE_PATH}")
    elif baseline is None:
        print("NO BASELINE: rerun with --write-baseline", file=sys.stderr)
        return 2
    print(f"report: {REPORT_PATH}")
    return 1 if overall_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
