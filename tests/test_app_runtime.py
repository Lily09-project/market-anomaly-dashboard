from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
import streamlit.testing.v1.app_test as app_test_module

from run_all import run_pipeline
from src import market_api
from src.research_snapshot import snapshot_to_json_bytes
from tests.test_snapshot_compare import make_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def button_by_label(app: AppTest, label: str):
    return next(button for button in app.button if button.label == label)


@pytest.fixture(scope="module")
def sample_pipeline_outputs() -> None:
    run_pipeline("sample")


@pytest.fixture(autouse=True)
def cleanup_streamlit_test_directory():
    yield
    app_test_module.TMP_DIR.cleanup()


def test_dashboard_pages_and_sidebar_interactions(monkeypatch, sample_pipeline_outputs: None) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.run(timeout=120)
    assert not app.exception
    assert len(app.get("plotly_chart")) >= 3
    assert len(app.dataframe) >= 2
    assert {button.label for button in app.button} >= {"重新取得資料", "套用代號", "清除代號"}
    assert any("DEMO" in item.value for item in app.warning)
    assert any("研究摘要" in item.value for item in app.markdown)
    assert any("資料可信度" in item.value for item in app.markdown)
    assert any("DEMO 示範資料" in item.value for item in app.markdown)
    assert any("research-shell" in item.value for item in app.markdown)
    assert any("instrument-workspace" in item.value for item in app.markdown)
    assert any("evidence-grid" in item.value for item in app.markdown)

    button_by_label(app, "重新取得資料").click()
    app.run(timeout=120)
    assert not app.exception
    assert any("已重新連線資料來源" in item.value for item in app.success)

    app.text_input[0].set_value("<script>")
    button_by_label(app, "套用代號").click()
    app.run(timeout=120)
    assert not app.exception
    assert any("合法的 yfinance 英文代號" in warning.value for warning in app.warning)

    app.text_input[0].set_value("TSLA")
    button_by_label(app, "套用代號").click()
    app.run(timeout=120)
    assert not app.exception
    assert app.session_state["active_custom_stock_symbol"] == "TSLA"
    assert app.query_params["symbol"] == ["TSLA"]

    button_by_label(app, "清除代號").click()
    app.run(timeout=120)
    assert not app.exception
    assert app.session_state["active_custom_stock_symbol"] == ""

    app.radio[0].set_value("異常偵測展示")
    app.run(timeout=120)
    assert app.query_params["page"] == ["anomalies"]
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


def test_dashboard_exposes_research_snapshot_downloads(monkeypatch, sample_pipeline_outputs: None) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.query_params["symbol"] = "TSLA"
    app.run(timeout=120)

    assert app.session_state["stock_analysis_symbol"] == "TSLA"
    assert app.query_params["symbol"] == ["TSLA"]
    labels = {item.label for item in app.get("download_button")}
    assert {"下載 JSON", "列印 HTML"} <= labels

def test_public_page_route_opens_snapshot_comparison(monkeypatch) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.query_params["page"] = "compare"
    app.run(timeout=120)

    assert not app.exception
    assert app.radio[0].value == "快照比較"
    assert [item.label for item in app.file_uploader] == ["基準快照", "目前快照"]

def test_snapshot_comparison_page_renders_uploaders(monkeypatch) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.run(timeout=120)
    app.radio[0].set_value("\u5feb\u7167\u6bd4\u8f03")
    app.run(timeout=120)

    assert not app.exception
    assert [item.label for item in app.file_uploader] == [
        "\u57fa\u6e96\u5feb\u7167",
        "\u76ee\u524d\u5feb\u7167",
    ]
    assert any("2 MiB" in item.value for item in app.caption)

    baseline_payload = snapshot_to_json_bytes(
        make_snapshot(start_date="2026-01-01", evidence_state="neutral")
    )
    current_payload = snapshot_to_json_bytes(
        make_snapshot(start_date="2026-03-01", evidence_state="positive")
    )
    app.file_uploader[0].upload("baseline.json", baseline_payload, "application/json")
    app.file_uploader[1].upload("current.json", current_payload, "application/json")
    app.run(timeout=120)

    assert not app.exception
    assert any(item.value == "\u6bd4\u8f03\u6458\u8981" for item in app.header)
    assert len(app.dataframe) == 2
    labels = {item.label for item in app.get("download_button")}
    assert "\u4e0b\u8f09\u6bd4\u8f03 JSON" in labels
