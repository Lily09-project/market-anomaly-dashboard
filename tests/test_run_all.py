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
