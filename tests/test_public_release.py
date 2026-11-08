from __future__ import annotations

import re

from src.utils import project_path


def test_runtime_and_development_dependencies_are_separated() -> None:
    runtime = project_path("requirements.txt").read_text(encoding="utf-8")
    development = project_path("requirements-dev.txt").read_text(encoding="utf-8")
    for tool in ("pytest", "bandit", "pip-audit", "ruff"):
        assert tool not in runtime
        assert tool in development
    assert "-r requirements.txt" in development


def test_container_uses_source_backed_data_and_serves_it_unprivileged() -> None:
    dockerfile = project_path("Dockerfile").read_text(encoding="utf-8")
    release_data_command = "python run_all.py --mode api --require-api"
    assert release_data_command in dockerfile
    assert "python run_all.py --mode sample" not in dockerfile
    assert "npm run build" in dockerfile
    assert "nginx-unprivileged" in dockerfile
    assert "USER 101" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert dockerfile.index(release_data_command) < dockerfile.index("npm run build") < dockerfile.index("USER 101")
    nginx = project_path("deploy/nginx.conf").read_text(encoding="utf-8")
    assert "Content-Security-Policy" in nginx
    assert "frame-ancestors 'none'" in nginx
    assert "server_tokens off" in nginx
    assert "location = /healthz" in nginx


def test_container_python_matches_ci_and_pages() -> None:
    expected = project_path(".python-version").read_text(encoding="utf-8").strip()
    dockerfile = project_path("Dockerfile").read_text(encoding="utf-8")
    images = re.findall(r"^FROM python:(\d+\.\d+)-slim@sha256:[0-9a-f]{64} AS data$", dockerfile, re.MULTILINE)
    assert images == [expected]
    for workflow in project_path(".github/workflows").glob("*.yml"):
        for version in re.findall(r'python-version: "([^"]+)"', workflow.read_text(encoding="utf-8")):
            assert version == expected, workflow.name
    dependabot = project_path(".github/dependabot.yml").read_text(encoding="utf-8")
    docker = dependabot.split("package-ecosystem: docker", 1)[1].split("package-ecosystem:", 1)[0]
    assert "dependency-name: python" in docker
    assert "version-update:semver-minor" in docker
    assert "version-update:semver-major" in docker


def test_nginx_caches_fingerprinted_assets_without_dropping_security_headers() -> None:
    nginx = project_path("deploy/nginx.conf").read_text(encoding="utf-8")
    locations = re.findall(r"^    location ([^{\n]+)\{(.*?)\n    \}", nginx, re.DOTALL | re.MULTILINE)
    blocks = {path.strip(): body for path, body in locations}
    assert 'Cache-Control "public, max-age=31536000, immutable"' in blocks["/assets/"]
    assert 'Cache-Control "no-cache"' in blocks["/"]
    assert 'Cache-Control "no-cache"' in blocks["/data/"]
    for path, body in blocks.items():
        if "add_header" not in body:
            continue
        # add_header inside a location replaces the server-level headers.
        for header in ("X-Content-Type-Options", "Referrer-Policy", "X-Frame-Options", "frame-ancestors 'none'"):
            assert header in body, (path, header)


def test_github_actions_build_and_check_the_container() -> None:
    workflow = project_path(".github/workflows/security.yml").read_text(encoding="utf-8")
    assert "container-build:" in workflow
    assert "docker build --tag market-regime-lab:ci ." in workflow
    assert "http://127.0.0.1:8080/healthz" in workflow
    assert "content-security-policy" in workflow
    assert "docker logs" in workflow
    assert "/data/provenance.json" in workflow
    assert 'provenance.get("provider") == "finmind"' in workflow
    assert 'provenance.get("is_simulated") is False' in workflow
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
        entries = [
            line
            for line in lock.replace("\\\n", " ").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        assert entries
        for entry in entries:
            requirement = entry.split("--hash=", 1)[0]
            assert "==" in requirement, entry
            assert "--hash=sha256:" in entry, f"missing hashes: {requirement}"


def test_gitignore_keeps_generated_and_secret_files_out() -> None:
    gitignore = project_path(".gitignore").read_text(encoding="utf-8")
    for token in ("web/node_modules/", "web/dist/", "web/public/data/", "data/sample/", ".env.*", "!.env.example", "*.pem", "*.key", "credentials*.json"):
        assert token in gitignore, token
