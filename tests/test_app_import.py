from __future__ import annotations

import importlib
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
    assert "股票分析儀表板" in source
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
    assert "render_anomaly_page" in source
    assert "自訂股票代號" in source
    assert "套用代號" in source
    assert "active_custom_stock_symbol" in source
    assert "個股分析" in source
    assert "分析總覽" in source
    assert "股票健診" in source
    assert "近期表現" in source
    assert "異常偵測展示" in source
    assert "模型評估指標" not in source
    assert "開始日期" in source
    assert "結束日期" in source
    assert "本地端執行與測試指令" not in source
    assert "@media (max-width: 760px)" in source
    assert "@media (prefers-reduced-motion: reduce)" in source
    assert ":focus-visible" in source
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

    status, is_live = app.build_stock_source_status(
        "twse_openapi",
        [{"source": "yfinance"}],
    )
    assert status == "外部資料已連線：yfinance / TWSE"
    assert is_live is True
    fallback_status, fallback_live = app.build_stock_source_status(
        "unavailable",
        [{"source": "sample"}],
    )
    assert "sample data" in fallback_status
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
    assert "@media (prefers-reduced-motion: reduce)" in css


def test_streamlit_config_defines_both_native_themes() -> None:
    config_source = project_path(".streamlit/config.toml").read_text(encoding="utf-8")
    assert '[theme]' in config_source
    assert '[theme.dark]' in config_source
    assert '[theme.light]' in config_source
    assert '[theme.dark.sidebar]' in config_source
    assert '[theme.light.sidebar]' in config_source
    assert 'port = 8765' in config_source


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
