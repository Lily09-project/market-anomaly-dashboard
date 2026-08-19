from __future__ import annotations

import importlib
import tomllib
from datetime import date

import pandas as pd

from src.app_helpers import safe_load_csv
from src.theme import DEFAULT_THEME_NAME, REQUIRED_THEME_KEYS, THEME_OPTIONS, contrast_ratio, validate_theme_contrast
from src.utils import project_path


def test_app_import_is_safe() -> None:
    app = importlib.import_module("app")
    assert hasattr(app, "main")
    assert hasattr(app, "inject_global_css")
    assert hasattr(app, "apply_plotly_theme")
    assert hasattr(app, "DISPLAY_COLUMN_MAP")


def test_safe_load_csv_missing_file_returns_empty_dataframe() -> None:
    df = safe_load_csv(project_path("__missing_for_safe_load_csv_test__.csv"))
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_dark_and_light_themes_are_complete_and_readable() -> None:
    assert DEFAULT_THEME_NAME == "charcoal_orange"
    assert DEFAULT_THEME_NAME in THEME_OPTIONS
    assert "paper_orange" in THEME_OPTIONS
    assert THEME_OPTIONS["charcoal_orange"]["mode"] == "dark"
    assert THEME_OPTIONS["paper_orange"]["mode"] == "light"
    assert THEME_OPTIONS["charcoal_orange"]["plotly_template"] == "plotly_dark"
    assert THEME_OPTIONS["paper_orange"]["plotly_template"] == "plotly_white"
    assert set(THEME_OPTIONS) == {"charcoal_orange", "paper_orange"}
    for theme in THEME_OPTIONS.values():
        assert REQUIRED_THEME_KEYS <= set(theme)
        result = validate_theme_contrast(theme)
        assert result["passed"], result
        assert contrast_ratio(theme["text"], theme["background"]) >= 4.5
        assert contrast_ratio(theme["text"], theme["card"]) >= 4.5
        assert contrast_ratio(theme["muted_text"], theme["background"]) >= 3.0
        assert contrast_ratio(theme["muted_text"], theme["card"]) >= 3.0
        assert contrast_ratio(theme["success"], theme["background"]) >= 3.0


def test_app_frontend_contracts() -> None:
    app = importlib.import_module("app")
    required_columns = {
        "date",
        "symbol",
        "close",
        "daily_return",
        "volatility_20",
        "risk_score_baseline",
        "anomaly_score",
    }
    assert required_columns <= set(app.DISPLAY_COLUMN_MAP)

    source = project_path("app.py").read_text(encoding="utf-8")
    assert "選擇深色主題" not in source
    assert "股票研究工作台" in source
    assert "股票分析代號" in source
    assert "產業篩選" in source
    assert "熱門股" in source
    assert "產業同類比較" in source
    assert "render_peer_comparison" in source
    assert "get_peer_comparison_symbols" in source
    assert "TECHNICAL_INDICATOR_OPTIONS" in source
    assert "技術指標" in source
    assert "布林通道" in source
    assert "MACD" in source
    assert "stock_display_pair" in source
    assert "lookup_stock_display_name" in source
    assert "resolve_dashboard_theme_name" in source
    assert 'st.context.theme.get("type")' in source
    assert "get_theme(fallback_name)" in source
    assert "render_stock_analysis_page" in source
    assert "render_market_radar_page" in source
    radar_source = project_path("src/market_radar_page.py").read_text(encoding="utf-8")
    assert "研究優先序" in radar_source
    assert "最低證據分數" in radar_source
    assert "render_anomaly_page" in source
    assert "自訂股票代號" in source
    assert "套用代號" in source
    assert "active_custom_stock_symbol" in source
    assert "個股分析" in source
    assert "研究摘要" in source
    assert "資料可信度" in source
    assert "證據矩陣" in source
    assert "證據一致性" in source
    assert "render_evidence_coherence" in source
    assert "本期變化" in source
    assert "同業脈絡" in source
    assert "render_research_brief" in source
    assert "render_research_workflow" in source
    assert source.index("render_research_workflow(workflow)") < source.index("render_research_brief(brief)")
    assert "build_research_workflow" in source
    assert "研究路徑" in source
    assert "build_research_brief" in source
    assert "近期表現" in source
    assert "異常偵測展示" in source
    assert "模型評估指標" not in source
    assert "技術評分" not in source
    assert "render_health_score" not in source
    assert "render_signal_cards" not in source
    assert "開始日期" in source
    assert "結束日期" in source
    assert "本地端執行與測試指令" not in source
    assert "@media (max-width: 760px)" in source
    assert "@media (max-width: 1024px)" in source
    assert "@media (prefers-reduced-motion: reduce)" in source
    assert ":focus-visible" in source
    assert "font-variant-numeric: tabular-nums" in source
    assert 'initial_sidebar_state="collapsed"' in source
    assert 'placeholder="例如 2881、TSLA、SPY"' in source
    assert 'width: min(86vw, 320px)' in source
    assert 'evidence_markup = "".join(item.strip() for item in evidence_items)' in source
    assert "filter_start_date" in source
    assert "filter_end_date" in source
    assert "card-spacer" in source
    assert ".dashboard-topline h1" in source
    assert "skip-link" in source
    assert 'id="main-content"' in source
    expand_selector = '[data-testid="stExpandSidebarButton"]'
    assert source.index(expand_selector) < source.index("@media (max-width: 760px)")
    assert "近期價格與成交量資料" in source
    assert "固定網址 http://localhost:8765" not in source
    assert 'paper_bgcolor=theme["card"]' in source
    assert 'family="Microsoft JhengHei UI, Microsoft JhengHei, Noto Sans TC, sans-serif"' in source
    assert 'color=theme["text"]' in source
    assert 'gridcolor=theme["chart_grid"]' in source
    assert "titlefont" not in source
    assert "--ui-radius: 6px" in source
    assert "touch-action: manipulation" in source
    assert "linear-gradient" not in source
    assert "transform: translateY(-1px)" not in source
    assert "市場代表標的，依最新可用資料更新。" in source
    assert "PAGE_ROUTES" in source
    assert 'st.query_params["page"]' in source
    assert 'st.query_params["symbol"]' in source
    assert ".st-key-active_page label > div:first-child" in source
    nav_grid_start = source.index('        .st-key-active_page [role="radiogroup"]')
    nav_grid_end = source.index('        .st-key-active_page label {{', nav_grid_start)
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in source[nav_grid_start:nav_grid_end]
    assert "render_data_service_notice" in source
    assert "render_product_footer" in source

    readme = project_path("README.md").read_text(encoding="utf-8")
    assert "可解釋研究工作台" in readme
    assert "可解釋市場雷達" in readme
    assert "src/market_screener.py" in readme
    assert "資料來源與降級" in readme
    assert "不提供買賣建議" in readme
    assert "研究工作流" in readme

    user_guide = project_path("docs/user-guide.md").read_text(encoding="utf-8")
    assert "`r`n" not in user_guide
    assert "docs/research-workflow.md" in readme
    assert "docs/user-guide.md" in readme
    assert "docs/deployment.md" in readme

    assert app.stock_display_pair("2330.TW", "台積電") == "2330.TW · 台積電"
    lookup = app.stock_symbol_lookup(app.get_stock_universe())
    assert app.anomaly_symbol_label("2330", lookup) == "2330.TW · 台積電"


def test_custom_symbol_validation_and_theme_resolution() -> None:
    app = importlib.import_module("app")
    assert app.resolve_custom_stock_symbol("2881") == "2881.TW"
    assert app.resolve_custom_stock_symbol("tsla") == "TSLA"
    assert app.resolve_custom_stock_symbol("^GSPC") == "^GSPC"
    assert app.resolve_custom_stock_symbol("<script>") is None
    assert app.resolve_custom_stock_symbol("AAPL;rm") is None

    cfg = {
        "dashboard": {
            "theme_name": "charcoal_orange",
            "dark_theme_name": "charcoal_orange",
            "light_theme_name": "paper_orange",
        }
    }
    assert app.resolve_dashboard_theme_name(cfg, "dark") == "charcoal_orange"
    assert app.resolve_dashboard_theme_name(cfg, "light") == "paper_orange"
    assert app.resolve_dashboard_theme_name(cfg, None) == "charcoal_orange"
    assert app.hex_to_rgba("#FDB338", 0.08) == "rgba(253, 179, 56, 0.080)"
    assert app.market_source_label("sample") == "DEMO"
    assert app.market_source_label("yfinance") == "LIVE"

    status, is_live = app.build_stock_source_status(
        "twse_openapi",
        [{"source": "yfinance"}],
    )
    assert status == "LIVE"
    assert is_live is True
    fallback_status, fallback_live = app.build_stock_source_status(
        "unavailable",
        [{"source": "sample"}],
    )
    assert fallback_status == "DEMO"
    assert fallback_live is False


def test_global_css_uses_selected_light_theme(monkeypatch) -> None:
    app = importlib.import_module("app")
    if app.st is None:
        return
    captured = {}

    def capture_markdown(body: str, **kwargs) -> None:
        captured["body"] = body
        captured["unsafe_allow_html"] = kwargs.get("unsafe_allow_html")

    monkeypatch.setattr(app.st, "markdown", capture_markdown)
    light_theme = THEME_OPTIONS["paper_orange"]
    app.inject_global_css(light_theme)
    css = captured["body"]
    assert captured["unsafe_allow_html"] is True
    assert light_theme["background"] in css
    assert light_theme["text"] in css
    assert f"color-scheme: {light_theme['mode']}" in css
    assert ".research-brief" in css
    assert ".research-evidence--positive" in css
    assert "--space-6" in css
    assert ".research-shell" in css
    assert ".data-rail" in css
    assert ".instrument-workspace" in css
    assert ".evidence-grid" in css
    assert ".research-path" in css
    assert ".research-path-grid" in css
    assert ".coherence-panel" in css
    assert ".coherence-grid" in css
    assert light_theme["success"] in css
    assert light_theme["danger"] in css
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_streamlit_config_defines_both_native_themes() -> None:
    config_source = project_path(".streamlit/config.toml").read_text(encoding="utf-8")
    config = tomllib.loads(config_source)
    assert '[theme]' in config_source
    assert '[theme.dark]' in config_source
    assert '[theme.light]' in config_source
    assert '[theme.dark.sidebar]' in config_source
    assert '[theme.light.sidebar]' in config_source
    assert 'port = 8765' in config_source
    assert config["server"]["maxUploadSize"] == 2


def test_date_clamp_handles_out_of_range_values() -> None:
    app = importlib.import_module("app")
    min_date = date(2024, 1, 1)
    max_date = date(2024, 12, 31)
    assert app.clamp_date_value(date(2023, 12, 31), min_date, max_date, min_date) == min_date
    assert app.clamp_date_value(date(2025, 1, 1), min_date, max_date, min_date) == max_date
    assert app.clamp_date_value(None, min_date, max_date, max_date) == max_date
    assert app.clamp_date_value((date(2024, 6, 1), date(2024, 7, 1)), min_date, max_date, min_date) == date(2024, 6, 1)


def test_plotly_theme_applies_without_invalid_axis_properties() -> None:
    app = importlib.import_module("app")
    if app.go is None:
        return
    for theme in THEME_OPTIONS.values():
        fig = app.go.Figure()
        fig.add_trace(app.go.Scatter(x=[1, 2], y=[3, 4]))
        app.apply_plotly_theme(fig, theme, "測試圖表")
        fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
        fig.update_yaxes(title_text="數值", title_font=dict(color=theme["text"]))
        assert fig.layout.xaxis.title.font.color == theme["text"]
        assert fig.layout.yaxis.title.font.color == theme["text"]
        assert fig.layout.paper_bgcolor == theme["card"]


def test_research_snapshot_public_contract() -> None:
    app_source = project_path("app.py").read_text(encoding="utf-8")
    assert "render_snapshot_actions" in app_source
    assert "st.download_button(" in app_source
    assert "下載 JSON" in app_source
    assert "列印 HTML" in app_source

    readme = project_path("README.md").read_text(encoding="utf-8")
    workflow = project_path("docs/research-workflow.md").read_text(encoding="utf-8")
    assert "Research Snapshot" in readme
    assert "snapshot_id" in readme
    assert "offline" in readme.lower()
    assert "raw OHLCV" in workflow
    assert "does not predict" in workflow


def test_snapshot_comparison_public_contract() -> None:
    source = project_path("app.py").read_text(encoding="utf-8")

    assert "\\u5feb\\u7167\\u6bd4\\u8f03" in source
    assert "render_snapshot_comparison_page" in source
    assert "\\u57fa\\u6e96\\u5feb\\u7167" in source
    assert "\\u76ee\\u524d\\u5feb\\u7167" in source

    readme = project_path("README.md").read_text(encoding="utf-8")
    workflow = project_path("docs/research-workflow.md").read_text(encoding="utf-8")
    assert "Snapshot Comparison" in readme
    assert "integrity verification" in workflow

def test_stock_page_exposes_research_readiness_panel() -> None:
    source = project_path("app.py").read_text(encoding="utf-8")

    assert "研究就緒度" in source
    assert "readiness-grid" in source
    assert "這不是股票評分" in source
