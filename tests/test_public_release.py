from __future__ import annotations

from src.utils import project_path


def test_runtime_and_development_dependencies_are_separated() -> None:
    runtime = project_path("requirements.txt").read_text(encoding="utf-8")
    development = project_path("requirements-dev.txt").read_text(encoding="utf-8")
    for tool in ("pytest", "bandit", "pip-audit", "ruff"):
        assert tool not in runtime
        assert tool in development
    assert "-r requirements.txt" in development


def test_container_builds_the_site_and_serves_it_unprivileged() -> None:
    dockerfile = project_path("Dockerfile").read_text(encoding="utf-8")
    assert "python run_all.py --mode sample" in dockerfile
    assert "npm run build" in dockerfile
    assert "nginx-unprivileged" in dockerfile
    assert "USER 101" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert dockerfile.index("python run_all.py --mode sample") < dockerfile.index("npm run build") < dockerfile.index("USER 101")
    nginx = project_path("deploy/nginx.conf").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in nginx
    assert "frame-ancestors 'none'" in nginx
    assert "server_tokens off" in nginx
    assert "location = /healthz" in nginx


def test_github_actions_build_and_check_the_container() -> None:
    workflow = project_path(".github/workflows/security.yml").read_text(encoding="utf-8")
    assert "container-build:" in workflow
    assert "docker build --tag market-regime-lab:ci ." in workflow
    assert "http://127.0.0.1:8080/healthz" in workflow
    assert "content-security-policy" in workflow
    assert "docker logs" in workflow
    assert "npm audit --audit-level=high" in workflow
    assert "gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e" in workflow


def test_quality_gate_runs_python_and_web_acceptance() -> None:
    workflow = project_path(".github/workflows/quality.yml").read_text(encoding="utf-8")
    for step in ("--cov-fail-under=90", "diff -r", "npm run typecheck", "npm run lint", "npm run coverage", "npm run size", "npm run e2e"):
        assert step in workflow, step
    pages = project_path(".github/workflows/pages.yml").read_text(encoding="utf-8")
    assert "path: web/dist" in pages
    assert "smoke:" in pages


def test_locks_pin_every_transitive_dependency() -> None:
    runtime_lock = project_path("requirements-runtime.lock.txt").read_text(encoding="utf-8")
    dev_lock = project_path("requirements-dev.lock.txt").read_text(encoding="utf-8")
    for token in ("certifi==", "numpy==", "pandas==", "urllib3==", "python-dateutil=="):
        assert token in runtime_lock
        assert token in dev_lock
    for token in ("bandit==", "pip-audit==", "pytest==", "pytest-cov==", "ruff=="):
        assert token in dev_lock
    for lock in (runtime_lock, dev_lock):
        assert all("==" in line for line in lock.splitlines() if line.strip() and not line.startswith("#"))


def test_gitignore_keeps_generated_and_secret_files_out() -> None:
    gitignore = project_path(".gitignore").read_text(encoding="utf-8")
    for token in ("web/node_modules/", "web/dist/", "web/public/data/", "data/sample/", ".env.*", "!.env.example", "*.pem", "*.key", "credentials*.json"):
        assert token in gitignore, token
