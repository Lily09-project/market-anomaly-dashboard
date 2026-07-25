from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import joblib_compat
from src.utils import load_config, project_path


def assert_bat_files_are_valid() -> None:
    bat_path = project_path("run_project.bat")
    if not bat_path.exists():
        raise FileNotFoundError("Missing run_project.bat")

    bat = bat_path.read_text(encoding="utf-8")

    forbidden = ["PYTHON_CMD", "mkdir py", "mkdir -3"]
    for item in forbidden:
        if item in bat:
            raise AssertionError(f"BAT file contains forbidden string: {item}")

    required = [
        'set "PY_EXE="',
        'set "PY_ARGS="',
        "python --version >nul 2>nul",
        "py -3 --version >nul 2>nul",
        'set "CODEX_BUNDLED_PY=%USERPROFILE%\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe"',
        '"%CODEX_BUNDLED_PY%" --version >nul 2>nul',
        'set "STREAMLIT_PORT=8765"',
        'set "VENV_PY=%CD%\\.venv\\Scripts\\python.exe"',
        '"%PY_EXE%" %PY_ARGS% -m venv .venv',
        '"%VENV_PY%" -m pip install -r requirements.txt',
        '"%VENV_PY%" -m pytest -q',
        '"%VENV_PY%" -m streamlit run app.py',
        "--server.port %STREAMLIT_PORT%",
        "Using Python: %PY_EXE% %PY_ARGS%",
        "Project path: %CD%",
        "Fixed dashboard URL: http://localhost:%STREAMLIT_PORT%",
    ]
    for item in required:
        if item not in bat:
            raise AssertionError(f"BAT file missing required string: {item}")

    direct_streamlit_lines = [
        line.strip().lower()
        for line in bat.splitlines()
        if line.strip() and not line.strip().lower().startswith(("rem", "echo"))
    ]
    if "streamlit run app.py" in direct_streamlit_lines:
        raise AssertionError("BAT file directly calls streamlit instead of .venv Python.")


def run_smoke_test(config: dict | None = None) -> bool:
    cfg = config or load_config()
    assert_bat_files_are_valid()

    required_paths = [
        project_path("run_project.bat"),
        project_path(cfg["data"]["features_path"]),
        project_path(cfg["data"]["results_path"]),
        project_path(cfg["model"]["path"]),
        project_path(cfg["reports"]["evaluation_summary_path"]),
        project_path("app.py"),
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required files: {missing}")

    features = pd.read_csv(project_path(cfg["data"]["features_path"]))
    results = pd.read_csv(project_path(cfg["data"]["results_path"]))
    required_feature_columns = {"date", "symbol", "close", "volatility_20", "risk_score_baseline"}
    required_result_columns = required_feature_columns | {"model_anomaly", "anomaly_score", "pseudo_anomaly"}
    if features.empty or results.empty:
        raise AssertionError("Feature or result data is empty.")
    if missing_cols := sorted(required_feature_columns - set(features.columns)):
        raise AssertionError(f"Feature data missing columns: {missing_cols}")
    if missing_cols := sorted(required_result_columns - set(results.columns)):
        raise AssertionError(f"Result data missing columns: {missing_cols}")

    loaded = joblib_compat.load(project_path(cfg["model"]["path"]))
    if "model" not in loaded or "features" not in loaded:
        raise AssertionError("Model artifact is missing model or feature metadata.")
    compile(project_path("app.py").read_text(encoding="utf-8"), "app.py", "exec")
    import app  # noqa: F401

    print("Smoke test passed.")
    return True


if __name__ == "__main__":
    run_smoke_test()
