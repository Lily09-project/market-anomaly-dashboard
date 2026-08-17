from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
import streamlit.testing.v1.app_test as app_test_module

from src import market_api


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def cleanup_streamlit_test_directory():
    yield
    app_test_module.TMP_DIR.cleanup()


def test_public_radar_route_renders_explainable_ranking(monkeypatch) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.query_params["page"] = "radar"
    app.run(timeout=120)

    assert not app.exception
    assert app.radio[0].value == "市場雷達"
    assert app.query_params["page"] == ["radar"]
    assert {item.label for item in app.selectbox} >= {"產業篩選", "研究配置", "候選池規模"}
    assert {item.label for item in app.slider} >= {"最低證據分數"}
    assert any("研究優先序" in item.value for item in app.markdown)
    assert any("查看個股分析" in item.value and "?page=stocks&amp;symbol=" in item.value for item in app.markdown)
    assert any("評分方法" in item.label for item in app.expander)
    assert any("DEMO" in item.value for item in app.warning)
    assert len(app.dataframe) == 1
    assert len(app.dataframe[0].value) > 0
    assert {"排序", "股票", "總分", "趨勢", "動能", "量能", "波動韌性", "資料來源"} <= set(
        app.dataframe[0].value.columns
    )

def test_radar_query_parameters_restore_and_update_filters(monkeypatch) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.query_params.update(
        {
            "page": "radar",
            "industry": "ETF",
            "profile": "defensive",
            "min_score": "65",
            "pool_size": "6",
        }
    )
    app.run(timeout=120)

    controls = {item.label: item for item in app.selectbox}
    assert controls["產業篩選"].value == "ETF"
    assert controls["研究配置"].value == "defensive"
    assert controls["候選池規模"].value == 6
    assert app.slider[0].value == 65

    controls["研究配置"].set_value("trend")
    app.slider[0].set_value(70)
    app.run(timeout=120)

    assert app.query_params["profile"] == ["trend"]
    assert app.query_params["min_score"] == ["70"]
    assert app.query_params["industry"] == ["ETF"]
    assert app.query_params["pool_size"] == ["6"]


def test_invalid_radar_query_parameters_fall_back_to_safe_defaults(monkeypatch) -> None:
    monkeypatch.setattr(market_api, "requests", None)
    monkeypatch.setattr(market_api, "yf", None)

    app = AppTest.from_file(PROJECT_ROOT / "app.py")
    app.query_params.update(
        {
            "page": "radar",
            "industry": "不存在的產業",
            "profile": "unknown",
            "min_score": "999",
            "pool_size": "999",
        }
    )
    app.run(timeout=120)

    controls = {item.label: item for item in app.selectbox}
    assert controls["產業篩選"].value == "全部"
    assert controls["研究配置"].value == "balanced"
    assert controls["候選池規模"].value == 10
    assert app.slider[0].value == 100
