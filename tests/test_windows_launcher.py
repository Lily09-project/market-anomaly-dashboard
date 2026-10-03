"""Windows acceptance is executable CI, not only textual launcher checks."""
from pathlib import Path


def test_launcher_requires_the_locked_python_version():
    source = Path("run_project.bat").read_text(encoding="utf-8")
    assert "py -3.12 --version" in source
    assert "sys.version_info[:2] == (3, 12)" in source
    assert "Install Python 3.10+" not in source
    assert 'set "PY_ARGS=-3"' not in source
    assert "Existing .venv must use Python 3.12" in source
    assert source.count("\n:python_ready\n") == 1


def test_windows_ci_executes_the_real_noninteractive_launcher():
    source = Path(".github/workflows/windows-launcher.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in source
    assert "call run_project.bat --validate" in source
    assert "continue-on-error" not in source
    assert "persist-credentials: false" in source

def test_smoke_gate_accepts_locked_bootstrap_and_rejects_unversioned_launcher(tmp_path, monkeypatch):
    from src import smoke_test

    launcher = tmp_path / "run_project.bat"
    original = Path("run_project.bat").read_text(encoding="utf-8")
    launcher.write_text(original, encoding="utf-8")
    monkeypatch.setattr(smoke_test, "project_path", lambda _path: launcher)
    smoke_test.assert_bat_files_are_valid()
    launcher.write_text(original.replace("py -3.12 --version >nul 2>nul", "py -3 --version >nul 2>nul"), encoding="utf-8")
    import pytest
    with pytest.raises(AssertionError, match="py -3.12"):
        smoke_test.assert_bat_files_are_valid()
