from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
import streamlit.testing.v1.app_test as app_test_module

from run_all import run_pipeline
from src import market_api


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def cleanup_streamlit_test_directory():
    yield
    app_test_module.TMP_DIR.cleanup()


def test_dashboard_pages_and_sidebar_interactions(monkeypatch) -> None:
    run_pipeline("sample")
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.run(timeout=120)
    assert not app.exception
    assert len(app.get("plotly_chart")) >= 3
    assert len(app.dataframe) >= 2
    assert [button.label for button in app.button] == ["套用代號", "清除代號"]
    assert any("本機快取 / sample data" in item.value for item in app.markdown)
    assert any("研究摘要" in item.value for item in app.markdown)
    assert any("資料可信度" in item.value for item in app.markdown)
    assert any("sample data" in item.value for item in app.markdown)
    assert any("research-shell" in item.value for item in app.markdown)
    assert any("instrument-workspace" in item.value for item in app.markdown)
    assert any("evidence-grid" in item.value for item in app.markdown)

    app.text_input[0].set_value("<script>")
    app.button[0].click()
    app.run(timeout=120)
    assert not app.exception
    assert any("合法的 yfinance 英文代號" in warning.value for warning in app.warning)

    app.text_input[0].set_value("TSLA")
    app.button[0].click()
    app.run(timeout=120)
    assert not app.exception
    assert app.session_state["active_custom_stock_symbol"] == "TSLA"

    app.button[1].click()
    app.run(timeout=120)
    assert not app.exception
    assert app.session_state["active_custom_stock_symbol"] == ""

    app.radio[0].set_value("異常偵測展示")
    app.run(timeout=120)
    assert not app.exception
    assert [item.label for item in app.date_input] == ["開始日期", "結束日期"]
    assert len(app.get("plotly_chart")) == 3
    assert any("本機分析資料" in item.value for item in app.markdown)

    start_value = app.date_input[0].value
    end_value = app.date_input[1].value
    app.date_input[0].set_value(end_value)
    app.date_input[1].set_value(start_value)
    app.run(timeout=120)
    assert not app.exception
    assert app.date_input[0].value <= app.date_input[1].value


def test_dashboard_exposes_research_snapshot_downloads(monkeypatch) -> None:
    run_pipeline("sample")
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.run(timeout=120)

    labels = {item.label for item in app.get("download_button")}
    assert {"下載 JSON", "列印 HTML"} <= labels