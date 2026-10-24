"""Windows acceptance is executable CI, not only textual launcher checks."""
from pathlib import Path


def _launcher() -> str:
    return Path("run_project.bat").read_text(encoding="utf-8")


def test_launcher_requires_the_locked_python_version():
    source = _launcher()
    assert "py -3.12 --version" in source
    assert "sys.version_info[:2] == (3, 12)" in source
    assert "Existing .venv must use Python 3.12" in source
    assert source.count("\n:python_ready\n") == 1


def test_launcher_never_deletes_an_existing_environment():
    source = _launcher()
    assert 'rmdir /s /q ".venv"' not in source
    assert "Existing .venv is broken. Preserve or move it" in source


def test_validation_runs_every_gate_and_never_starts_the_site():
    source = _launcher()
    for command in (
        "-m pip check",
        "run_all.py --mode sample",
        '-W error -m pytest -q -p no:cacheprovider --basetemp "%PYTEST_BASETEMP%"',
        "scripts\\verify_release.py",
        "-m bandit -q -r run_all.py src scripts",
        "-m ruff check run_all.py src scripts tests",
        "-m pip_audit --strict --progress-spinner off",
        "call npm ci --no-audit --no-fund",
        "call npm run typecheck",
        "call npm run lint",
        "call npm run coverage",
        "call npm run build",
        "call npm run size",
    ):
        assert command in source, command
    assert source.index("Validation completed successfully. Web server launch skipped.") < source.index("Starting Market Regime Lab")
    assert "call npm run preview -- --host 127.0.0.1" in source
    assert "[ERROR] Unsupported argument: %~1" in source
    assert "exit /b 2" in source
    assert 'if /I not "%~1"=="--validate" pause' in source


def test_windows_ci_executes_the_real_noninteractive_launcher():
    source = Path(".github/workflows/windows-launcher.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in source
    assert "call run_project.bat --validate" in source
    assert "actions/setup-node@" in source
    assert "continue-on-error" not in source
    assert "persist-credentials: false" in source
