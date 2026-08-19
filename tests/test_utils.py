from __future__ import annotations

import pandas as pd
import pytest

from src.utils import (
    MAX_HTTP_RESPONSE_BYTES,
    atomic_write_dataframe,
    normalize_http_timeout,
    read_http_response_bytes,
    safe_exception_message,
    write_json,
)


def test_atomic_write_dataframe_replaces_existing_complete_file(tmp_path) -> None:
    path = tmp_path / "output.csv"
    atomic_write_dataframe(pd.DataFrame({"value": [1, 2]}), path)
    atomic_write_dataframe(pd.DataFrame({"value": [3, 4]}), path)

    written = pd.read_csv(path)
    assert written["value"].tolist() == [3, 4]
    assert list(tmp_path.glob(".output.csv.*.tmp")) == []


def test_write_json_replaces_existing_complete_file(tmp_path) -> None:
    path = tmp_path / "summary.json"
    write_json({"status": "old"}, path)
    write_json({"status": "new", "rows": 2}, path)

    assert path.read_text(encoding="utf-8") == '{\n  "status": "new",\n  "rows": 2\n}'
    assert list(tmp_path.glob(".summary.json.*.tmp")) == []


def test_normalize_http_timeout_rejects_invalid_values() -> None:
    assert normalize_http_timeout(None) == 15.0
    assert normalize_http_timeout("invalid", default=8.0) == 8.0
    assert normalize_http_timeout(0) == 15.0
    assert normalize_http_timeout(-5) == 15.0
    assert normalize_http_timeout(12) == 12.0
    assert normalize_http_timeout(120) == 60.0


def test_read_http_response_bytes_enforces_header_and_stream_limits() -> None:
    class Response:
        headers = {"content-length": str(MAX_HTTP_RESPONSE_BYTES + 1)}

        def iter_content(self, chunk_size: int):
            yield b"ignored"

    with pytest.raises(ValueError, match="exceeds"):
        read_http_response_bytes(Response())

    class ChunkedResponse:
        headers = {}

        def iter_content(self, chunk_size: int):
            yield b"a" * MAX_HTTP_RESPONSE_BYTES
            yield b"b"

    with pytest.raises(ValueError, match="exceeds"):
        read_http_response_bytes(ChunkedResponse())


def test_safe_exception_message_redacts_url_query_secrets() -> None:
    message = safe_exception_message(
        RuntimeError("GET https://example.test/data?api_key=secret-value&token=another-secret failed")
    )

    assert "secret-value" not in message
    assert "another-secret" not in message
    assert "[REDACTED]" in message
