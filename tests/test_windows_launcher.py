"""Windows acceptance is executable CI, not only textual launcher checks."""
from pathlib import Path


def test_launcher_requires_the_locked_python_version():
    source = Path("run_project.bat").read_text(encoding="utf-8")
    assert "py -3.12 --version" in source
    assert "sys.version_info[:2] == (3, 12)" in source
    assert "Install Python 3.10+" not in source
    assert 'set "PY_ARGS=-3"' not in source
    assert "Existing .venv must use Python 3.12" in source


def test_windows_ci_executes_the_real_noninteractive_launcher():
    source = Path(".github/workflows/windows-launcher.yml").read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in source
    assert "call run_project.bat --validate" in source
    assert "continue-on-error" not in source
    assert "persist-credentials: false" in source
