#!/usr/bin/env python3
"""Fail-closed acceptance runner driven by quality/test-manifest.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SCHEMA_VERSION = "1.0"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "quality" / "test-manifest.json"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "acceptance"


class ManifestError(ValueError):
    """Raised when a manifest violates the executable contract."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"invalid JSON: {exc}") from exc
    validate_manifest(manifest)
    return manifest, hashlib.sha256(raw).hexdigest()


def _command(value: Any, label: str) -> None:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise ManifestError(f"{label} must be a non-empty string array")


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {SCHEMA_VERSION}")
    if not isinstance(manifest.get("project"), str) or not manifest["project"]:
        raise ManifestError("project must be a non-empty string")
    profiles = manifest.get("profiles")
    if not isinstance(profiles, list) or not profiles or len(profiles) != len(set(profiles)):
        raise ManifestError("profiles must be a non-empty unique string array")
    if not all(isinstance(profile, str) and profile for profile in profiles):
        raise ManifestError("profiles must contain only non-empty strings")
    gates = manifest.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ManifestError("gates must be a non-empty array")
    ids: set[str] = set()
    for index, gate in enumerate(gates):
        label = f"gates[{index}]"
        if not isinstance(gate, dict):
            raise ManifestError(f"{label} must be an object")
        gate_id = gate.get("id")
        if not isinstance(gate_id, str) or not gate_id or gate_id in ids:
            raise ManifestError(f"{label}.id must be non-empty and unique")
        ids.add(gate_id)
        gate_profiles = gate.get("profiles")
        if not isinstance(gate_profiles, list) or not gate_profiles:
            raise ManifestError(f"{label}.profiles must be a non-empty array")
        unknown = set(gate_profiles) - set(profiles)
        if unknown:
            raise ManifestError(f"{label}.profiles contains unknown values: {sorted(unknown)}")
        timeout = gate.get("timeout_seconds")
        if not isinstance(timeout, int) or not 1 <= timeout <= 7200:
            raise ManifestError(f"{label}.timeout_seconds must be between 1 and 7200")
        if not isinstance(gate.get("required"), bool):
            raise ManifestError(f"{label}.required must be boolean")
        freshness = gate.get("evidence_freshness", "existing")
        if freshness not in {"existing", "generated"}:
            raise ManifestError(f"{label}.evidence_freshness must be existing or generated")
        if freshness == "generated" and not gate.get("evidence"):
            raise ManifestError(f"{label}.generated evidence requires at least one path")
        _command(gate.get("command"), f"{label}.command")
        gate_type = gate.get("type")
        if gate_type not in {"command", "browser"}:
            raise ManifestError(f"{label}.type must be command or browser")
        if gate_type == "browser":
            service = gate.get("service")
            if not isinstance(service, dict):
                raise ManifestError(f"{label}.service is required for browser gates")
            _command(service.get("command"), f"{label}.service.command")
            health_url = service.get("health_url")
            parsed = urlsplit(health_url if isinstance(health_url, str) else "")
            if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ManifestError(f"{label}.service.health_url must be loopback HTTP")
            startup = service.get("startup_timeout_seconds")
            if not isinstance(startup, int) or not 1 <= startup <= 600:
                raise ManifestError(
                    f"{label}.service.startup_timeout_seconds must be between 1 and 600"
                )


def expand_command(command: list[str], temp_dir: Path) -> list[str]:
    replacements = {
        "{python}": sys.executable,
        "{root}": str(ROOT),
        "{temp}": str(temp_dir),
    }
    expanded: list[str] = []
    for item in command:
        for token, replacement in replacements.items():
            item = item.replace(token, replacement)
        expanded.append(item)
    return expanded


def stop_process_tree(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass


def run_process(
    command: list[str], timeout: int, stdout_path: Path, stderr_path: Path
) -> tuple[int | None, bool, str | None]:
    try:
        with stdout_path.open("w", encoding="utf-8", errors="replace") as stdout_file, \
                stderr_path.open("w", encoding="utf-8", errors="replace") as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=stdout_file,
                stderr=stderr_file,
                stdin=subprocess.DEVNULL,
            )
            try:
                return process.wait(timeout=timeout), False, None
            except subprocess.TimeoutExpired:
                stop_process_tree(process)
                return None, True, f"timed out after {timeout} seconds"
    except OSError as exc:
        stderr_path.write_text(str(exc), encoding="utf-8")
        return None, False, f"failed to start: {exc}"


def wait_for_health(url: str, timeout: int, service: subprocess.Popen[Any]) -> str | None:
    deadline = time.monotonic() + timeout
    last_error = "service did not become healthy"
    while time.monotonic() < deadline:
        if service.poll() is not None:
            return f"service exited before health check (exit {service.returncode})"
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return None
                last_error = f"health check returned HTTP {response.status}"
        except Exception as exc:  # the final error is evidence, retries are intentional
            last_error = str(exc)
        time.sleep(0.5)
    return f"startup timed out after {timeout} seconds: {last_error}"


def capture_failure_evidence(gate: dict[str, Any], run_dir: Path) -> list[dict[str, Any]]:
    relative = gate.get("failure_evidence")
    if not isinstance(relative, str) or not relative:
        return []
    source = (ROOT / relative).resolve()
    if not source.is_relative_to(ROOT) or not source.is_file():
        return [{"path": relative, "exists": False}]
    captured: list[dict[str, Any]] = []
    destination = run_dir / f"{gate['id']}.failure-evidence.json"
    shutil.copy2(source, destination)
    captured.append({"path": str(destination.relative_to(ROOT)), "exists": True})
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return captured
    for name in payload.get("screenshots", []):
        if not isinstance(name, str) or Path(name).name != name:
            continue
        screenshot = (source.parent / name).resolve()
        if not screenshot.is_relative_to(source.parent.resolve()) or not screenshot.is_file():
            continue
        screenshot_destination = run_dir / f"{gate['id']}.{name}"
        shutil.copy2(screenshot, screenshot_destination)
        captured.append({"path": str(screenshot_destination.relative_to(ROOT)), "exists": True})
    return captured


def collect_required_evidence(
    gate: dict[str, Any], before: dict[str, int] | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    before = before or {}
    require_fresh = gate.get("evidence_freshness", "existing") == "generated"
    evidence = []
    for item in gate.get("evidence", []):
        path = ROOT / item
        exists = path.is_file()
        entry: dict[str, Any] = {"path": item, "exists": exists}
        if exists:
            stat = path.stat()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entry.update({
                "size_bytes": stat.st_size,
                "sha256": digest,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                "fresh": (item not in before or stat.st_mtime_ns != before[item]) if require_fresh else None,
            })
        evidence.append(entry)
    missing = [item["path"] for item in evidence if not item["exists"]]
    stale = [item["path"] for item in evidence if item.get("fresh") is False]
    failure = f"required evidence missing: {', '.join(missing)}" if missing else None
    if failure is None and stale:
        failure = f"required evidence not refreshed: {', '.join(stale)}"
    return evidence, failure


def run_gate(gate: dict[str, Any], run_dir: Path, temp_dir: Path) -> dict[str, Any]:
    gate_id = gate["id"]
    stdout_path = run_dir / f"{gate_id}.stdout.log"
    stderr_path = run_dir / f"{gate_id}.stderr.log"
    started = time.monotonic()
    evidence_before = {
        item: (ROOT / item).stat().st_mtime_ns
        for item in gate.get("evidence", [])
        if (ROOT / item).is_file()
    }
    exit_code: int | None = None
    failure: str | None = None
    timed_out = False
    service_logs: list[str] = []

    if gate["type"] == "command":
        exit_code, timed_out, failure = run_process(
            expand_command(gate["command"], temp_dir),
            gate["timeout_seconds"],
            stdout_path,
            stderr_path,
        )
    else:
        service = gate["service"]
        service_stdout = run_dir / f"{gate_id}.service.stdout.log"
        service_stderr = run_dir / f"{gate_id}.service.stderr.log"
        service_logs = [str(service_stdout.relative_to(ROOT)), str(service_stderr.relative_to(ROOT))]
        service_process: subprocess.Popen[Any] | None = None
        try:
            with service_stdout.open("w", encoding="utf-8", errors="replace") as out_file, \
                    service_stderr.open("w", encoding="utf-8", errors="replace") as err_file:
                service_process = subprocess.Popen(
                    expand_command(service["command"], temp_dir),
                    cwd=ROOT,
                    stdout=out_file,
                    stderr=err_file,
                    stdin=subprocess.DEVNULL,
                )
                failure = wait_for_health(
                    service["health_url"],
                    service["startup_timeout_seconds"],
                    service_process,
                )
                if failure is None:
                    exit_code, timed_out, failure = run_process(
                        expand_command(gate["command"], temp_dir),
                        gate["timeout_seconds"],
                        stdout_path,
                        stderr_path,
                    )
                else:
                    stdout_path.write_text("", encoding="utf-8")
                    stderr_path.write_text(failure, encoding="utf-8")
        except OSError as exc:
            failure = f"failed to start service: {exc}"
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text(failure, encoding="utf-8")
        finally:
            if service_process is not None:
                stop_process_tree(service_process)

    if failure is None and exit_code != 0:
        failure = f"command exited with code {exit_code}"
    evidence, evidence_failure = collect_required_evidence(gate, evidence_before)
    if failure is None and evidence_failure is not None:
        failure = evidence_failure
    status = "passed" if failure is None and exit_code == 0 else "failed"
    if status == "failed":
        evidence.extend(capture_failure_evidence(gate, run_dir))
    return {
        "id": gate_id,
        "category": gate["category"],
        "status": status,
        "required": gate["required"],
        "exit_code": exit_code,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
        "stdout_log": str(stdout_path.relative_to(ROOT)),
        "stderr_log": str(stderr_path.relative_to(ROOT)),
        "service_logs": service_logs,
        "evidence": evidence,
        "failure_reason": failure,
    }


def git_environment() -> tuple[str | None, bool | None]:
    prefix = ["git", "-c", f"safe.directory={ROOT}", "-C", str(ROOT)]
    try:
        commit = subprocess.run(
            [*prefix, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
        status = subprocess.run(
            [*prefix, "status", "--porcelain"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    return (commit.stdout.strip() or None), bool(status.stdout.strip()) if status.returncode == 0 else None


def write_report(path: Path, report: dict[str, Any]) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", nargs="?", help="manifest profile to execute")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--list", action="store_true", help="validate and list profiles/gates")
    args = parser.parse_args()

    try:
        manifest, manifest_hash = load_manifest(args.manifest.resolve())
    except (OSError, ManifestError) as exc:
        print(f"MANIFEST ERROR: {exc}", file=sys.stderr)
        return 2

    if args.list:
        print("profiles: " + ", ".join(manifest["profiles"]))
        for gate in manifest["gates"]:
            print(f"{gate['id']}: {','.join(gate['profiles'])}")
        return 0
    if args.profile not in manifest["profiles"]:
        parser.error("profile is required and must be one of: " + ", ".join(manifest["profiles"]))

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{os.getpid()}"
    report_root = args.report_root.resolve()
    run_dir = report_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    temp_dir = Path(tempfile.mkdtemp(prefix=f"{manifest['project']}-{run_id}-"))
    started_at = utc_now()
    started_clock = time.monotonic()
    results: list[dict[str, Any]] = []
    blocked = False
    try:
        for gate in manifest["gates"]:
            if args.profile not in gate["profiles"]:
                continue
            if blocked:
                results.append({
                    "id": gate["id"], "category": gate["category"], "status": "skipped",
                    "required": gate["required"], "exit_code": None, "duration_seconds": 0.0,
                    "timed_out": False, "stdout_log": None, "stderr_log": None,
                    "service_logs": [], "evidence": [],
                    "failure_reason": "skipped after an earlier required gate failed",
                })
                print(f"[SKIP] {gate['id']}")
                continue
            result = run_gate(gate, run_dir, temp_dir)
            results.append(result)
            print(f"[{result['status'].upper()}] {gate['id']} ({result['duration_seconds']:.3f}s)")
            if result["status"] == "failed" and gate["required"]:
                blocked = True
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    commit, dirty = git_environment()
    passed = sum(item["status"] == "passed" for item in results)
    failed = sum(item["status"] == "failed" for item in results)
    skipped = sum(item["status"] == "skipped" for item in results)
    report = {
        "schema_version": SCHEMA_VERSION,
        "project": manifest["project"],
        "profile": args.profile,
        "manifest_sha256": manifest_hash,
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_seconds": round(time.monotonic() - started_clock, 3),
        "status": "failed" if any(item["status"] == "failed" and item["required"] for item in results) else "passed",
        "environment": {
            "platform": platform.platform(),
            "runtime": sys.version.split()[0],
            "git_commit": commit,
            "git_dirty": dirty,
        },
        "summary": {"total": len(results), "passed": passed, "failed": failed, "skipped": skipped},
        "gates": results,
    }
    report_path = run_dir / "acceptance-report.json"
    write_report(report_path, report)
    print(f"report: {report_path}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
