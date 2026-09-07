from __future__ import annotations

from run_all import run_pipeline
from src.smoke_test import assert_bat_files_are_valid
from src.utils import load_config, project_path


def test_run_all_sample_mode_outputs_required_files() -> None:
    run_pipeline("sample")
    cfg = load_config()
    required = [
        "run_all.py",
        "run_project.bat",
        cfg["data"]["features_path"],
        cfg["data"]["results_path"],
        cfg["model"]["path"],
        cfg["reports"]["evaluation_summary_path"],
    ]
    for path in required:
        assert project_path(path).exists(), f"Missing {path}"


def test_bat_files_are_valid() -> None:
    assert_bat_files_are_valid()
    bat = project_path("run_project.bat").read_text(encoding="utf-8")
    assert 'findstr /R /C:":%STREAMLIT_PORT% .*LISTENING"' in bat
    assert "[ERROR] Port %STREAMLIT_PORT% is already in use." in bat


def test_windows_launcher_has_complete_fail_closed_validation_mode() -> None:
    bat = project_path("run_project.bat").read_text(encoding="utf-8")

    for command in (
        "chcp 65001 >nul",
        'set "PYTHONUTF8=1"',
        'set "PYTHONIOENCODING=utf-8"',
        '"%VENV_PY%" -m pip install --upgrade "pip>=26.2"',
        '"%VENV_PY%" -W error -m pytest',
        '"%VENV_PY%" -m compileall -q app.py src scripts tests',
        '"%VENV_PY%" -m pip check',
        '"%VENV_PY%" scripts\\verify_release.py',
        '"%VENV_PY%" -m bandit -q -r app.py src scripts',
        '"%VENV_PY%" -m pip_audit --strict --progress-spinner off',
    ):
        assert command in bat
    assert 'if /I "%~1"=="--validate"' in bat
    assert 'if /I "%~1"=="--validate" goto :port_ready' in bat
    assert ":port_ready" in bat
    assert 'if exist "%CD%\\.venv\\Scripts\\python.exe"' in bat
    assert 'if defined PY_EXE goto :python_ready' in bat
    assert "%userprofile%\\.cache\\" not in bat.lower()
    assert 'if /I "%~1"=="--help" goto :usage' in bat
    assert "[ERROR] Unsupported argument: %~1" in bat
    assert "exit /b 2" in bat
    assert "Validation completed successfully. Streamlit launch skipped." in bat
