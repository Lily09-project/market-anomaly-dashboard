from __future__ import annotations

import gc
import sys


def pytest_sessionfinish() -> None:
    """Close Streamlit 1.58's module-level AppTest temporary directory."""
    app_test_module = sys.modules.get("streamlit.testing.v1.app_test")
    temporary_directory = getattr(app_test_module, "TMP_DIR", None)
    if temporary_directory is not None:
        temporary_directory.cleanup()
    gc.collect()
