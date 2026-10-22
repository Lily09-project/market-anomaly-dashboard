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

@pytest.mark.parametrize("lock_path", LOCK_FILES)
@pytest.mark.parametrize(
    ("name", "floor", "unsafe_version"),
    [("streamlit", "1.66.1", "1.66.0"), ("pillow", "13.0.0", "12.3.0")],
)
def test_security_floors_cannot_regress(lock_path, name, floor, unsafe_version):
    direct = {
        canonicalize_name(item.name): item for item in read_requirements("requirements.txt")
    }
    locked = {
        canonicalize_name(item.name): item for item in read_requirements(lock_path)
    }
    assert name in direct, f"Missing explicit security floor for {name}"
    assert direct[name].specifier.contains(floor)
    assert not direct[name].specifier.contains(unsafe_version)
    pins = list(locked[name].specifier)
    assert len(pins) == 1 and pins[0].operator == "=="
    assert Requirement(f"{name}>={floor}").specifier.contains(pins[0].version)
