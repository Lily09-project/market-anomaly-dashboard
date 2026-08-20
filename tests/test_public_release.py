from __future__ import annotations

from src.utils import project_path


def test_runtime_and_development_dependencies_are_separated() -> None:
    runtime = project_path("requirements.txt").read_text(encoding="utf-8")
    development = project_path("requirements-dev.txt").read_text(encoding="utf-8")

    assert "pytest" not in runtime
    assert "bandit" not in runtime
    assert "pip-audit" not in runtime
    assert "-r requirements.txt" in development
    assert "pytest" in development
    assert "bandit" in development
    assert "pip-audit" in development


def test_container_runs_unprivileged_with_healthcheck() -> None:
    dockerfile = project_path("Dockerfile").read_text(encoding="utf-8")

    assert "USER appuser" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "/_stcore/health" in dockerfile
    assert "--server.address=0.0.0.0" in dockerfile
    assert "python run_all.py --mode sample" in dockerfile
    assert "chown -R appuser:appuser /app" in dockerfile
    assert dockerfile.index("python run_all.py --mode sample") < dockerfile.index("USER appuser")
    assert dockerfile.index("USER appuser") < dockerfile.index("CMD [\"streamlit\"")


def test_public_user_and_deployment_guides_cover_product_states() -> None:
    user_guide = project_path("docs/user-guide.md").read_text(encoding="utf-8")
    deployment = project_path("docs/deployment.md").read_text(encoding="utf-8")
    launcher = project_path("run_project.bat").read_text(encoding="utf-8")

    for state in ("LIVE", "部分連線", "DEMO", "離線"):
        assert state in user_guide
    assert "不寫入磁碟" in user_guide
    assert "unprivileged" in deployment
    assert "requirements-dev.txt" in launcher
    assert "Operational security boundary" in deployment
    assert "rate limits" in deployment
    assert "2 MiB" in deployment

def test_github_actions_builds_and_health_checks_container() -> None:
    workflow = project_path(".github/workflows/security.yml").read_text(encoding="utf-8")

    assert "container-build:" in workflow
    assert "docker build --tag research-trust-workbench:ci ." in workflow
    assert "docker run --detach --publish 8765:8765" in workflow
    assert "http://127.0.0.1:8765/_stcore/health" in workflow
    assert "docker logs" in workflow


def test_github_actions_runs_locked_release_and_browser_gates() -> None:
    workflow = project_path(".github/workflows/security.yml").read_text(encoding="utf-8")

    assert "concurrency:" in workflow
    assert "group: security-${{ github.workflow }}-${{ github.ref }}" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "pip install --requirement requirements-dev.lock" in workflow
    assert "python scripts/verify_release.py" in workflow
    assert "python -W error -m pytest" in workflow
    assert "--requirement requirements-e2e.txt" in workflow
    assert "python -m playwright install --with-deps chromium" in workflow
    assert "browser-ui:" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "python scripts/ui_qa.py --url http://127.0.0.1:8765" in workflow
    assert workflow.count("actions/checkout@08c6903cd8c0fde910a37f88322edcfb5dd907a8") == 3

    e2e_requirements = project_path("requirements-e2e.txt").read_text(encoding="utf-8")
    assert "playwright==1.58.0" in e2e_requirements
    assert "docs/screenshots/ui-qa/" in project_path(".gitignore").read_text(encoding="utf-8")
