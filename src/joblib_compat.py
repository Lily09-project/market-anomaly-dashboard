from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

try:
    import joblib as _joblib
except Exception:
    _joblib = None


def dump(value: Any, filename: str | Path) -> list[str]:
    if _joblib is None:
        raise RuntimeError("joblib is required to write model artifacts.")
    return _joblib.dump(value, filename)


def load(filename: str | Path) -> Any:
    if _joblib is None:
        raise RuntimeError("joblib is required to read model artifacts.")
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Setting the shape on a NumPy array has been deprecated.*",
            category=DeprecationWarning,
            module=r"joblib\.numpy_pickle",
        )
        return _joblib.load(Path(filename))
