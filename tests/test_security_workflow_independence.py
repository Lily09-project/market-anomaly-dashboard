from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _job(workflow: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z_][a-zA-Z0-9_-]*:|\Z)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"Missing mandatory job: {name}"
    return match.group(1)


def test_dependency_audit_cannot_hide_source_validation() -> None:
    workflow = (ROOT / ".github/workflows/security.yml").read_text(encoding="utf-8")
    source = _job(workflow, "python-security")
    audit = _job(workflow, "dependency-audit")

    assert "python -m pip_audit --strict --progress-spinner off" in audit
    assert "pip_audit" not in source
    assert "python -m bandit" in source
    assert "python -m ruff check" in source
    for job in (source, audit):
        assert not re.search(r"^    (needs|if|continue-on-error):", job, re.MULTILINE)
        assert not re.search(r"^        (if|continue-on-error):", job, re.MULTILINE)
        assert "continue-on-error:" not in job
        assert "--ignore-vuln" not in job
        assert "|| true" not in job
