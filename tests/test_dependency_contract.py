"""Keep published install ranges and reproducible environments consistent."""
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


LOCK_FILES = ["requirements-dev.lock.txt","requirements-runtime.lock.txt"]


def read_requirements(path):
    return [
        Requirement(line.strip())
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith(("#", "-"))
    ]


@pytest.mark.parametrize("lock_path", LOCK_FILES)
def test_runtime_requirements_match_the_reproducible_lock(lock_path):
    locked = {canonicalize_name(item.name): item for item in read_requirements(lock_path)}
    for requirement in read_requirements("requirements.txt"):
        if requirement.marker is not None and not requirement.marker.evaluate({"python_version": "3.12"}):
            continue
        name = canonicalize_name(requirement.name)
        assert name in locked, f"{lock_path} is missing {name}"
        pins = list(locked[name].specifier)
        assert len(pins) == 1 and pins[0].operator == "==", f"{name} is not pinned"
        assert requirement.specifier.contains(pins[0].version), (
            f"{lock_path}: {name} {pins[0].version} violates {requirement.specifier}"
        )
