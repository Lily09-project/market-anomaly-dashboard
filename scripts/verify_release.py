from __future__ import annotations

import re
# This invokes a fixed git command without shell expansion.
import subprocess  # nosec B404
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_RUNTIME = {
    "pandas",
    "numpy",
    "pyyaml",
    "requests",
    "urllib3",
    "certifi",
}
FORBIDDEN_TRACKED_PREFIXES = (
    ".env/",
    "data/raw/",
    "data/processed/",
    "data/cache/",
    "models/",
    "reports/metrics/",
    "reports/figures/",
    "web/node_modules/",
    "web/dist/",
    "web/public/data/",
    "data/sample/",
)


def _normalise_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value.strip().lower())


def _lock_entries(path: Path) -> list[str]:
    """Return logical lock lines, joining backslash continuations (hash format)."""
    entries: list[str] = []
    pending = ""
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        entries.append((pending + line).strip())
        pending = ""
    if pending.strip():
        entries.append(pending.strip())
    return [entry for entry in entries if not entry.startswith("-")]


def _split_lock_entry(entry: str) -> tuple[str, list[str]]:
    """Split a lock entry into its requirement and its --hash values."""
    parts = entry.split()
    hashes = [part.split("=", 1)[1] for part in parts if part.startswith("--hash=")]
    requirement = " ".join(part for part in parts if not part.startswith("--hash="))
    return requirement, hashes


def _lock_packages(path: Path) -> set[str]:
    packages = set()
    for entry in _lock_entries(path):
        requirement, _ = _split_lock_entry(entry)
        name = re.split(r"[<>=!~;\[ ]", requirement, maxsplit=1)[0]
        packages.add(_normalise_package_name(name))
    return packages


def _lock_format_failures(path: Path) -> list[str]:
    failures = []
    for entry in _lock_entries(path):
        requirement, hashes = _split_lock_entry(entry)
        if "==" not in requirement:
            failures.append(f"{path.name} contains an unpinned dependency: {requirement}")
        if not hashes or not all(value.startswith("sha256:") for value in hashes):
            failures.append(f"{path.name} has no sha256 hashes for: {requirement}")
    return failures


def _tracked_files() -> list[str]:
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={PROJECT_ROOT.as_posix()}",
            "ls-files",
        ],  # nosec B603, B607
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def run_checks() -> list[str]:
    failures: list[str] = []
    runtime_lock = PROJECT_ROOT / "requirements-runtime.lock.txt"
    dev_lock = PROJECT_ROOT / "requirements-dev.lock.txt"
    if not runtime_lock.exists():
        failures.append("requirements-runtime.lock.txt is missing")
    else:
        packages = _lock_packages(runtime_lock)
        missing = sorted(_normalise_package_name(item) for item in REQUIRED_RUNTIME - packages)
        if missing:
            failures.append(f"runtime lock is missing: {', '.join(missing)}")
        failures.extend(_lock_format_failures(runtime_lock))
    if not dev_lock.exists():
        failures.append("requirements-dev.lock.txt is missing")
    else:
        failures.extend(_lock_format_failures(dev_lock))

    try:
        tracked = _tracked_files()
    except (OSError, subprocess.CalledProcessError) as exc:
        failures.append(f"unable to inspect tracked files: {exc}")
    else:
        leaked = [
            path
            for path in tracked
            if path == ".env" or path.startswith(FORBIDDEN_TRACKED_PREFIXES)
        ]
        if leaked:
            failures.append("private/generated paths are tracked: " + ", ".join(leaked))

    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "USER 101" not in dockerfile:
        failures.append("Dockerfile does not drop root privileges")
    if "HEALTHCHECK" not in dockerfile:
        failures.append("Dockerfile has no healthcheck")
    index_html = (PROJECT_ROOT / "web" / "index.html").read_text(encoding="utf-8")
    if "Content-Security-Policy" not in index_html:
        failures.append("web/index.html does not declare a Content-Security-Policy")
    return failures


def main() -> int:
    failures = run_checks()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[PASS] release manifest, public-file boundary, CSP and container checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
