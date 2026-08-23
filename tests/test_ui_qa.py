from __future__ import annotations

from scripts.ui_qa import (
    PAGE_CONTRACTS,
    PAGE_LOAD_STATE,
    STREAMLIT_EXCEPTION_SELECTOR,
    VIEWPORTS,
    missing_page_contracts,
)


def test_ui_page_contracts_cover_all_public_routes() -> None:
    assert set(PAGE_CONTRACTS) == {"stocks", "radar", "anomalies", "compare"}
    assert PAGE_LOAD_STATE == "domcontentloaded"


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
