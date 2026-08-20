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
    "requests",
    "scikit-learn",
    "streamlit",
    "gitpython",
    "plotly",
    "matplotlib",
    "joblib",
    "pyyaml",
    "yfinance",
}
FORBIDDEN_TRACKED_PREFIXES = (
    ".env/",
    "data/raw/",
    "data/processed/",
    "data/cache/",
    "models/",
    "reports/metrics/",
    "reports/figures/",
)


def _normalise_package_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value.strip().lower())


def _lock_packages(path: Path) -> set[str]:
    packages = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~;\[]", line, maxsplit=1)[0]
        packages.add(_normalise_package_name(name))
    return packages


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],  # nosec B603, B607
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.replace("\\", "/") for line in result.stdout.splitlines() if line]


def run_checks() -> list[str]:
    failures: list[str] = []
    runtime_lock = PROJECT_ROOT / "requirements-runtime.lock"
    dev_lock = PROJECT_ROOT / "requirements-dev.lock"
    if not runtime_lock.exists():
        failures.append("requirements-runtime.lock is missing")
    else:
        packages = _lock_packages(runtime_lock)
        missing = sorted(_normalise_package_name(item) for item in REQUIRED_RUNTIME - packages)
        if missing:
            failures.append(f"runtime lock is missing: {', '.join(missing)}")
        if any("==" not in line for line in runtime_lock.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")):
            failures.append("runtime lock contains an unpinned dependency")
    if not dev_lock.exists():
        failures.append("requirements-dev.lock is missing")

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

    config_text = (PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    if "port = 8765" not in config_text:
        failures.append("Streamlit fixed port is not 8765")
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    if "USER appuser" not in dockerfile:
        failures.append("Dockerfile does not drop root privileges")
    if "HEALTHCHECK" not in dockerfile:
        failures.append("Dockerfile has no healthcheck")
    return failures


def main() -> int:
    failures = run_checks()
    if failures:
        for failure in failures:
            print(f"[FAIL] {failure}")
        return 1
    print("[PASS] release manifest, public-file boundary, fixed port, and container checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
