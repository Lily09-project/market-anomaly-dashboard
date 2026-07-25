from __future__ import annotations

import pickle
import warnings
from pathlib import Path
from typing import Any

try:
    import joblib as _joblib
except Exception:
    _joblib = None


def dump(value: Any, filename: str | Path) -> list[str]:
    if _joblib is not None:
        return _joblib.dump(value, filename)
    path = Path(filename)
    with path.open("wb") as f:
        pickle.dump(value, f)
    return [str(path)]


def load(filename: str | Path) -> Any:
    if _joblib is not None:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Setting the shape on a NumPy array has been deprecated.*",
                category=DeprecationWarning,
                module=r"joblib\.numpy_pickle",
            )
            return _joblib.load(filename)
    with Path(filename).open("rb") as f:
        return pickle.load(f)
