from __future__ import annotations

from scripts.verify_release import run_checks


def test_release_checks_pass_for_public_repository_boundary() -> None:
    assert run_checks() == []
