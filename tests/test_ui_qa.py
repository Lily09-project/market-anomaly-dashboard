from __future__ import annotations

import json
from pathlib import Path

from scripts.ui_qa import (
    PAGE_CONTRACTS,
    PAGE_LOAD_STATE,
    STREAMLIT_EXCEPTION_SELECTOR,
    VIEWPORTS,
    describe_console_error,
    missing_page_contracts,
    write_failure_evidence,
)


class _ConsoleMessage:
    text = "Failed to load resource: net::ERR_CONNECTION_FAILED"
    location = {"url": "https://example.invalid/font.woff2"}


def test_ui_page_contracts_cover_all_public_routes() -> None:
    assert set(PAGE_CONTRACTS) == {"stocks", "radar", "anomalies", "compare"}
    assert PAGE_LOAD_STATE == "domcontentloaded"


def test_console_error_includes_originating_resource_url() -> None:
    assert describe_console_error(_ConsoleMessage()).endswith(
        "@ https://example.invalid/font.woff2"
    )


def test_ui_page_contract_reports_missing_content() -> None:
    assert missing_page_contracts("stocks", "股票分析\n大盤指數") == []
    assert missing_page_contracts("stocks", "股票分析") == ["大盤指數"]


def test_ui_page_contract_rejects_unknown_route() -> None:
    assert missing_page_contracts("unknown", "任何內容") == ["unknown route"]

def test_ui_qa_checks_streamlit_runtime_exceptions() -> None:
    assert STREAMLIT_EXCEPTION_SELECTOR == '[data-testid="stException"]'


def test_ui_qa_covers_small_phone_and_landscape_layouts() -> None:
    viewports = {name: (width, height) for name, width, height in VIEWPORTS}

    assert viewports["desktop"] == (1440, 1000)
    assert viewports["small-mobile"][0] == 375
    assert viewports["landscape"][0] > viewports["landscape"][1]


def test_browser_failure_evidence_is_structured_and_atomic(tmp_path: Path) -> None:
    (tmp_path / "failure-stocks-mobile.png").write_bytes(b"png")
    (tmp_path / "stocks-mobile.png").write_bytes(b"png")
    path = write_failure_evidence("http://127.0.0.1:8765", tmp_path, "mobile/stocks: console error")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert "mobile/stocks" in payload["error"]
    assert payload["screenshots"] == ["failure-stocks-mobile.png", "stocks-mobile.png"]
    assert not (tmp_path / "failure-evidence.json.tmp").exists()
