from __future__ import annotations

import html
from datetime import datetime, timezone
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

try:
    import plotly.graph_objects as go
except Exception:
    go = None

try:
    import streamlit as st
except Exception:
    st = None

from src.app_helpers import build_kpis, filter_by_symbol_and_date, get_available_symbols, load_dashboard_data
from src.market_api import (
    build_stock_analysis,
    build_market_cards,
    build_watchlist_cards,
    compute_technical_indicators,
    fetch_twse_company_profiles,
    fetch_twse_esg_legal_data,
    fetch_yfinance_histories,
    fetch_yfinance_history,
    format_number,
    get_stock_universe,
    lookup_twse_company,
    to_yfinance_symbol,
)
from src.market_radar_page import render_market_radar
from src.product_state import (
    PAGE_ROUTES,
    build_data_service_state,
    page_label_from_route,
    route_from_page_label,
)
from src.research_brief import build_research_brief
from src.research_workflow import build_research_workflow
from src.research_snapshot import build_research_snapshot, render_snapshot_html, snapshot_to_json_bytes
from src.snapshot_compare import (
    SnapshotValidationError,
    compare_snapshots,
    comparison_to_json_bytes,
    parse_snapshot_bytes,
)

from src.theme import get_theme, validate_theme_contrast
from src.utils import load_config


DISPLAY_COLUMN_MAP = {
    "date": "日期",
    "symbol": "股票",
    "open": "開盤價",
    "high": "最高價",
    "low": "最低價",
    "close": "收盤價",
    "volume": "成交量",
    "currency_pair": "匯率組合",
    "exchange_rate": "匯率",
    "daily_return": "日報酬率",
    "abs_return": "絕對報酬率",
    "volatility_20": "20 日波動率",
    "risk_score_baseline": "風險分數",
    "model_anomaly": "異常事件",
    "anomaly_score": "異常分數",
    "volume_zscore_20": "成交量 Z-score",
    "timestamp": "時間",
    "station_id": "站點編號",
    "station_name": "站點名稱",
    "district": "行政區",
    "total_capacity": "總車位",
    "available_bikes": "可借車輛",
    "available_spaces": "可還空位",
    "status": "站點狀態",
    "occupancy_rate": "使用率",
    "target_next_available_bikes": "下一時間點可借車輛",
    "predicted_available_bikes": "預測可借車輛",
    "anomaly": "異常事件",
    "quality_flag": "資料品質標記",
}

TECHNICAL_INDICATOR_OPTIONS = ["MA5", "MA20", "MA60", "布林通道", "成交量", "RSI", "MACD"]
DEFAULT_TECHNICAL_INDICATORS = ["MA5", "MA20", "MA60", "成交量", "RSI"]
CUSTOM_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9^][A-Za-z0-9.^=_-]{0,19}$")
PLOTLY_CONFIG = {"displaylogo": False, "responsive": True, "scrollZoom": False}

RESEARCH_STATE_LABELS = {
    "ready": "資料可用",
    "caution": "保守解讀",
    "unavailable": "資料不足",
    "positive": "支持",
    "neutral": "中性",
    "risk": "注意",
}


def _load_twse_sources() -> tuple[pd.DataFrame, str, pd.DataFrame, str]:
    with ThreadPoolExecutor(max_workers=2) as executor:
        company_future = executor.submit(fetch_twse_company_profiles)
        esg_future = executor.submit(fetch_twse_esg_legal_data)
        company_profiles, company_source = company_future.result()
        esg_data, esg_source = esg_future.result()
    return company_profiles, company_source, esg_data, esg_source


if st is not None and st.runtime.exists():

    @st.cache_data(ttl=3600, show_spinner=False)
    def cached_load_twse_sources() -> tuple[pd.DataFrame, str, pd.DataFrame, str]:
        return _load_twse_sources()


    @st.cache_data(ttl=900, show_spinner=False)
    def cached_market_cards() -> list[dict]:
        return build_market_cards()


    @st.cache_data(ttl=900, show_spinner=False)
    def cached_watchlist_cards(symbols: tuple[str, ...] | None = None) -> list[dict]:
        return build_watchlist_cards(list(symbols) if symbols is not None else None)


    @st.cache_data(ttl=900, show_spinner=False)
    def cached_stock_history(symbol: str, period: str = "1y") -> tuple[pd.DataFrame, str]:
        return fetch_yfinance_history(symbol, period=period)

    @st.cache_data(ttl=900, show_spinner=False)
    def cached_radar_histories(symbols: tuple[str, ...]) -> dict[str, tuple[pd.DataFrame, str]]:
        return fetch_yfinance_histories(list(symbols), period="1y")

else:
    cached_load_twse_sources = _load_twse_sources
    cached_market_cards = build_market_cards

    def cached_watchlist_cards(symbols: tuple[str, ...] | None = None) -> list[dict]:
        return build_watchlist_cards(list(symbols) if symbols is not None else None)

    def cached_stock_history(symbol: str, period: str = "1y") -> tuple[pd.DataFrame, str]:
        return fetch_yfinance_history(symbol, period=period)


    def cached_radar_histories(symbols: tuple[str, ...]) -> dict[str, tuple[pd.DataFrame, str]]:
        return fetch_yfinance_histories(list(symbols), period="1y")

def require_streamlit() -> bool:
    if st is None:
        print("目前找不到 Streamlit，請先執行 pip install -r requirements.txt")
        return False
    if go is None:
        st.error("目前找不到 Plotly，請先執行 pip install -r requirements.txt")
        return False
    return True


def clamp_date_value(value, min_date, max_date, fallback):
    if isinstance(value, (tuple, list)):
        value = value[0] if value else fallback
    if value is None:
        return fallback
    if value < min_date:
        return min_date
    if value > max_date:
        return max_date
    return value


def prepare_date_inputs(min_date, max_date) -> None:
    start_key = "filter_start_date"
    end_key = "filter_end_date"
    st.session_state[start_key] = clamp_date_value(st.session_state.get(start_key), min_date, max_date, min_date)
    st.session_state[end_key] = clamp_date_value(st.session_state.get(end_key), min_date, max_date, max_date)
    if st.session_state[start_key] > st.session_state[end_key]:
        st.session_state[start_key], st.session_state[end_key] = st.session_state[end_key], st.session_state[start_key]


def stock_display_pair(symbol: str, display: str | None = None) -> str:
    clean_symbol = str(symbol).strip()
    clean_display = str(display or "").strip()
    if not clean_display or clean_display == clean_symbol:
        clean_display = "自訂標的"
    return f"{clean_symbol} · {clean_display}"


def escape_html(value: object) -> str:
    return html.escape(str(value), quote=True)


def hex_to_rgba(hex_color: str, alpha: float) -> str:
    clean = hex_color.strip().lstrip("#")
    red, green, blue = (int(clean[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {max(0.0, min(1.0, alpha)):.3f})"


def lookup_stock_display_name(symbol: str, governance_df: pd.DataFrame | None = None) -> str:
    if governance_df is not None:
        company = lookup_twse_company(symbol, governance_df)
        if company.get("twse_name"):
            return str(company["twse_name"])
    lookup = stock_symbol_lookup(get_stock_universe())
    item = lookup.get(str(symbol)) or lookup.get(to_yfinance_symbol(str(symbol)))
    if item:
        return item["display"]
    return "自訂標的"


def stock_option_label(item: dict[str, str]) -> str:
    category = item.get("category", "")
    suffix = f" · {category}" if category else ""
    return f'{stock_display_pair(item["symbol"], item["display"])}{suffix}'


def stock_symbol_lookup(stock_universe: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    lookup = {}
    for item in stock_universe:
        lookup[item["symbol"]] = item
        lookup[item["symbol"].replace(".TW", "")] = item
        if item["symbol"].startswith("00"):
            lookup[item["symbol"].replace(".TW", "").lstrip("0")] = item
    return lookup


def anomaly_symbol_label(symbol: str, lookup: dict[str, dict[str, str]]) -> str:
    raw = str(symbol)
    item = lookup.get(raw) or lookup.get(to_yfinance_symbol(raw))
    if item:
        return stock_display_pair(item["symbol"], item["display"])
    return stock_display_pair(raw, "自訂標的")


def resolve_custom_stock_symbol(raw_symbol: str) -> str | None:
    clean_symbol = raw_symbol.strip()
    if not clean_symbol or not CUSTOM_SYMBOL_PATTERN.fullmatch(clean_symbol):
        return None
    return to_yfinance_symbol(clean_symbol)


def resolve_dashboard_theme_name(cfg: dict, context_theme_type: str | None = None) -> str:
    dashboard_cfg = cfg.get("dashboard", {})
    if context_theme_type == "light":
        return dashboard_cfg.get("light_theme_name", "paper_orange")
    if context_theme_type == "dark":
        return dashboard_cfg.get("dark_theme_name", "charcoal_orange")
    return dashboard_cfg.get("theme_name", "charcoal_orange")


def build_stock_source_status(company_source: str, cards: list[dict]) -> tuple[str, bool]:
    state = build_data_service_state(company_source, cards)
    as_of_text = f' · 資料截至 {state["as_of_date"]}' if state["as_of_date"] else ""
    return f'{state["label"]}{as_of_text}', bool(state["is_live"])
def get_industry_options(stock_universe: list[dict[str, str]]) -> list[str]:
    categories = sorted({item.get("category", "").strip() for item in stock_universe if item.get("category", "").strip()})
    return ["全部"] + categories


def filter_stock_universe(stock_universe: list[dict[str, str]], industry: str) -> list[dict[str, str]]:
    if industry == "全部":
        return stock_universe
    filtered = [item for item in stock_universe if item.get("category") == industry]
    return filtered or stock_universe


def get_popular_symbols(stock_universe: list[dict[str, str]], industry: str, limit: int = 6) -> list[str] | None:
    if industry == "全部":
        return None
    filtered = filter_stock_universe(stock_universe, industry)
    return [item["symbol"] for item in filtered[:limit]]


def get_peer_comparison_symbols(
    stock_universe: list[dict[str, str]],
    selected_symbol: str,
    selected_industry: str,
    limit: int = 8,
) -> tuple[list[str], str]:
    lookup = stock_symbol_lookup(stock_universe)
    selected_yf_symbol = to_yfinance_symbol(selected_symbol)
    selected_item = lookup.get(selected_yf_symbol) or lookup.get(str(selected_symbol))
    peer_industry = selected_industry
    if peer_industry == "全部" and selected_item:
        peer_industry = selected_item.get("category", "全部")
    pool = filter_stock_universe(stock_universe, peer_industry)
    pool_symbols = [item["symbol"] for item in pool]
    ordered = []
    if selected_yf_symbol:
        ordered.append(selected_yf_symbol)
    ordered.extend(symbol for symbol in pool_symbols if symbol != selected_yf_symbol)
    seen = set()
    unique = []
    for symbol in ordered:
        if symbol in seen:
            continue
        seen.add(symbol)
        unique.append(symbol)
    return unique[:limit], peer_industry


def format_peer_range_position(card: dict) -> str:
    high = float(card.get("high_52w", 0) or 0)
    low = float(card.get("low_52w", 0) or 0)
    latest = float(card.get("latest_close", 0) or 0)
    if high <= low:
        return "50%"
    position = max(0, min(100, (latest - low) / (high - low) * 100))
    return f"{position:.0f}%"


def render_peer_comparison(cards: list[dict], selected_symbol: str, industry: str, theme: dict) -> None:
    st.header("產業同類比較")
    if not cards:
        st.info("目前沒有足夠的同類股票資料可比較。")
        return
    st.caption(f"比較範圍：{industry}。表格用來快速比較同類股票的當日變化、量能與 52 週位置。")
    selected_yf_symbol = to_yfinance_symbol(selected_symbol)
    rows = []
    for card in cards:
        avg_volume = float(card.get("avg_volume", 0) or 0)
        volume = float(card.get("volume", 0) or 0)
        volume_ratio = volume / avg_volume if avg_volume else 0.0
        rows.append(
            {
                "狀態": "目前選股" if card["symbol"] == selected_yf_symbol else "",
                "股票": stock_display_pair(card["symbol"], card["display"]),
                "類別": card.get("category", ""),
                "最新價": f'{card["latest_close"]:,.2f} {card["currency"]}',
                "漲跌": f'{card["change_pct"]:+.2f}%',
                "量能倍率": f"{volume_ratio:.2f}x",
                "52 週位置": format_peer_range_position(card),
                "資料源": card.get("source", ""),
            }
        )
    table = pd.DataFrame(rows)
    st.dataframe(table, width="stretch", hide_index=True)


def inject_global_css(theme: dict) -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            color-scheme: {theme["mode"]};
            --ui-background: {theme["background"]};
            --ui-surface: {theme["surface"]};
            --ui-card: {theme["card"]};
            --ui-text: {theme["text"]};
            --ui-muted: {theme["muted_text"]};
            --ui-border: {theme["border"]};
            --ui-accent: {theme["accent"]};
            --ui-space-1: 0.25rem;
            --ui-space-2: 0.5rem;
            --ui-space-3: 0.75rem;
            --ui-space-4: 1rem;
            --ui-space-6: 1.5rem;
            --ui-space-8: 2rem;
            --space-1: 0.25rem;
            --space-2: 0.5rem;
            --space-3: 0.75rem;
            --space-4: 1rem;
            --space-6: 2rem;
            --space-8: 3rem;
            --ui-raised: color-mix(in srgb, {theme["card"]} 92%, {theme["text"]});
            --ui-accent-muted: color-mix(in srgb, {theme["accent"]} 14%, transparent);
            --ui-data-font: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
            --ui-radius: 6px;
        }}

        html,
        body,
        [data-testid="stAppViewContainer"],
        [data-testid="stAppViewBlockContainer"] {{
            background: {theme["background"]} !important;
            color: {theme["text"]} !important;
            font-family: "Noto Sans TC", "Microsoft JhengHei UI", "Microsoft JhengHei", system-ui, sans-serif;
            letter-spacing: 0;
            max-width: 100%;
            overflow-x: hidden;
        }}

        html {{
            touch-action: manipulation;
        }}

        header[data-testid="stHeader"] {{
            background: transparent !important;
            border-bottom: 0 !important;
            box-shadow: none !important;
            height: 0 !important;
            min-height: 0 !important;
            pointer-events: none !important;
        }}

        [data-testid="stSidebarCollapsedControl"] {{
            pointer-events: auto !important;
            position: relative;
            z-index: 100;
        }}

        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {{
            display: none !important;
            visibility: hidden !important;
            height: 0 !important;
            min-height: 0 !important;
            pointer-events: none !important;
        }}

        [data-testid="stToolbar"] {{
            display: flex !important;
            visibility: visible !important;
            height: 0 !important;
            min-height: 0 !important;
            pointer-events: none !important;
        }}

        [data-testid="stToolbar"] [data-testid="stBaseButton-header"],
        [data-testid="stToolbar"] [data-testid="stMainMenuButton"] {{
            display: none !important;
            visibility: hidden !important;
        }}

        .stApp {{
            background: {theme["background"]};
            color: {theme["text"]};
        }}

        .block-container {{
            max-width: 1480px;
            padding-top: 3.75rem;
            padding-bottom: 3rem;
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: {theme["text"]} !important;
            font-weight: 720 !important;
            letter-spacing: 0 !important;
            scroll-margin-top: 1rem;
        }}

        .skip-link {{
            position: fixed;
            top: 0.75rem;
            left: 0.75rem;
            z-index: 1000;
            transform: translateY(-180%);
            padding: 0.65rem 0.85rem;
            border-radius: 8px;
            background: {theme["accent"]};
            color: {theme["background"]} !important;
            font-weight: 800;
            transition: transform 160ms ease;
        }}

        .skip-link:focus-visible {{
            transform: translateY(0);
        }}

        h1 {{
            font-size: 2.25rem !important;
            line-height: 1.08 !important;
            overflow-wrap: anywhere;
            text-wrap: balance;
        }}

        h2 {{
            font-size: 1.5rem !important;
            line-height: 1.2 !important;
            margin-top: 1.8rem !important;
            margin-bottom: 0.75rem !important;
            text-wrap: balance;
        }}

        h3 {{
            font-size: 1.25rem !important;
            line-height: 1.25 !important;
            text-wrap: balance;
        }}

        p, li, div[data-testid="stMarkdownContainer"] {{
            color: {theme["text"]};
            font-size: 1.02rem;
            line-height: 1.6;
        }}

        div[data-testid="stCaptionContainer"], .stCaption, small {{
            color: {theme["muted_text"]} !important;
            opacity: 1 !important;
            font-size: 0.94rem !important;
            line-height: 1.55 !important;
        }}

        [data-testid="stSidebar"] {{
            background-color: {theme["sidebar"]};
            border-right: 1px solid {theme["border"]};
        }}

        [data-testid="stSidebar"] > div:first-child {{
            padding-top: 1.25rem;
            padding-bottom: 1.5rem;
        }}

        [data-testid="stSidebar"] h2 {{
            font-size: 1.15rem !important;
            line-height: 1.3 !important;
            margin-top: 1.1rem !important;
            margin-bottom: 0.75rem !important;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {{
            gap: 0.4rem;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] label {{
            min-height: 44px;
            padding: 0.45rem 0.65rem;
            border: 1px solid transparent;
            border-radius: 8px;
            background: transparent;
            transition: background-color 180ms ease, border-color 180ms ease;
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {{
            background: {theme["surface"]};
            border-color: {theme["border"]};
        }}

        [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {{
            background: color-mix(in srgb, {theme["accent"]} 12%, {theme["surface"]});
            border-color: {theme["accent"]};
        }}

        [data-testid="stSidebar"] * {{
            color: {theme["text"]} !important;
        }}

        [data-testid="stSidebar"] label {{
            font-weight: 850 !important;
            color: {theme["text"]} !important;
            font-size: 0.98rem !important;
        }}

        [data-testid="stMetric"] {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-left: 5px solid {theme["accent"]};
            border-radius: 8px;
            min-height: 116px;
            padding: 18px;
            box-shadow: {theme["shadow"]};
        }}

        [data-testid="stMetric"] * {{
            opacity: 1 !important;
        }}

        [data-testid="stMetricValue"] {{
            color: {theme["accent"]} !important;
            font-weight: 900 !important;
            letter-spacing: 0 !important;
            font-size: 2rem !important;
        }}

        [data-testid="stMetricLabel"] {{
            color: {theme["muted_text"]} !important;
            font-weight: 800 !important;
            font-size: 0.94rem !important;
        }}

        [data-testid="stMetricDelta"] {{
            color: {theme["accent"]} !important;
        }}

        .kpi-card {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: 8px;
            padding: 18px;
            box-shadow: {theme["soft_shadow"]};
            color: {theme["text"]};
        }}

        .research-brief {{
            border-top: 2px solid {theme["accent"]};
            margin: 1.75rem 0 1.25rem;
            padding: 1rem 0 0.25rem;
        }}

        .research-brief-heading,
        .research-quality {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
        }}

        .research-brief-heading h3 {{
            margin: 0 !important;
        }}

        .section-eyebrow {{
            color: {theme["accent"]};
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.08em;
            margin-bottom: 0.3rem;
        }}

        .research-status {{
            border-left: 3px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.92rem;
            font-weight: 850;
            padding-left: 0.55rem;
        }}

        .research-status--ready {{
            border-left-color: {theme["success"]};
            color: {theme["success"]};
        }}

        .research-status--caution {{
            border-left-color: {theme["warning"]};
            color: {theme["warning"]};
        }}

        .research-quality {{
            border-bottom: 1px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.95rem;
            line-height: 1.5;
            margin-top: 0.8rem;
            padding: 0 0 0.8rem;
        }}

        .research-quality strong {{
            color: {theme["text"]};
        }}

        .research-warnings {{
            color: {theme["muted_text"]};
            font-size: 0.94rem;
            line-height: 1.5;
            margin: 0.75rem 0 0;
            padding-left: 1.15rem;
        }}

        .research-evidence {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            min-height: 188px;
            padding: 1rem;
        }}

        .research-evidence--positive {{ border-top: 3px solid {theme["success"]}; }}
        .research-evidence--neutral {{ border-top: 3px solid {theme["secondary"]}; }}
        .research-evidence--risk {{ border-top: 3px solid {theme["danger"]}; }}
        .research-evidence--unavailable {{ border-top: 3px solid {theme["border"]}; }}

        .research-evidence-headline {{
            color: {theme["text"]};
            font-size: 1.12rem;
            font-weight: 850;
            line-height: 1.35;
            margin: 0.5rem 0;
        }}

        .research-evidence-metrics {{
            color: {theme["muted_text"]};
            font-size: 0.92rem;
            line-height: 1.45;
            margin-top: 0.85rem;
        }}
        .dashboard-topline {{
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: center;
            margin-bottom: 1.5rem;
            padding-bottom: 1.25rem;
            border-bottom: 1px solid {theme["border"]};
        }}

        .page-header-copy {{
            min-width: 0;
            flex: 1 1 auto;
        }}

        .page-date {{
            margin-top: 0.45rem;
        }}

        .dashboard-topline h1 {{
            margin: 0 0 0.3rem 0 !important;
        }}

        .status-group {{
            display: flex;
            gap: 0.6rem;
            flex-wrap: wrap;
            justify-content: flex-end;
            align-items: center;
        }}

        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            padding: 0.35rem 0.65rem;
            border-radius: 4px;
            border: 0;
            border-left: 2px solid {theme["border"]};
            background: transparent;
            color: {theme["muted_text"]};
            font-size: 0.9rem;
            font-weight: 650;
            min-height: 32px;
            line-height: 1.35;
            white-space: normal;
        }}

        .status-pill::before {{
            content: "";
            width: 0.5rem;
            height: 0.5rem;
            flex: 0 0 0.5rem;
            border-radius: 999px;
            background: {theme["muted_text"]};
        }}

        .status-pill.live {{
            color: {theme["success"]};
            border-left-color: {theme["success"]};
            background: transparent;
        }}

        .status-pill.live::before {{
            background: {theme["success"]};
            box-shadow: 0 0 0 3px color-mix(in srgb, {theme["success"]} 18%, transparent);
        }}

        .market-card, .watch-card, .info-card {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            padding: 18px 20px;
            box-shadow: none;
            min-height: 128px;
            transition: border-color 180ms ease, background-color 180ms ease;
        }}

        .market-card, .watch-card {{
            position: relative;
            overflow: hidden;
        }}

        .market-card::before, .watch-card::before {{
            content: "";
            position: absolute;
            inset: 0 0 auto 0;
            height: 1px;
            background: {theme["accent"]};
            opacity: 0.7;
        }}

        .market-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1rem;
        }}

        .market-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.75rem;
            margin-bottom: 0.75rem;
        }}

        .market-card-copy {{
            min-width: 0;
        }}

        .card-spacer {{
            display: block;
            padding-bottom: 1rem;
        }}

        .market-card:hover, .watch-card:hover, .info-card:hover {{
            border-color: {theme["primary"]};
            background: color-mix(in srgb, {theme["primary"]} 4%, {theme["card"]});
        }}

        .watch-card {{
            min-height: 270px;
            padding: 20px 22px;
            display: flex;
            flex-direction: column;
        }}

        .watch-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.8rem;
        }}

        .watch-card-copy {{
            min-width: 0;
        }}

        .market-card .price-text, .watch-card .price-text {{
            margin-top: auto;
        }}

        .currency-label {{
            color: {theme["muted_text"]};
            font-size: 0.9rem;
            font-weight: 800;
        }}

        .metric-value-lg {{
            font-size: 1.3rem;
        }}

        .card-title {{
            color: {theme["text"]};
            font-size: 1.1rem;
            line-height: 1.28;
            font-weight: 850;
            margin-bottom: 0.3rem;
            max-width: 100%;
            white-space: normal;
            overflow-wrap: anywhere;
        }}

        .detail-title {{
            font-size: 2rem;
            line-height: 1.15;
            margin-bottom: 0.35rem;
        }}

        .card-subtitle {{
            color: {theme["muted_text"]};
            font-size: 0.96rem;
            line-height: 1.45;
            margin-bottom: 0.85rem;
        }}

        .price-text {{
            font-size: 1.98rem;
            line-height: 1.1;
            font-weight: 900;
            color: {theme["text"]};
        }}

        .positive {{
            color: {theme["success"]} !important;
            font-weight: 850;
        }}

        .negative {{
            color: {theme["danger"]} !important;
            font-weight: 850;
        }}

        .neutral {{
            color: {theme["muted_text"]} !important;
            font-weight: 750;
        }}

        .tag {{
            display: inline-flex;
            align-items: center;
            padding: 0.22rem 0.55rem;
            border-radius: 4px;
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.86rem;
            font-weight: 700;
            flex-shrink: 0;
            white-space: nowrap;
        }}

        .market-symbol-tag {{
            min-width: auto;
            height: auto;
            border-radius: 8px;
            padding: 0.22rem 0.48rem;
            background: color-mix(in srgb, {theme["primary"]} 14%, {theme["surface"]});
            border-color: {theme["border"]};
            font-size: 0.8rem;
        }}

        .metric-row {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            column-gap: 2.25rem;
            row-gap: 0.95rem;
            border-top: 1px solid {theme["border"]};
            padding-top: 1rem;
            margin-top: 1.15rem;
        }}

        .metric-label {{
            color: {theme["muted_text"]};
            font-size: 0.92rem;
            line-height: 1.35;
        }}

        .metric-value {{
            color: {theme["text"]};
            font-size: 1.08rem;
            font-weight: 800;
            margin-top: 0.15rem;
        }}

        .metric-row > div:nth-child(2n) {{
            padding-left: 0.7rem;
            border-left: 1px solid {theme["border"]};
        }}

        .health-bar {{
            height: 7px;
            width: 100%;
            border-radius: 999px;
            background: {theme["surface"]};
            overflow: hidden;
            border: 1px solid {theme["border"]};
        }}

        .health-fill {{
            height: 100%;
            border-radius: 2px;
            background: {theme["success"]};
        }}

        .signal-card {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            padding: 16px;
            min-height: 132px;
            box-shadow: none;
        }}

        .signal-card strong {{
            display: block;
            color: {theme["text"]};
            font-size: 1.2rem;
            line-height: 1.25;
            margin-top: 0.35rem;
            margin-bottom: 0.35rem;
        }}

        .score-wrap {{
            display: grid;
            grid-template-columns: minmax(220px, 0.72fr) 1fr;
            gap: 1rem;
            align-items: stretch;
        }}

        .score-panel {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            padding: 18px;
            min-height: 280px;
        }}

        .score-number {{
            font-size: 3rem;
            line-height: 1;
            color: {theme["success"]};
            font-weight: 900;
            letter-spacing: 0 !important;
        }}

        .score-line {{
            display: grid;
            grid-template-columns: 72px 1fr 44px;
            gap: 0.75rem;
            align-items: center;
            margin: 0.8rem 0;
        }}

        .range-track {{
            position: relative;
            height: 10px;
            border-radius: 2px;
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            margin: 1rem 0 0.55rem;
        }}

        .range-marker {{
            position: absolute;
            top: 50%;
            width: 18px;
            height: 18px;
            border-radius: 999px;
            background: {theme["text"]};
            border: 3px solid {theme["background"]};
            transform: translate(-50%, -50%);
            box-shadow: 0 0 0 2px {theme["accent"]};
        }}

        .range-labels {{
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            color: {theme["muted_text"]};
            font-size: 0.9rem;
        }}

        .stock-section-title {{
            margin-top: 1.6rem;
            margin-bottom: 0.6rem;
            color: {theme["text"]};
            font-size: 1.25rem;
            font-weight: 720;
            display: flex;
            align-items: center;
            gap: 0.6rem;
        }}

        .stock-section-title::before {{
            content: "";
            width: 2px;
            height: 1.2em;
            border-radius: 0;
            background: {theme["accent"]};
            flex: 0 0 2px;
        }}

        .section-card {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            padding: 18px;
            margin-bottom: 18px;
            box-shadow: none;
            color: {theme["text"]};
        }}

        .detail-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1.25rem;
        }}

        .detail-header-copy {{
            min-width: 0;
        }}

        .detail-tag-group {{
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
            justify-content: flex-end;
        }}

        .help-text {{
            color: {theme["muted_text"]} !important;
            font-size: 1rem;
            line-height: 1.65;
        }}

        .warning-text {{
            color: {theme["warning"]} !important;
            font-weight: 800;
        }}

        .danger-text {{
            color: {theme["danger"]} !important;
            font-weight: 800;
        }}

        .success-text {{
            color: {theme["success"]} !important;
            font-weight: 800;
        }}

        .notice, .info-box {{
            background: color-mix(in srgb, {theme["accent"]} 5%, transparent);
            border: 1px solid {theme["border"]};
            border-left: 3px solid {theme["accent"]};
            color: {theme["text"]};
            padding: 10px 12px;
            border-radius: 4px;
            margin: 8px 0 18px 0;
            font-size: 0.98rem;
            line-height: 1.6;
        }}

        .warning-box {{
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-left: 3px solid {theme["danger"]};
            color: {theme["text"]};
            padding: 12px 14px;
            border-radius: 4px;
            font-size: 0.98rem;
            line-height: 1.6;
        }}

        .stAlert {{
            background-color: {theme["surface"]} !important;
            color: {theme["text"]} !important;
            border: 1px solid {theme["border"]} !important;
        }}

        .stPlotlyChart {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            padding: 0;
            margin: 0.75rem 0 1.25rem;
            box-shadow: none;
        }}

        div[data-testid="stDataFrame"] {{
            background-color: {theme["card"]} !important;
            color: {theme["text"]} !important;
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            overflow: hidden;
            font-size: 1.03rem !important;
            line-height: 1.55 !important;
        }}

        div[data-testid="stDataFrame"] [role="columnheader"],
        div[data-testid="stDataFrame"] [role="gridcell"],
        div[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"] * {{
            color: {theme["text"]} !important;
            font-size: 1.03rem !important;
            line-height: 1.55 !important;
        }}

        div[data-testid="stDataFrame"] [role="columnheader"] {{
            background: {theme["table_header"]} !important;
            font-weight: 850 !important;
        }}

        div[data-testid="stForm"] {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            padding: 16px 14px 14px;
            margin-top: 0.75rem;
            margin-bottom: 1rem;
        }}

        div[data-testid="stForm"] label,
        div[data-testid="stForm"] [data-testid="stWidgetLabel"] {{
            display: flex !important;
            align-items: center !important;
            gap: 0.35rem !important;
            min-height: 1.7rem !important;
            white-space: normal !important;
            line-height: 1.35 !important;
            margin-bottom: 0.35rem !important;
            overflow: visible !important;
        }}

        div[data-testid="stForm"] div[data-baseweb="input"] {{
            margin-bottom: 0.95rem;
            min-height: 48px !important;
        }}

        div[data-testid="stForm"] div[data-baseweb="input"] > div {{
            min-height: 48px !important;
            display: flex !important;
            align-items: center !important;
        }}

        div[data-testid="stForm"] div[data-baseweb="input"] input {{
            min-height: 48px !important;
            line-height: 1.35 !important;
            padding: 0.7rem 0.8rem !important;
            box-sizing: border-box !important;
            color: {theme["text"]} !important;
            caret-color: {theme["accent"]} !important;
            font-size: 1rem !important;
        }}

        div[data-testid="stForm"] div[data-baseweb="input"] input::placeholder {{
            color: {theme["muted_text"]} !important;
            opacity: 0.85 !important;
        }}

        div[data-testid="stForm"] button {{
            width: 100%;
            margin-top: 0.25rem;
            justify-content: center;
        }}

        div[data-testid="stForm"] [data-testid="column"] {{
            min-width: 0;
        }}

        button {{
            border-radius: 6px !important;
            min-height: 44px !important;
            cursor: pointer !important;
            touch-action: manipulation;
            transition: border-color 180ms ease, background-color 180ms ease, color 180ms ease, box-shadow 180ms ease !important;
        }}

        button[kind="secondary"],
        button[data-testid="stBaseButton-secondary"] {{
            background: {theme["surface"]} !important;
            border: 1px solid {theme["border"]} !important;
            color: {theme["text"]} !important;
            font-weight: 800 !important;
        }}

        button[kind="secondary"]:hover,
        button[data-testid="stBaseButton-secondary"]:hover {{
            border-color: {theme["accent"]} !important;
            color: {theme["accent"]} !important;
            box-shadow: {theme["soft_shadow"]} !important;
        }}

        button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {{
            background: {theme["accent"]} !important;
            border: 1px solid {theme["accent"]} !important;
            color: {theme["background"]} !important;
            font-weight: 850 !important;
        }}

        button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {{
            background: {theme["warning"]} !important;
            border-color: {theme["warning"]} !important;
            box-shadow: {theme["soft_shadow"]} !important;
        }}

        button:focus-visible,
        a:focus-visible,
        input:focus-visible,
        textarea:focus-visible,
        select:focus-visible,
        [tabindex]:focus-visible {{
            outline: 3px solid {theme["accent"]} !important;
            outline-offset: 2px !important;
        }}

        button:active {{
            transform: translateY(1px);
        }}

        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        div[data-baseweb="textarea"] > div {{
            min-height: 44px;
            background-color: {theme["surface"]} !important;
            border-color: {theme["border"]} !important;
            color: {theme["text"]} !important;
            font-size: 1rem !important;
        }}

        div[data-baseweb="select"] > div:hover,
        div[data-baseweb="input"] > div:hover {{
            border-color: {theme["primary"]} !important;
        }}

        div[data-baseweb="popover"],
        div[role="listbox"],
        ul[role="listbox"] {{
            background: {theme["background"]} !important;
            border: 1px solid {theme["border"]} !important;
            border-radius: 8px !important;
            box-shadow: {theme["hover_shadow"]} !important;
        }}

        div[data-baseweb="calendar"],
        div[data-baseweb="calendar"] > div {{
            background: {theme["background"]} !important;
            color: {theme["text"]} !important;
        }}

        li[role="option"],
        div[role="option"] {{
            min-height: 44px !important;
            background: {theme["background"]} !important;
            color: {theme["text"]} !important;
            font-weight: 700 !important;
            font-size: 0.96rem !important;
        }}

        li[role="option"]:hover,
        div[role="option"]:hover,
        li[aria-selected="true"],
        div[aria-selected="true"] {{
            background: {theme["surface"]} !important;
            color: {theme["accent"]} !important;
        }}

        a {{
            color: {theme["primary"]} !important;
        }}

        pre, code {{
            background: {theme["surface"]} !important;
            color: {theme["text"]} !important;
            border: 1px solid {theme["border"]};
            border-radius: 6px !important;
        }}

        /* Keep the sidebar entry point reachable when Streamlit restores a collapsed sidebar. */
        [data-testid="stExpandSidebarButton"] {{
            display: flex !important;
            visibility: visible !important;
            position: fixed !important;
            top: 0.75rem !important;
            left: 0.75rem !important;
            z-index: 1000 !important;
            pointer-events: auto !important;
            width: 44px !important;
            height: 44px !important;
            align-items: center !important;
            justify-content: center !important;
            border: 1px solid {theme["border"]} !important;
            border-radius: 8px !important;
            background: {theme["surface"]} !important;
            box-shadow: {theme["soft_shadow"]} !important;
        }}

        [data-testid="stExpandSidebarButton"] button {{
            width: 44px !important;
            height: 44px !important;
            min-height: 44px !important;
            padding: 0 !important;
            color: {theme["text"]} !important;
        }}

        @media (prefers-reduced-motion: reduce) {{
            *, *::before, *::after {{
                animation-duration: 0.01ms !important;
                animation-iteration-count: 1 !important;
                scroll-behavior: auto !important;
                transition-duration: 0.01ms !important;
            }}
        }}

        @media (max-width: 1350px) {{
            .market-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}

        @media (max-width: 760px) {{
            [data-testid="stToolbar"] {{
                display: flex !important;
                visibility: visible !important;
                height: 0 !important;
                min-height: 0 !important;
                pointer-events: none !important;
            }}

            [data-testid="stToolbar"] [data-testid="stBaseButton-header"],
            [data-testid="stToolbar"] [data-testid="stMainMenuButton"] {{
                display: none !important;
                visibility: hidden !important;
            }}

            [data-testid="stSidebarCollapsedControl"] {{
                display: flex !important;
                position: fixed !important;
                top: 0.75rem !important;
                left: 0.75rem !important;
                z-index: 1000 !important;
                width: 44px !important;
                height: 44px !important;
                align-items: center !important;
                justify-content: center !important;
                border: 1px solid {theme["border"]} !important;
                border-radius: 8px !important;
                background: {theme["surface"]} !important;
                box-shadow: {theme["soft_shadow"]} !important;
            }}

            [data-testid="stSidebarCollapsedControl"] button {{
                width: 44px !important;
                height: 44px !important;
                min-height: 44px !important;
                padding: 0 !important;
                color: {theme["text"]} !important;
            }}

            [data-testid="stExpandSidebarButton"] {{
                display: flex !important;
                visibility: visible !important;
                position: fixed !important;
                top: 0.75rem !important;
                left: 0.75rem !important;
                z-index: 1000 !important;
                pointer-events: auto !important;
                width: 44px !important;
                height: 44px !important;
                align-items: center !important;
                justify-content: center !important;
                border: 1px solid {theme["border"]} !important;
                border-radius: 8px !important;
                background: {theme["surface"]} !important;
                box-shadow: {theme["soft_shadow"]} !important;
            }}

            [data-testid="stExpandSidebarButton"] button {{
                width: 44px !important;
                height: 44px !important;
                min-height: 44px !important;
                padding: 0 !important;
                color: {theme["text"]} !important;
            }}

            .block-container {{
                padding-left: 1rem;
                padding-right: 1rem;
                padding-top: 3.75rem;
            }}

            h1 {{
                font-size: 2.15rem !important;
                line-height: 1.1 !important;
            }}

            .research-brief {{
            border-top: 2px solid {theme["accent"]};
            margin: 1.75rem 0 1.25rem;
            padding: 1rem 0 0.25rem;
        }}

        .research-brief-heading,
        .research-quality {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.75rem;
            flex-wrap: wrap;
        }}

        .research-brief-heading h3 {{
            margin: 0 !important;
        }}

        .section-eyebrow {{
            color: {theme["accent"]};
            font-size: 0.72rem;
            font-weight: 850;
            letter-spacing: 0.08em;
            margin-bottom: 0.3rem;
        }}

        .research-status {{
            border-left: 3px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.92rem;
            font-weight: 850;
            padding-left: 0.55rem;
        }}

        .research-status--ready {{
            border-left-color: {theme["success"]};
            color: {theme["success"]};
        }}

        .research-status--caution {{
            border-left-color: {theme["warning"]};
            color: {theme["warning"]};
        }}

        .research-quality {{
            border-bottom: 1px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.95rem;
            line-height: 1.5;
            margin-top: 0.8rem;
            padding: 0 0 0.8rem;
        }}

        .research-quality strong {{
            color: {theme["text"]};
        }}

        .research-warnings {{
            color: {theme["muted_text"]};
            font-size: 0.94rem;
            line-height: 1.5;
            margin: 0.75rem 0 0;
            padding-left: 1.15rem;
        }}

        .research-evidence {{
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
            min-height: 188px;
            padding: 1rem;
        }}

        .research-evidence--positive {{ border-top: 3px solid {theme["success"]}; }}
        .research-evidence--neutral {{ border-top: 3px solid {theme["secondary"]}; }}
        .research-evidence--risk {{ border-top: 3px solid {theme["danger"]}; }}
        .research-evidence--unavailable {{ border-top: 3px solid {theme["border"]}; }}

        .research-evidence-headline {{
            color: {theme["text"]};
            font-size: 1.12rem;
            font-weight: 850;
            line-height: 1.35;
            margin: 0.5rem 0;
        }}

        .research-evidence-metrics {{
            color: {theme["muted_text"]};
            font-size: 0.92rem;
            line-height: 1.45;
            margin-top: 0.85rem;
        }}
        .dashboard-topline {{
                flex-direction: column;
                align-items: stretch;
                gap: 0.85rem;
            }}

            .dashboard-topline h1 {{
                font-size: 2.15rem !important;
            }}

            .page-date {{
                font-size: 0.95rem !important;
            }}

            .status-group {{
                justify-content: stretch;
            }}

            .status-pill {{
                width: 100%;
                justify-content: flex-start;
                text-align: left;
            }}

            .detail-header {{
                flex-direction: column;
            }}

            .detail-tag-group {{
                justify-content: flex-start;
            }}

            .market-card, .watch-card, .section-card, .info-card {{
                padding: 16px;
                border-radius: var(--ui-radius);
            }}

            .market-grid {{
                grid-template-columns: 1fr;
            }}

            .watch-card {{
                min-height: 0;
            }}

            .price-text {{
                font-size: 1.62rem;
                overflow-wrap: anywhere;
            }}

            .detail-title {{
                font-size: 1.65rem;
            }}

            .metric-row {{
                grid-template-columns: 1fr;
            }}

            .metric-row > div:nth-child(2n) {{
                padding-left: 0;
                border-left: 0;
            }}

            .score-wrap {{
                grid-template-columns: 1fr;
            }}

            .score-line {{
                grid-template-columns: 64px 1fr 40px;
            }}
        }}

        /* Research terminal visual system */
        .research-shell {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(260px, 0.62fr);
            align-items: end;
            gap: var(--space-6);
            margin: 0 0 var(--space-6);
            padding: var(--space-4) 0 var(--space-6);
            border-top: 2px solid {theme["accent"]};
            border-bottom: 1px solid {theme["border"]};
        }}

        .research-shell .page-header-copy {{
            padding-top: var(--space-2);
        }}

        .research-shell h1 {{
            font-size: 2.6rem !important;
            font-weight: 800 !important;
            line-height: 1.06 !important;
        }}

        .st-key-active_page {{
            max-width: 760px;
            margin: 0 0 var(--space-6);
        }}

        .st-key-active_page [role="radiogroup"] {{
            display: grid !important;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: var(--space-2) !important;
            padding: var(--space-2);
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-radius: var(--ui-radius);
        }}

        .st-key-active_page label {{
            min-width: 0;
            min-height: 44px;
            justify-content: center;
            padding: 0.55rem 0.7rem !important;
            border: 1px solid transparent;
            border-radius: 4px;
            color: {theme["muted_text"]} !important;
            font-weight: 750 !important;
            text-align: center;
            transition: background-color 180ms ease, border-color 180ms ease, color 180ms ease;
        }}

        .st-key-active_page label > div:first-child {{
            display: none;
        }}

        .st-key-active_page label input {{
            position: absolute;
            opacity: 0;
            pointer-events: none;
        }}

        .st-key-active_page label:hover {{
            background: {theme["card"]};
            border-color: {theme["border"]};
            color: {theme["text"]} !important;
        }}

        .st-key-active_page label:has(input:checked) {{
            background: {theme["card"]};
            border-color: {theme["accent"]};
            color: {theme["text"]} !important;
        }}

        .product-footer {{
            display: flex;
            flex-wrap: wrap;
            gap: var(--space-2) var(--space-6);
            margin-top: var(--space-8);
            padding: var(--space-4) 0 var(--space-6);
            border-top: 1px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.86rem;
            line-height: 1.55;
        }}

        .product-footer strong {{
            color: {theme["text"]};
        }}        .research-shell .page-date {{
            max-width: 54rem;
            margin-top: var(--space-3);
            color: {theme["muted_text"]};
        }}

        .data-rail {{
            display: flex;
            align-items: stretch;
            justify-content: flex-end;
            gap: var(--space-2);
            min-width: 0;
            padding-left: var(--space-4);
            border-left: 1px solid {theme["border"]};
        }}

        .data-rail .status-pill {{
            align-self: stretch;
            justify-content: flex-start;
            min-height: 44px;
            padding: 0.55rem 0.75rem;
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-left: 3px solid {theme["border"]};
            font-variant-numeric: tabular-nums;
        }}

        .data-rail .status-pill.live {{
            border-left-color: {theme["success"]};
            color: {theme["text"]};
        }}

        .market-grid {{
            gap: var(--space-4);
            margin-bottom: var(--space-6);
        }}

        .market-card {{
            min-height: 152px;
            padding: 1.15rem 1.2rem 1.1rem 1.35rem;
            border-left: 3px solid {theme["accent"]};
        }}

        .market-card::before {{
            display: none;
        }}

        .market-card .price-text,
        .watch-card .price-text,
        .metric-value,
        [data-testid="stMetricValue"] {{
            font-family: var(--ui-data-font);
            font-variant-numeric: tabular-nums;
        }}

        .market-card .price-text {{
            font-size: 1.72rem;
        }}

        .market-card .positive,
        .market-card .negative,
        .watch-card .positive,
        .watch-card .negative {{
            display: inline-flex;
            align-items: center;
            min-height: 1.55rem;
            margin-top: var(--space-2);
            padding: 0.05rem 0;
            font-family: var(--ui-data-font);
            font-size: 0.95rem;
        }}

        .watch-card {{
            min-height: 292px;
            padding: 1.3rem 1.35rem;
            border-top: 0;
            border-left: 3px solid {theme["border"]};
        }}

        .watch-card::before {{
            inset: auto 0 0 0;
            height: 1px;
            background: {theme["border"]};
            opacity: 1;
        }}

        .watch-card:hover {{
            border-left-color: {theme["accent"]};
        }}

        .card-spacer {{
            padding-bottom: var(--space-4);
        }}

        .metric-row {{
            column-gap: var(--space-6);
            row-gap: var(--space-3);
            margin-top: var(--space-4);
        }}

        .metric-label {{
            font-size: 0.88rem;
            font-weight: 700;
        }}

        .metric-value {{
            font-size: 1.04rem;
            line-height: 1.35;
        }}

        .instrument-workspace {{
            position: relative;
            margin-top: var(--space-3);
            padding: 1.45rem 1.5rem;
            border-top: 2px solid {theme["accent"]};
            background: {theme["card"]};
        }}

        .instrument-workspace .detail-header {{
            gap: var(--space-6);
        }}

        .instrument-workspace .detail-title {{
            font-size: 2.25rem;
            line-height: 1.12;
        }}

        .instrument-workspace .price-text {{
            margin-top: var(--space-4);
            font-size: 2.4rem;
            font-family: var(--ui-data-font);
            font-variant-numeric: tabular-nums;
        }}

        .instrument-workspace .detail-tag-group {{
            max-width: 30rem;
            gap: var(--space-2);
        }}

        .research-brief {{
            margin: var(--space-8) 0 var(--space-4);
            padding: var(--space-4) 0 0.25rem;
            border-top-width: 2px;
        }}

        .research-quality {{
            display: grid;
            grid-template-columns: minmax(9rem, 1fr) repeat(2, auto);
            column-gap: var(--space-4);
            align-items: center;
            padding-bottom: var(--space-4);
        }}

        .readiness-panel {{
            display: grid;
            grid-template-columns: minmax(9.5rem, 0.7fr) minmax(0, 3.3fr);
            margin: 0 0 var(--space-6);
            overflow: hidden;
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-top: 3px solid {theme["warning"]};
            border-radius: var(--ui-radius);
        }}

        .readiness-panel--ready {{ border-top-color: {theme["success"]}; }}
        .readiness-panel--limited {{ border-top-color: {theme["danger"]}; }}

        .readiness-score {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            min-height: 11rem;
            padding: var(--space-5);
            background: {theme["surface"]};
            border-right: 1px solid {theme["border"]};
        }}

        .readiness-score > span,
        .readiness-action-label {{
            color: {theme["muted_text"]};
            font-size: 0.78rem;
            font-weight: 800;
        }}

        .readiness-score strong {{
            color: {theme["text"]};
            font-family: var(--ui-data-font);
            font-size: 3rem;
            font-variant-numeric: tabular-nums;
            line-height: 1;
        }}

        .readiness-score small {{
            color: {theme["muted_text"]};
            font-family: var(--ui-data-font);
            font-size: 0.9rem;
        }}

        .readiness-content {{
            min-width: 0;
            padding: var(--space-5);
        }}

        .readiness-heading {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: var(--space-3);
            flex-wrap: wrap;
        }}

        .readiness-heading h4 {{
            margin: 0;
            color: {theme["text"]};
            font-size: 1.15rem;
        }}

        .readiness-heading span {{
            color: {theme["muted_text"]};
            font-size: 0.78rem;
        }}

        .readiness-summary {{
            margin: var(--space-2) 0 var(--space-4);
            color: {theme["muted_text"]};
            line-height: 1.55;
        }}

        .readiness-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: var(--space-3);
        }}

        .readiness-dimension {{
            min-width: 0;
            padding: var(--space-3);
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-radius: calc(var(--ui-radius) - 2px);
        }}

        .readiness-dimension-heading {{
            display: flex;
            justify-content: space-between;
            gap: var(--space-2);
            color: {theme["text"]};
            font-size: 0.85rem;
        }}

        .readiness-dimension-heading span {{
            color: {theme["muted_text"]};
            font-family: var(--ui-data-font);
            white-space: nowrap;
        }}

        .readiness-track {{
            height: 4px;
            margin: var(--space-2) 0;
            overflow: hidden;
            background: {theme["border"]};
        }}

        .readiness-track span {{
            display: block;
            height: 100%;
            background: {theme["accent"]};
        }}

        .readiness-dimension p {{
            margin: 0;
            color: {theme["muted_text"]};
            font-size: 0.78rem;
            line-height: 1.45;
        }}

        .readiness-action-label {{
            margin-top: var(--space-4);
        }}

        .readiness-actions {{
            margin: var(--space-2) 0 0;
            padding-left: 1.1rem;
            color: {theme["muted_text"]};
            font-size: 0.82rem;
            line-height: 1.5;
        }}

        @media (max-width: 1024px) {{
            .readiness-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}

        @media (max-width: 760px) {{
            .readiness-panel,
            .readiness-grid {{
                grid-template-columns: minmax(0, 1fr);
            }}

            .readiness-score {{
                min-height: 0;
                flex-direction: row;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4);
                border-right: 0;
                border-bottom: 1px solid {theme["border"]};
            }}

            .readiness-score strong {{
                font-size: 2.25rem;
            }}

            .readiness-content {{
                padding: var(--space-4);
            }}
        }}
        .coherence-panel {{
            margin: 0 0 var(--space-6);
            padding: var(--space-4);
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-left: 3px solid {theme["secondary"]};
            border-radius: var(--ui-radius);
        }}

        .coherence-panel--aligned {{ border-left-color: {theme["success"]}; }}
        .coherence-panel--divergent {{ border-left-color: {theme["warning"]}; }}
        .coherence-panel--risk-heavy {{ border-left-color: {theme["danger"]}; }}
        .coherence-panel--incomplete {{ border-left-color: {theme["border"]}; }}

        .coherence-heading {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: var(--space-3);
            flex-wrap: wrap;
        }}

        .coherence-heading h3 {{
            margin: 0 !important;
        }}

        .coherence-heading > span {{
            color: {theme["muted_text"]};
            font-size: 0.78rem;
        }}

        .coherence-status {{
            margin-top: var(--space-3);
            color: {theme["text"]};
            font-size: 1.02rem;
            font-weight: 850;
        }}

        .coherence-summary,
        .coherence-next {{
            color: {theme["muted_text"]};
            line-height: 1.5;
        }}

        .coherence-summary {{
            margin: var(--space-1) 0 var(--space-3);
        }}

        .coherence-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: var(--space-2);
        }}

        .coherence-count {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-2);
            padding: 0.55rem 0.7rem;
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-radius: calc(var(--ui-radius) - 2px);
            color: {theme["muted_text"]};
            font-size: 0.82rem;
        }}

        .coherence-count strong {{
            color: {theme["text"]};
            font-family: var(--ui-data-font);
            font-size: 1.1rem;
        }}

        .coherence-next {{
            margin: var(--space-3) 0 0;
            font-size: 0.82rem;
        }}

        .coherence-next strong {{
            color: {theme["text"]};
        }}

        @media (max-width: 1024px) {{
            .coherence-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}

        @media (max-width: 760px) {{
            .coherence-grid {{
                grid-template-columns: minmax(0, 1fr);
            }}
        }}
        .research-path {{
            margin: 0 0 var(--space-6);
            padding: var(--space-4);
            background: {theme["surface"]};
            border: 1px solid {theme["border"]};
            border-top: 3px solid {theme["accent"]};
            border-radius: var(--ui-radius);
        }}

        .research-path-heading {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: var(--space-3);
            flex-wrap: wrap;
        }}

        .research-path-heading h3 {{ margin: 0 !important; }}

        .research-path-heading > span {{
            color: {theme["accent"]};
            font-size: 0.84rem;
            font-weight: 850;
        }}

        .research-path-summary {{
            max-width: 70rem;
            margin: var(--space-2) 0 var(--space-4);
            color: {theme["muted_text"]};
            font-size: 0.9rem;
            line-height: 1.5;
        }}

        .research-path-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: var(--space-3);
        }}

        .research-path-step {{
            min-width: 0;
            padding: var(--space-3);
            background: {theme["card"]};
            border: 1px solid {theme["border"]};
            border-top: 3px solid {theme["secondary"]};
            border-radius: calc(var(--ui-radius) - 2px);
        }}

        .research-path-step--complete {{ border-top-color: {theme["success"]}; }}
        .research-path-step--review {{ border-top-color: {theme["warning"]}; }}
        .research-path-step--blocked {{ border-top-color: {theme["danger"]}; }}

        .research-path-step-heading {{
            display: flex;
            align-items: center;
            gap: var(--space-2);
        }}

        .research-path-step-index {{
            display: inline-flex;
            flex: 0 0 auto;
            align-items: center;
            justify-content: center;
            width: 1.65rem;
            height: 1.65rem;
            border: 1px solid {theme["border"]};
            border-radius: 50%;
            color: {theme["text"]};
            font-family: var(--ui-data-font);
            font-size: 0.8rem;
            font-weight: 850;
        }}

        .research-path-step-label {{
            flex: 1 1 auto;
            min-width: 0;
            color: {theme["text"]};
            font-size: 0.94rem;
            font-weight: 850;
        }}

        .research-path-step-status {{
            flex: 0 0 auto;
            color: {theme["muted_text"]};
            font-size: 0.74rem;
            font-weight: 800;
            white-space: nowrap;
        }}

        .research-path-step--complete .research-path-step-status {{ color: {theme["success"]}; }}
        .research-path-step--review .research-path-step-status {{ color: {theme["warning"]}; }}
        .research-path-step--blocked .research-path-step-status {{ color: {theme["danger"]}; }}

        .research-path-step-detail {{
            margin: var(--space-2) 0 0;
            color: {theme["muted_text"]};
            font-size: 0.8rem;
            line-height: 1.48;
        }}

        .research-path-next {{
            margin-top: var(--space-4);
            padding-top: var(--space-3);
            border-top: 1px solid {theme["border"]};
            color: {theme["muted_text"]};
            font-size: 0.88rem;
            line-height: 1.5;
        }}

        .research-path-next strong {{ color: {theme["text"]}; }}

        @media (max-width: 1024px) {{
            .research-path-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}

        @media (max-width: 760px) {{
            .research-path {{ padding: var(--space-3); }}
            .research-path-grid {{ grid-template-columns: minmax(0, 1fr); }}
        }}
        .evidence-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: var(--space-3);
            margin-bottom: var(--space-6);
        }}

        .research-evidence {{
            min-height: 216px;
            padding: 1.15rem;
            display: flex;
            flex-direction: column;
        }}

        .research-evidence-headline {{
            font-size: 1.08rem;
            line-height: 1.42;
        }}

        .research-evidence-metrics {{
            margin-top: auto;
            padding-top: var(--space-3);
            border-top: 1px solid {theme["border"]};
            font-family: var(--ui-data-font);
            font-size: 0.82rem;
        }}

        .stock-section-title {{
            margin-top: var(--space-8);
            margin-bottom: var(--space-3);
            font-size: 1.3rem;
        }}

        .stPlotlyChart {{
            margin: var(--space-3) 0 var(--space-6);
            border-top: 2px solid {theme["border"]};
        }}

        div[data-testid="stDataFrame"] {{
            margin-bottom: var(--space-6);
        }}

        @media (max-width: 1024px) {{
            .research-shell {{
                grid-template-columns: 1fr;
                gap: var(--space-4);
            }}

            .data-rail {{
                justify-content: flex-start;
                padding: var(--space-3) 0 0;
                border-top: 1px solid {theme["border"]};
                border-left: 0;
            }}

            .market-grid,
            .evidence-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}

            .research-quality {{
                grid-template-columns: 1fr 1fr;
                row-gap: var(--space-2);
            }}

            .research-quality strong {{
                grid-column: 1 / -1;
            }}
        }}

        @media (max-width: 760px) {{
            [data-testid="stSidebar"] {{
                position: fixed !important;
                inset: 0 auto 0 0;
                z-index: 1200 !important;
                width: min(86vw, 320px) !important;
                max-width: 320px !important;
                overflow-y: auto;
                box-shadow: {theme["hover_shadow"]};
            }}

            .block-container {{
                padding-top: 4.5rem;
                padding-bottom: var(--space-6);
            }}

            .st-key-active_page {{
                max-width: none;
                margin-bottom: var(--space-4);
            }}

            .st-key-active_page [role="radiogroup"] {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-1) !important;
                padding: var(--space-1);
            }}

            .st-key-active_page label {{
                min-height: 52px;
                padding: 0.45rem 0.4rem !important;
                font-size: 0.78rem !important;
                line-height: 1.2;
                white-space: normal;
            }}

            .product-footer {{
                display: grid;
                gap: var(--space-2);
            }}            .research-shell {{
                margin-bottom: var(--space-4);
                padding-top: var(--space-3);
            }}

            .research-shell h1 {{
                font-size: 2rem !important;
                line-height: 1.12 !important;
            }}

            .data-rail {{
                display: block;
            }}

            .data-rail .status-pill {{
                width: 100%;
            }}

            .market-grid,
            .evidence-grid {{
                grid-template-columns: minmax(0, 1fr);
                gap: var(--space-3);
            }}

            .market-card {{
                min-height: 142px;
            }}

            .watch-card {{
                min-height: 0;
                padding: 1.15rem;
            }}

            .metric-row {{
                column-gap: var(--space-4);
            }}

            .instrument-workspace {{
                padding: 1.2rem;
            }}

            .instrument-workspace .detail-header {{
                display: block;
            }}

            .instrument-workspace .detail-title {{
                font-size: 1.75rem;
            }}

            .instrument-workspace .price-text {{
                font-size: 1.92rem;
            }}

            .instrument-workspace .detail-tag-group {{
                justify-content: flex-start;
                margin-top: var(--space-4);
            }}

            .research-quality {{
                grid-template-columns: 1fr;
            }}

            .research-evidence {{
                min-height: 0;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def apply_plotly_theme(fig, theme: dict, title: str | None = None):
    fig.update_layout(
        title=dict(text=title, x=0.01, xanchor="left") if title else None,
        template=theme.get("plotly_template", "plotly_dark"),
        paper_bgcolor=theme["card"],
        plot_bgcolor=theme["card"],
        font=dict(
            family="Microsoft JhengHei UI, Microsoft JhengHei, Noto Sans TC, sans-serif",
            color=theme["text"],
            size=14,
        ),
        title_font=dict(color=theme["text"], size=19),
        margin=dict(l=24, r=20, t=64, b=40),
        hovermode="x unified",
        xaxis=dict(
            gridcolor=theme["chart_grid"],
            tickfont=dict(color=theme["muted_text"], size=13),
            title=dict(font=dict(color=theme["text"])),
            zerolinecolor=theme["chart_grid"],
            linecolor=theme["border"],
            automargin=True,
        ),
        yaxis=dict(
            gridcolor=theme["chart_grid"],
            tickfont=dict(color=theme["muted_text"], size=13),
            title=dict(font=dict(color=theme["text"])),
            zerolinecolor=theme["chart_grid"],
            linecolor=theme["border"],
            automargin=True,
        ),
        legend=dict(font=dict(color=theme["text"])),
        hoverlabel=dict(bgcolor=theme["surface"], font_color=theme["text"], bordercolor=theme["border"]),
    )
    return fig


def line_with_anomalies(df: pd.DataFrame, y: str, title: str, y_title: str, theme: dict):
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["date"],
            y=df[y],
            mode="lines",
            line=dict(color=theme["primary"], width=2.4),
            name=y_title,
        )
    )
    anomalies = df[df["model_anomaly"] == 1]
    fig.add_trace(
        go.Scatter(
            x=anomalies["date"],
            y=anomalies[y],
            mode="markers",
            marker=dict(
                color=theme["danger"],
                size=10,
                symbol="diamond-open",
                line=dict(color=theme["accent"], width=2),
            ),
            name="異常事件",
        )
    )
    apply_plotly_theme(fig, theme, title)
    fig.update_layout(height=380)
    fig.update_yaxes(title_text=y_title, title_font=dict(color=theme["text"]))
    fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
    return fig


def style_anomaly_table(table: pd.DataFrame, theme: dict):
    return table.style.set_properties(
        **{
            "background-color": theme["card"],
            "color": theme["text"],
            "border-color": theme["border"],
        }
    ).set_table_styles(
        [
            {"selector": "th", "props": [("background-color", theme["table_header"]), ("color", theme["text"])]},
            {"selector": "td", "props": [("border-color", theme["border"])]},
        ]
    )


def change_class(value: float) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "neutral"


def market_source_label(source: object) -> str:
    return {
        "sample": "DEMO",
        "yfinance": "LIVE",
        "twse_openapi": "LIVE",
        "local_cache": "快取",
        "unavailable": "離線",
    }.get(str(source or "").strip(), str(source or "未知"))

def render_market_cards(theme: dict, cards: list[dict] | None = None) -> None:
    st.header("大盤指數")
    cards = cards if cards is not None else build_market_cards()
    if not cards:
        st.info("目前無法取得大盤資料，請稍後再試或檢查網路。")
        return
    card_items = []
    for card in cards[:4]:
        css_class = change_class(card["change_pct"])
        card_label = escape_html(stock_display_pair(card["symbol"], card["display"]))
        card_region = escape_html(card["region"])
        card_source = escape_html(market_source_label(card["source"]))
        card_items.append(
            f"""
            <div class="market-card">
                <div class="market-card-header">
                    <div class="market-card-copy">
                        <div class="card-title">{card_label}</div>
                        <div class="card-subtitle">{card_region} · {card_source} · 截至 {escape_html(card.get("latest_date", "未知"))}</div>
                    </div>
                    <span class="tag market-symbol-tag">{card_region}</span>
                </div>
                <div class="price-text">{card["latest_close"]:,.2f}</div>
                <div class="{css_class}">{card["change_pct"]:+.2f}%（{card["change"]:+.2f}）</div>
            </div>
            """
        )
    # Keep every card in one continuous HTML block so Streamlit does not treat
    # later indented cards as a code block.
    card_markup = "".join(item.strip() for item in card_items)
    st.markdown(f'<div class="market-grid">{card_markup}</div>', unsafe_allow_html=True)


def render_popular_stocks(cards: list[dict], industry: str = "全部") -> None:
    st.header("熱門股")
    if not cards:
        st.info("目前沒有可顯示的熱門股資料，請稍後重試。")
        return
    if industry == "全部":
        st.caption("市場代表標的，依最新可用資料更新。")
    else:
        st.caption(f"目前顯示「{industry}」類別中的熱門追蹤標的。")
    columns = st.columns(2, gap="large")
    for index, card in enumerate(cards):
        css_class = change_class(card["change_pct"])
        card_label = escape_html(stock_display_pair(card["symbol"], card["display"]))
        card_category = escape_html(card["category"])
        card_source = escape_html(market_source_label(card["source"]))
        card_currency = escape_html(card.get("currency", ""))
        with columns[index % 2]:
            st.markdown(
                f"""
                <div class="card-spacer"><article class="watch-card" aria-label="{card_label}">
                    <div class="watch-card-header">
                        <div class="watch-card-copy">
                            <div class="card-title">{card_label}</div>
                            <div class="card-subtitle">{card_category} · 截至 {escape_html(card.get("latest_date", "未知"))}</div>
                        </div>
                        <span class="tag">{card_source}</span>
                    </div>
                    <div class="price-text">{card["latest_close"]:,.2f} <span class="currency-label">{card_currency}</span></div>
                    <div class="{css_class}">{card["change_pct"]:+.2f}%（{card["change"]:+.2f}）</div>
                    <div class="metric-row">
                        <div><div class="metric-label">成交量</div><div class="metric-value">{format_number(card["volume"], 1)}</div></div>
                        <div><div class="metric-label">20 日均量</div><div class="metric-value">{format_number(card["avg_volume"], 1)}</div></div>
                        <div><div class="metric-label">52 週高</div><div class="metric-value">{card["high_52w"]:,.2f}</div></div>
                        <div><div class="metric-label">52 週低</div><div class="metric-value">{card["low_52w"]:,.2f}</div></div>
                    </div>
                </article></div>
                """,
                unsafe_allow_html=True,
            )


def make_price_chart(history: pd.DataFrame, theme: dict, title: str, selected_indicators: list[str] | None = None):
    indicator_set = set(DEFAULT_TECHNICAL_INDICATORS if selected_indicators is None else selected_indicators)
    data = compute_technical_indicators(history)
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=data["date"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            close=data["close"],
            name="K 線",
            increasing_line_color=theme["success"],
            increasing_fillcolor=theme["success"],
            decreasing_line_color=theme["danger"],
            decreasing_fillcolor=theme["danger"],
        )
    )
    if "MA5" in indicator_set:
        fig.add_trace(go.Scatter(x=data["date"], y=data["ma5"], mode="lines", line=dict(color=theme["accent"], width=1.6), name="MA5"))
    if "MA20" in indicator_set:
        fig.add_trace(
            go.Scatter(
                x=data["date"],
                y=data["ma20"],
                mode="lines",
                line=dict(color=theme["secondary"], width=1.7, dash="dash"),
                name="MA20",
            )
        )
    if "MA60" in indicator_set:
        fig.add_trace(
            go.Scatter(
                x=data["date"],
                y=data["ma60"],
                mode="lines",
                line=dict(color=theme["primary"], width=1.4, dash="dot"),
                name="MA60",
            )
        )
    if "布林通道" in indicator_set:
        mid = data["close"].rolling(20, min_periods=5).mean()
        std = data["close"].rolling(20, min_periods=5).std()
        upper = mid + 2 * std
        lower = mid - 2 * std
        fig.add_trace(
            go.Scatter(
                x=data["date"],
                y=upper,
                mode="lines",
                line=dict(color=theme["warning"], width=1, dash="dot"),
                name="布林上軌",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=data["date"],
                y=lower,
                mode="lines",
                fill="tonexty",
                fillcolor=hex_to_rgba(theme["warning"], 0.08),
                line=dict(color=theme["warning"], width=1, dash="dot"),
                name="布林下軌",
            )
        )
    apply_plotly_theme(fig, theme, title)
    fig.update_layout(height=460, xaxis_rangeslider_visible=False)
    fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
    fig.update_yaxes(title_text="價格", title_font=dict(color=theme["text"]))
    return fig


def make_volume_chart(history: pd.DataFrame, theme: dict):
    data = compute_technical_indicators(history)
    colors = np.where(data["close"].diff().fillna(0) >= 0, theme["success"], theme["danger"])
    fig = go.Figure()
    fig.add_trace(go.Bar(x=data["date"], y=data["volume"], marker_color=colors, name="成交量"))
    fig.add_trace(go.Scatter(x=data["date"], y=data["volume_ma20"], mode="lines", line=dict(color=theme["accent"], width=1.8), name="20 日均量"))
    apply_plotly_theme(fig, theme, "成交量")
    fig.update_layout(height=230)
    fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
    fig.update_yaxes(title_text="成交量", title_font=dict(color=theme["text"]))
    return fig


def make_rsi_chart(history: pd.DataFrame, theme: dict):
    data = compute_technical_indicators(history)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=data["date"], y=data["rsi14"], mode="lines", line=dict(color=theme["primary"], width=2), name="RSI(14)"))
    fig.add_hline(y=70, line_dash="dash", line_color=theme["danger"], opacity=0.7, annotation_text="超買 70")
    fig.add_hline(y=30, line_dash="dash", line_color=theme["success"], opacity=0.7, annotation_text="超賣 30")
    apply_plotly_theme(fig, theme, "RSI(14)")
    fig.update_layout(height=230)
    fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
    fig.update_yaxes(title_text="RSI", title_font=dict(color=theme["text"]), range=[0, 100])
    return fig


def make_macd_chart(history: pd.DataFrame, theme: dict):
    data = compute_technical_indicators(history)
    ema12 = data["close"].ewm(span=12, adjust=False).mean()
    ema26 = data["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    colors = np.where(histogram >= 0, theme["success"], theme["danger"])
    fig = go.Figure()
    fig.add_trace(go.Bar(x=data["date"], y=histogram, marker_color=colors, name="柱狀差"))
    fig.add_trace(go.Scatter(x=data["date"], y=macd, mode="lines", line=dict(color=theme["primary"], width=2), name="MACD"))
    fig.add_trace(go.Scatter(x=data["date"], y=signal, mode="lines", line=dict(color=theme["accent"], width=1.7), name="Signal"))
    apply_plotly_theme(fig, theme, "MACD")
    fig.update_layout(height=230)
    fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
    fig.update_yaxes(title_text="MACD", title_font=dict(color=theme["text"]))
    return fig


def format_percent(value: float) -> str:
    return f"{value:+.2f}%"


def render_performance_cards(analysis: dict) -> None:
    st.markdown('<h3 class="stock-section-title">近期表現</h3>', unsafe_allow_html=True)
    columns = st.columns(4)
    for col, (label, value) in zip(columns, analysis["performance"].items()):
        safe_label = escape_html(label)
        css_class = change_class(value)
        col.markdown(
            f"""
            <div class="info-card">
                <div class="metric-label">{safe_label}</div>
                <div class="metric-value {css_class}" style="font-size:1.35rem;">{format_percent(value)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_research_readiness(readiness: dict) -> None:
    score = max(0, min(100, int(readiness.get("score", 0) or 0)))
    level = str(readiness.get("level", "limited"))
    if level not in {"ready", "review", "limited"}:
        level = "limited"
    label = escape_html(readiness.get("label", "資料條件受限"))
    summary = escape_html(readiness.get("summary", "目前沒有足夠資料完成品質判讀。"))

    dimension_items = []
    for item in readiness.get("dimensions", []):
        dimension_score = max(0, int(item.get("score", 0) or 0))
        max_score = max(1, int(item.get("max_score", 1) or 1))
        progress = min(100, round(dimension_score / max_score * 100))
        dimension_items.append(
            f'''<article class="readiness-dimension" role="listitem">
                <div class="readiness-dimension-heading">
                    <strong>{escape_html(item.get("label", ""))}</strong>
                    <span>{dimension_score} / {max_score}</span>
                </div>
                <div class="readiness-track" aria-hidden="true"><span style="width:{progress}%"></span></div>
                <p>{escape_html(item.get("detail", ""))}</p>
            </article>'''
        )
    dimensions_markup = "".join(dimension_items)

    actions = [str(item) for item in readiness.get("actions", []) if str(item).strip()]
    actions_markup = "".join(f"<li>{escape_html(item)}</li>" for item in actions)
    st.markdown(
        f'''
        <section class="readiness-panel readiness-panel--{level}" aria-label="研究就緒度">
            <div class="readiness-score">
                <span>研究就緒度</span>
                <div><strong>{score}</strong><small>/100</small></div>
            </div>
            <div class="readiness-content">
                <div class="readiness-heading">
                    <h4>{label}</h4>
                    <span>這不是股票評分，不代表投資價值</span>
                </div>
                <p class="readiness-summary">{summary}</p>
                <div class="readiness-grid" role="list">{dimensions_markup}</div>
                <div class="readiness-action-label">下一步檢查</div>
                <ul class="readiness-actions">{actions_markup}</ul>
            </div>
        </section>
        ''',
        unsafe_allow_html=True,
    )

def render_evidence_coherence(coherence: dict) -> None:
    status = str(coherence.get("status", "incomplete"))
    allowed_statuses = {"aligned", "divergent", "risk-heavy", "mixed", "incomplete"}
    if status not in allowed_statuses:
        status = "incomplete"
    label = escape_html(coherence.get("label", "證據尚不完整"))
    summary = escape_html(coherence.get("summary", "目前沒有足夠證據完成一致性判讀。"))
    next_focus = escape_html(coherence.get("next_focus", "先補足資料，再解讀技術證據。"))
    counts = coherence.get("counts", {})
    count_items = []
    for key, item_label in (("positive", "正向"), ("neutral", "中性"), ("risk", "風險"), ("unavailable", "不可用")):
        count = max(0, int(counts.get(key, 0) or 0)) if isinstance(counts, dict) else 0
        count_items.append(
            f'''<div class="coherence-count">
                <span>{item_label}</span><strong>{count}</strong>
            </div>'''
        )
    counts_markup = "".join(count_items)
    st.markdown(
        f'''
        <section class="coherence-panel coherence-panel--{status}" aria-label="證據一致性">
            <div class="coherence-heading">
                <div>
                    <div class="section-eyebrow">EVIDENCE COHERENCE</div>
                    <h3>證據一致性</h3>
                </div>
                <span>描述證據關係，不是股票評分</span>
            </div>
            <div class="coherence-status">{label}</div>
            <p class="coherence-summary">{summary}</p>
            <div class="coherence-grid" role="list">{counts_markup}</div>
            <p class="coherence-next"><strong>下一步：</strong>{next_focus}</p>
        </section>
        ''',
        unsafe_allow_html=True,
    )

def render_research_brief(brief: dict) -> None:
    quality = brief["data_quality"]
    quality_state = str(quality.get("state", "unavailable"))
    quality_label = RESEARCH_STATE_LABELS.get(quality_state, RESEARCH_STATE_LABELS["unavailable"])
    quality_class = "research-status--ready" if quality_state == "ready" else "research-status--caution"
    source_name = str(quality.get("source", "unavailable"))
    source_label = market_source_label(source_name)
    warnings = [str(item) for item in quality.get("warnings", []) if str(item).strip()]
    warnings_markup = "".join(f"<li>{escape_html(item)}</li>" for item in warnings)
    warning_section = (
        f'<ul class="research-warnings">{warnings_markup}</ul>'
        if warnings_markup
        else '<div class="research-warnings">目前欄位完整，可作為技術研究的起點。</div>'
    )
    observations = int(quality.get("observations", 0) or 0)
    coverage_pct = float(quality.get("coverage_pct", 0.0) or 0.0)
    latest_date = str(quality.get("latest_date", "")) or "無可用日期"
    st.markdown(
        f'''
        <section class="research-brief" aria-label="研究摘要">
            <div class="research-brief-heading">
                <div>
                    <div class="section-eyebrow">RESEARCH BRIEF</div>
                    <h3>研究摘要</h3>
                </div>
                <span class="research-status {quality_class}">{escape_html(quality_label)}</span>
            </div>
            <div class="research-quality">
                <strong>資料可信度</strong>
                <span>{escape_html(source_label)} · 最新資料 {escape_html(latest_date)}</span>
                <span>{observations} 筆觀測 · 覆蓋率 {coverage_pct:.0f}%</span>
            </div>
            {warning_section}
        </section>
        ''',
        unsafe_allow_html=True,
    )

    render_research_readiness(brief.get("readiness", {}))

    render_evidence_coherence(brief.get("coherence", {}))

    st.markdown('<h3 class="stock-section-title">證據矩陣</h3>', unsafe_allow_html=True)
    evidence = list(brief.get("evidence", []))
    if evidence:
        evidence_items = []
        for item in evidence:
            state = str(item.get("state", "unavailable"))
            state_class = state if state in {"positive", "neutral", "risk", "unavailable"} else "unavailable"
            metrics = " | ".join(escape_html(metric) for metric in item.get("metrics", [])) or "資料不足"
            evidence_items.append(
                f'''
                <article class="research-evidence research-evidence--{state_class}" role="listitem">
                    <div class="metric-label">{escape_html(item.get("label", ""))}</div>
                    <div class="research-evidence-headline">{escape_html(item.get("headline", ""))}</div>
                    <div class="card-subtitle">{escape_html(item.get("detail", ""))}</div>
                    <div class="research-evidence-metrics">{metrics}</div>
                </article>
                '''
            )
        evidence_markup = "".join(item.strip() for item in evidence_items)
        st.markdown(
            f'<div class="evidence-grid" role="list">{evidence_markup}</div>',
            unsafe_allow_html=True,
        )
    st.markdown('<h3 class="stock-section-title">本期變化</h3>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(brief.get("changes", {}).get("rows", [])), width="stretch", hide_index=True)

    st.markdown('<h3 class="stock-section-title">同業脈絡</h3>', unsafe_allow_html=True)
    peer_context = brief.get("peer_context", {})
    peer_summary = str(peer_context.get("summary", "資料不足以比較同業脈絡。"))
    if peer_context.get("state") == "unavailable":
        st.info(peer_summary)
    else:
        st.caption(peer_summary)
        st.dataframe(pd.DataFrame(peer_context.get("rows", [])), width="stretch", hide_index=True)


def render_research_workflow(workflow: dict) -> None:
    steps = workflow.get("steps", []) if isinstance(workflow, dict) else []
    if not steps:
        return
    next_step = workflow.get("next_step", {}) if isinstance(workflow, dict) else {}
    next_label = escape_html(next_step.get("label", "研究紀錄"))
    next_detail = escape_html(next_step.get("detail", "依序完成研究檢查後再保存快照。"))
    step_markup = []
    for index, item in enumerate(steps, start=1):
        status = str(item.get("status", "review"))
        if status not in {"complete", "review", "blocked"}:
            status = "review"
        step_markup.append(
            f'''<article class="research-path-step research-path-step--{status}" role="listitem">
                <div class="research-path-step-heading">
                    <span class="research-path-step-index" aria-hidden="true">{index}</span>
                    <span class="research-path-step-label">{escape_html(item.get("label", ""))}</span>
                    <span class="research-path-step-status">{escape_html(item.get("status_label", "需要覆核"))}</span>
                </div>
                <p class="research-path-step-detail">{escape_html(item.get("detail", ""))}</p>
            </article>'''
        )
    st.markdown(
        f'''
        <section class="research-path" aria-label="研究路徑">
            <div class="research-path-heading">
                <div>
                    <div class="section-eyebrow">RESEARCH PATH</div>
                    <h3>研究路徑</h3>
                </div>
                <span>下一步：{next_label}</span>
            </div>
            <p class="research-path-summary">{escape_html(workflow.get("summary", "依序檢查資料、證據、脈絡，再保存紀錄。"))}</p>
            <div class="research-path-grid" role="list">{"".join(step_markup)}</div>
            <div class="research-path-next"><strong>建議先做：</strong>{next_detail}</div>
        </section>
        ''',
        unsafe_allow_html=True,
    )

def render_snapshot_actions(snapshot: dict) -> None:
    as_of_date = str(snapshot.get("as_of_date", "")) or "unknown-date"
    symbol = str(snapshot.get("asset", {}).get("symbol", "stock"))
    safe_symbol = re.sub(r"[^A-Za-z0-9._-]+", "_", symbol).strip("._-") or "stock"
    safe_date = re.sub(r"[^0-9-]+", "", as_of_date) or "unknown-date"
    filename_base = f"research-snapshot-{safe_symbol}-{safe_date}"
    snapshot_id = str(snapshot.get("snapshot_id", ""))

    action_label, json_action, html_action = st.columns([1.2, 1, 1], gap="small", vertical_alignment="center")
    with action_label:
        st.caption(f"研究快照 · 截至 {as_of_date} · {snapshot_id[:12]}")
    with json_action:
        st.download_button(
            "下載 JSON",
            data=snapshot_to_json_bytes(snapshot),
            file_name=f"{filename_base}.json",
            mime="application/json",
            key=f"{filename_base}-json",
            use_container_width=True,
        )
    with html_action:
        st.download_button(
            "列印 HTML",
            data=render_snapshot_html(snapshot),
            file_name=f"{filename_base}.html",
            mime="text/html",
            key=f"{filename_base}-html",
            use_container_width=True,
        )
def render_stock_detail(
    selected_symbol: str,
    theme: dict,
    company_df: pd.DataFrame,
    peer_cards: list[dict],
    peer_industry: str,
    selected_indicators: list[str] | None = None,
) -> None:
    if selected_indicators is None:
        selected_indicators = DEFAULT_TECHNICAL_INDICATORS
    history, source = cached_stock_history(selected_symbol, period="1y")
    analysis = build_stock_analysis(history)
    if not analysis:
        st.warning("目前沒有足夠的個股資料可供分析，請稍後重試或改選其他股票。")
        return
    brief = build_research_brief(history, source, peer_cards, peer_industry)
    indicators = analysis["data"]
    latest = analysis["latest"]
    technical = analysis["technical"]
    change = float(latest["change"])
    change_pct = float(latest["change_pct"])
    display_name = lookup_stock_display_name(selected_symbol, company_df)
    stock_label = stock_display_pair(selected_symbol, display_name)
    safe_stock_label = escape_html(stock_label)
    safe_source = escape_html(market_source_label(source))
    safe_currency = escape_html(latest.get("currency", ""))
    css_class = change_class(change_pct)
    snapshot = build_research_snapshot(
        {
            "symbol": selected_symbol,
            "display_name": display_name,
            "industry": peer_industry,
            "currency": str(latest.get("currency", "")),
        },
        history,
        source,
        brief,
        datetime.now(timezone.utc),
    )

    st.header("個股分析")
    st.markdown(
        f"""
        <div class="section-card instrument-workspace">
            <div class="detail-header">
                <div class="detail-header-copy">
                    <div class="card-title detail-title">{safe_stock_label}</div>
                    <div class="card-subtitle">{safe_source} · 股票追蹤與技術分析</div>
                    <div class="price-text">{latest["close"]:,.2f} <span class="currency-label">{safe_currency}</span></div>
                    <div class="{css_class}">{change_pct:+.2f}%（{change:+.2f}）</div>
                </div>
                <div class="detail-tag-group">
                    <span class="tag">MA5 / MA20 / MA60</span>
                    <span class="tag">RSI / 量能 / 區間</span>
                    <span class="tag">TWSE 公司資料</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    workflow = build_research_workflow(
        brief.get("readiness", {}),
        brief.get("coherence", {}),
        brief.get("peer_context", {}),
    )
    render_research_workflow(workflow)
    render_research_brief(brief)
    render_snapshot_actions(snapshot)
    render_performance_cards(analysis)

    st.markdown('<h3 class="stock-section-title">技術圖表</h3>', unsafe_allow_html=True)
    st.caption("K 線固定顯示；均線、布林通道與副圖可在左側「技術指標」切換。")
    st.plotly_chart(
        make_price_chart(indicators, theme, f"{stock_label} 價格與指標", selected_indicators),
        width="stretch",
        config=PLOTLY_CONFIG,
    )
    sub_charts = []
    if "成交量" in selected_indicators:
        sub_charts.append(make_volume_chart(indicators, theme))
    if "RSI" in selected_indicators:
        sub_charts.append(make_rsi_chart(indicators, theme))
    if "MACD" in selected_indicators:
        sub_charts.append(make_macd_chart(indicators, theme))
    if sub_charts:
        chart_columns = st.columns(min(2, len(sub_charts)))
        for index, chart in enumerate(sub_charts):
            with chart_columns[index % len(chart_columns)]:
                st.plotly_chart(chart, width="stretch", config=PLOTLY_CONFIG)

    with st.expander("查看近期價格與成交量資料"):
        recent_prices = indicators[["date", "open", "high", "low", "close", "volume"]].tail(60).copy()
        recent_prices = recent_prices.rename(columns=DISPLAY_COLUMN_MAP).sort_values("日期", ascending=False)
        st.dataframe(recent_prices, width="stretch", hide_index=True)

    st.subheader("股票基本資料")
    info_cols = st.columns(6)
    info_values = [
        ("成交量", format_number(latest["volume"], 1)),
        ("20 日均量", format_number(indicators["volume"].tail(20).mean(), 1)),
        ("52 週最高", f"{technical['high_52w']:,.2f}"),
        ("52 週最低", f"{technical['low_52w']:,.2f}"),
        ("20 日壓力", f"{technical['resistance_20d']:,.2f}"),
        ("20 日支撐", f"{technical['support_20d']:,.2f}"),
    ]
    for col, (label, value) in zip(info_cols, info_values):
        col.markdown(
            f"""
            <div class="info-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value" style="font-size:1.25rem;">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_page_header(title: str, subtitle: str, status_text: str, status_live: bool = False) -> None:
    safe_title = escape_html(title)
    safe_subtitle = escape_html(subtitle)
    safe_status = escape_html(status_text)
    status_class = "status-pill live" if status_live else "status-pill"
    st.markdown(
        f"""
        <a class="skip-link" href="#main-content">跳到主要內容</a>
        <div class="dashboard-topline research-shell">
            <div class="page-header-copy" id="main-content" tabindex="-1">
                <h1>{safe_title}</h1>
                <div class="page-date help-text">{pd.Timestamp.today().strftime('%Y年%m月%d日')} · {safe_subtitle}</div>
            </div>
            <div class="status-group data-rail">
                <span class="{status_class}" role="status" aria-live="polite">{safe_status}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_data_service_notice(state: dict) -> None:
    mode = str(state.get("mode", "unavailable"))
    message = str(state.get("message", ""))
    if mode == "demo":
        st.warning(f"DEMO 示範模式：{message}")
    elif mode == "mixed":
        st.warning(f"部分資料已降級：{message}")
    elif mode == "unavailable":
        st.error(message)
    else:
        st.caption(message)

    status_column, action_column = st.columns([5, 1], gap="medium", vertical_alignment="center")
    with status_column:
        as_of_date = state.get("as_of_date")
        if as_of_date:
            st.caption(f"最新可用市場資料日：{as_of_date} · 行情快取最長 15 分鐘")
        else:
            st.caption("目前沒有可確認的市場資料日期。")
    with action_column:
        if st.button(
            "重新取得資料",
            key="refresh_market_data",
            help="清除本機快取並重新連線 yfinance 與 TWSE。",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.session_state["market_refresh_completed"] = True
            st.rerun()
    if st.session_state.pop("market_refresh_completed", False):
        st.success("已重新連線資料來源並更新畫面。")


def render_product_footer() -> None:
    st.markdown(
        """
        <footer class="product-footer">
            <strong>Research Trust Workbench</strong>
            <span>資料來源：yfinance、TWSE OpenAPI</span>
            <span>不建立帳號、不儲存上傳快照、不提供投資建議</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )

def render_market_radar_page(theme: dict) -> None:
    del theme
    render_market_radar(
        cached_load_twse_sources,
        cached_radar_histories,
        render_page_header,
        render_data_service_notice,
    )


def render_stock_analysis_page(theme: dict) -> None:
    with st.spinner("正在載入 TWSE 上市公司清單..."):
        company_profiles, company_source, esg_data, esg_source = cached_load_twse_sources()
    stock_universe = get_stock_universe(company_profiles)
    company_reference = company_profiles if not company_profiles.empty else esg_data
    industry_options = get_industry_options(stock_universe)

    if not st.session_state.get("stock_query_initialized"):
        query_symbol = str(st.query_params.get("symbol", "")).strip()
        resolved_query_symbol = resolve_custom_stock_symbol(query_symbol) if query_symbol else None
        if resolved_query_symbol:
            universe_lookup = stock_symbol_lookup(stock_universe)
            if resolved_query_symbol in universe_lookup:
                st.session_state["industry_filter"] = "全部"
                st.session_state["stock_analysis_symbol"] = resolved_query_symbol
                st.session_state["active_custom_stock_symbol"] = ""
            else:
                st.session_state["active_custom_stock_symbol"] = resolved_query_symbol
        st.session_state["stock_query_initialized"] = True

    with st.sidebar:
        selected_industry = st.selectbox("產業篩選", industry_options, key="industry_filter")
        filtered_universe = filter_stock_universe(stock_universe, selected_industry)
        stock_lookup = stock_symbol_lookup(filtered_universe)
        stock_symbols = [item["symbol"] for item in filtered_universe]
        if stock_symbols and st.session_state.get("stock_analysis_symbol") not in stock_symbols:
            st.session_state["stock_analysis_symbol"] = stock_symbols[0]
        selected_stock_symbol = st.selectbox(
            "股票分析代號",
            stock_symbols,
            format_func=lambda symbol: stock_option_label(stock_lookup[symbol]),
            key="stock_analysis_symbol",
        )
        selected_indicators = st.multiselect(
            "技術指標",
            TECHNICAL_INDICATOR_OPTIONS,
            default=DEFAULT_TECHNICAL_INDICATORS,
            key="technical_indicators",
            help="K 線固定顯示；這裡控制均線、布林通道與副圖。",
        )
        with st.form("custom_stock_form", clear_on_submit=False):
            custom_stock_symbol = st.text_input(
                "自訂股票代號",
                placeholder="例如 2881、TSLA、SPY",
                help="台股可輸入 4 到 6 碼，系統會自動轉為 yfinance 的 .TW 格式。",
                key="custom_stock_symbol_input",
                autocomplete="off",
            )
            form_actions = st.columns(2, gap="small")
            with form_actions[0]:
                apply_custom = st.form_submit_button("套用代號")
            with form_actions[1]:
                clear_custom = st.form_submit_button("清除代號")
        custom_symbol_error = ""
        if apply_custom:
            resolved_symbol = resolve_custom_stock_symbol(custom_stock_symbol)
            if resolved_symbol:
                st.session_state["active_custom_stock_symbol"] = resolved_symbol
            else:
                custom_symbol_error = "請輸入 4 到 6 碼台股代號，或合法的 yfinance 英文代號。"
        if clear_custom:
            st.session_state["active_custom_stock_symbol"] = ""
        if custom_symbol_error:
            st.warning(custom_symbol_error)
        active_custom_symbol = st.session_state.get("active_custom_stock_symbol", "")
        selected_yf_symbol = active_custom_symbol or selected_stock_symbol
        st.query_params["symbol"] = selected_yf_symbol
        all_stock_lookup = stock_symbol_lookup(stock_universe)
        selected_item = all_stock_lookup.get(selected_yf_symbol) or all_stock_lookup.get(to_yfinance_symbol(selected_yf_symbol))
        selected_stock_label = stock_display_pair(
            selected_yf_symbol,
            selected_item["display"] if selected_item else "自訂標的",
        )
        if active_custom_symbol:
            st.caption(f"目前使用自訂代號：{selected_stock_label}")
        else:
            st.caption(f"可選股票清單：{len(stock_universe)} 檔；資料源 {company_source}，亦可輸入合法 yfinance 代號。")

    with st.spinner("正在載入 yfinance 行情與產業比較資料..."):
        market_cards = cached_market_cards()
        popular_symbols = get_popular_symbols(stock_universe, selected_industry)
        popular_cards = cached_watchlist_cards(tuple(popular_symbols) if popular_symbols is not None else None)
        peer_symbols, peer_industry = get_peer_comparison_symbols(stock_universe, selected_yf_symbol, selected_industry)
        peer_cards = cached_watchlist_cards(tuple(peer_symbols))

    data_service_state = build_data_service_state(company_source, market_cards + popular_cards)
    source_status, source_is_live = build_stock_source_status(company_source, market_cards + popular_cards)
    render_page_header(
        "股票研究工作台",
        "台股 / 美股追蹤 · 技術證據 · 同業脈絡",
        source_status,
        source_is_live,
    )
    render_data_service_notice(data_service_state)
    st.markdown(
        '<div class="notice"><b>免責聲明：</b>本專案僅供資料分析與技術展示，不構成任何投資建議。</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        "市場狀態、熱門標的、技術指標與同業比較。"
    )
    st.caption(f"TWSE 上市公司清單：{company_source}；ESG 法律訴訟資料：{esg_source}")
    render_market_cards(theme, market_cards)
    render_popular_stocks(popular_cards, selected_industry)
    with st.spinner(f"正在載入 {selected_stock_label} 個股詳情..."):
        render_stock_detail(
            selected_yf_symbol,
            theme,
            company_reference,
            peer_cards,
            peer_industry,
            selected_indicators,
        )
    render_peer_comparison(peer_cards, selected_yf_symbol, peer_industry, theme)


def render_snapshot_comparison_page(theme: dict) -> None:
    render_page_header(
        "\u7814\u7a76\u5feb\u7167\u6bd4\u8f03",
        "\u96e2\u7dda\u5dee\u7570\u6aa2\u8996 \u00b7 \u8cc7\u6599\u4f86\u6e90 \u00b7 \u8b49\u64da\u72c0\u614b",
        "SHA-256 \u5b8c\u6574\u6027\u9a57\u8b49",
        status_live=True,
    )
    st.markdown(
        '<div class="notice"><b>\u6bd4\u8f03\u908a\u754c\uff1a</b>'
        "\u50c5\u6bd4\u8f03\u672c\u5c08\u6848\u532f\u51fa\u7684\u540c\u4e00\u80a1\u7968\u5feb\u7167\uff0c"
        "\u4e0a\u50b3\u5167\u5bb9\u4e0d\u6703\u5beb\u5165\u78c1\u789f\u6216\u50b3\u9001\u5230\u5916\u90e8\u670d\u52d9\u3002</div>",
        unsafe_allow_html=True,
    )

    baseline_column, current_column = st.columns(2, gap="large")
    with baseline_column:
        baseline_file = st.file_uploader(
            "\u57fa\u6e96\u5feb\u7167",
            type=["json"],
            key="baseline_snapshot_upload",
            help="\u8f03\u65e9\u7684 Research Snapshot JSON\u3002",
        )
    with current_column:
        current_file = st.file_uploader(
            "\u76ee\u524d\u5feb\u7167",
            type=["json"],
            key="current_snapshot_upload",
            help="\u8f03\u65b0\u7684 Research Snapshot JSON\u3002",
        )
    st.caption(
        "\u6bcf\u500b\u6a94\u6848\u4e0a\u9650 2 MiB\uff1b"
        "\u50c5\u63a5\u53d7 schema 1.0\u3001UTF-8 \u7de8\u78bc\u4e14\u901a\u904e snapshot_id \u9a57\u8b49\u7684 JSON\u3002"
    )

    parsed_snapshots: dict[str, dict] = {}
    upload_errors = False
    for key, label, uploaded_file in (
        ("baseline", "\u57fa\u6e96\u5feb\u7167", baseline_file),
        ("current", "\u76ee\u524d\u5feb\u7167", current_file),
    ):
        if uploaded_file is None:
            continue
        try:
            parsed_snapshots[key] = parse_snapshot_bytes(uploaded_file.getvalue())
        except SnapshotValidationError as exc:
            upload_errors = True
            st.error(f"{label}\uff1a{exc}")

    if upload_errors:
        return
    if len(parsed_snapshots) < 2:
        st.info("\u7b49\u5f85\u5169\u4efd\u5feb\u7167\u4ee5\u5efa\u7acb\u53ef\u9a57\u8b49\u7684\u5dee\u7570\u3002")
        return

    try:
        comparison = compare_snapshots(
            parsed_snapshots["baseline"],
            parsed_snapshots["current"],
        )
    except SnapshotValidationError as exc:
        st.error(str(exc))
        return

    asset = comparison["asset"]
    chronology = comparison["chronology"]
    symbol_label = stock_display_pair(asset["symbol"], asset.get("display_name"))
    elapsed_days = int(chronology["elapsed_days"])
    if chronology["state"] == "reverse":
        st.warning(
            "\u76ee\u524d\u5feb\u7167\u7684\u5e02\u5834\u65e5\u671f\u65e9\u65bc\u57fa\u6e96\u5feb\u7167\uff1b"
            "\u5dee\u7570\u4ecd\u4fdd\u7559\u4e0a\u50b3\u9806\u5e8f\u986f\u793a\u3002"
        )

    st.header("\u6bd4\u8f03\u6458\u8981")
    summary_values = (
        ("\u80a1\u7968", symbol_label),
        (
            "\u671f\u9593",
            f'{comparison["baseline_as_of_date"]} \u2192 {comparison["current_as_of_date"]}',
        ),
        ("\u76f8\u9694\u65e5\u6578", f"{elapsed_days:+d} \u65e5"),
        (
            "\u8b49\u64da\u8b8a\u66f4",
            f'{comparison["changed_evidence_count"]} / {len(comparison["evidence"])}',
        ),
    )
    for column, (label, value) in zip(
        st.columns(4, gap="medium"),
        summary_values,
    ):
        column.markdown(
            f'<div class="info-card">'
            f'<div class="metric-label">{escape_html(label)}</div>'
            f'<div class="metric-value" style="font-size:1.12rem;">{escape_html(value)}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    st.subheader("\u8cc7\u6599\u4f86\u6e90\u8207\u5b8c\u6574\u6027")
    provenance_rows = []
    for row in comparison["provenance"]:
        baseline_value = row.get("baseline")
        current_value = row.get("current")
        if row["field"] == "\u6b77\u53f2\u8cc7\u6599\u6307\u7d0b":
            baseline_text = str(baseline_value or "")
            current_text = str(current_value or "")
            baseline_value = (
                f"{baseline_text[:12]}\u2026{baseline_text[-8:]}"
                if len(baseline_text) > 24
                else baseline_text
            )
            current_value = (
                f"{current_text[:12]}\u2026{current_text[-8:]}"
                if len(current_text) > 24
                else current_text
            )
        provenance_rows.append(
            {
                "\u6b04\u4f4d": row["field"],
                "\u57fa\u6e96\u5feb\u7167": baseline_value,
                "\u76ee\u524d\u5feb\u7167": current_value,
                "\u72c0\u614b": "\u5df2\u8b8a\u66f4" if row["changed"] else "\u76f8\u540c",
            }
        )
    st.dataframe(pd.DataFrame(provenance_rows), width="stretch", hide_index=True)

    warning_groups = (
        ("\u57fa\u6e96\u5feb\u7167", comparison.get("baseline_warnings", [])),
        ("\u76ee\u524d\u5feb\u7167", comparison.get("current_warnings", [])),
    )
    for label, warnings in warning_groups:
        if warnings:
            st.warning(f"{label}\uff1a" + "\uff1b".join(str(item) for item in warnings))

    st.subheader("\u8b49\u64da\u72c0\u614b\u5dee\u7570")
    evidence_rows = []
    for row in comparison["evidence"]:
        baseline_state = RESEARCH_STATE_LABELS.get(
            row["baseline_state"],
            row["baseline_state"],
        )
        current_state = RESEARCH_STATE_LABELS.get(
            row["current_state"],
            row["current_state"],
        )
        baseline_metrics = " \u00b7 ".join(row["baseline_metrics"])
        current_metrics = " \u00b7 ".join(row["current_metrics"])
        evidence_rows.append(
            {
                "\u8b49\u64da": row["label"],
                "\u57fa\u6e96\u72c0\u614b": baseline_state,
                "\u76ee\u524d\u72c0\u614b": current_state,
                "\u57fa\u6e96\u89c0\u5bdf": " | ".join(
                    item
                    for item in (row["baseline_headline"], baseline_metrics)
                    if item
                ),
                "\u76ee\u524d\u89c0\u5bdf": " | ".join(
                    item
                    for item in (row["current_headline"], current_metrics)
                    if item
                ),
                "\u8b8a\u66f4": "\u6709" if row["changed"] else "\u7121",
            }
        )
    st.dataframe(pd.DataFrame(evidence_rows), width="stretch", hide_index=True)

    safe_symbol = re.sub(r"[^A-Za-z0-9._-]+", "_", asset["symbol"])
    st.download_button(
        "\u4e0b\u8f09\u6bd4\u8f03 JSON",
        data=comparison_to_json_bytes(comparison),
        file_name=(
            f"research-comparison-{safe_symbol}-"
            f'{comparison["baseline_as_of_date"]}-'
            f'{comparison["current_as_of_date"]}.json'
        ),
        mime="application/json",
        key="download_snapshot_comparison",
    )


def render_anomaly_page(cfg: dict, theme: dict) -> None:
    render_page_header(
        "異常偵測展示",
        "資料工程 · 特徵工程 · 異常標記流程",
        "本機分析資料",
    )
    st.markdown(
        '<div class="notice"><b>展示定位：</b>本頁獨立呈現原本的異常波動偵測流程，不混入股票分析頁。</div>',
        unsafe_allow_html=True,
    )
    with st.spinner("正在載入異常偵測資料..."):
        data, error = load_dashboard_data(cfg)
    if error:
        st.error(error)
        st.info("API 讀取失敗或尚未產生資料時，系統可切換為 DEMO 示範資料。")
        return

    symbols = get_available_symbols(data)
    if not symbols:
        st.error("目前資料不足，請先產生 DEMO 示範資料。")
        return
    stock_lookup = stock_symbol_lookup(get_stock_universe())

    with st.sidebar:
        selected_symbol = st.selectbox(
            "異常偵測展示代號",
            symbols,
            format_func=lambda symbol: anomaly_symbol_label(symbol, stock_lookup),
        )
        min_date = data["date"].min().date()
        max_date = data["date"].max().date()
        prepare_date_inputs(min_date, max_date)
        start_date = st.date_input("開始日期", min_value=min_date, max_value=max_date, key="filter_start_date")
        end_date = st.date_input("結束日期", min_value=min_date, max_value=max_date, key="filter_end_date")
        if start_date > end_date:
            st.warning("開始日期晚於結束日期，系統已自動交換日期。")
            start_date, end_date = end_date, start_date

    filtered = filter_by_symbol_and_date(data, selected_symbol, start_date, end_date)
    if filtered.empty:
        st.warning("所選股票與日期區間沒有可用資料，請調整日期或改選其他股票。")
        return
    kpis = build_kpis(filtered)

    st.header("展示核心指標")
    st.caption("以下 KPI 用來快速觀察選定股票在區間內的最新狀態、波動程度與異常事件數。")
    cols = st.columns(4)
    cols[0].metric("最新收盤價", kpis["latest_close"])
    cols[1].metric("近期波動率", kpis["recent_volatility"])
    cols[2].metric("異常事件數", kpis["anomaly_count"])
    cols[3].metric("平均成交量", kpis["average_volume"])

    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("股價趨勢與異常事件")
        st.caption("異常標記代表模型判定的異常波動日期，只表示資料行為異常，不代表投資訊號。")
        st.plotly_chart(
            line_with_anomalies(filtered, "close", "股價趨勢與異常事件", "收盤價", theme),
            width="stretch",
            config=PLOTLY_CONFIG,
        )
    with right:
        st.subheader("20 日波動率")
        st.caption("波動率用於觀察價格變動幅度是否擴大或收斂。")
        st.plotly_chart(
            line_with_anomalies(filtered, "volatility_20", "20 日波動率趨勢", "20 日波動率", theme),
            width="stretch",
            config=PLOTLY_CONFIG,
        )

    fx_df = data.drop_duplicates("date").sort_values("date")
    fx_filtered = fx_df[(fx_df["date"] >= pd.Timestamp(start_date)) & (fx_df["date"] <= pd.Timestamp(end_date))]
    fx_fig = go.Figure()
    fx_fig.add_trace(
        go.Scatter(
            x=fx_filtered["date"],
            y=fx_filtered["exchange_rate"],
            mode="lines",
            line=dict(color=theme["success"], width=2.4),
            name="USD/TWD",
        )
    )
    apply_plotly_theme(fx_fig, theme, "匯率趨勢")
    fx_fig.update_layout(height=340)
    fx_fig.update_xaxes(title_text="日期", title_font=dict(color=theme["text"]))
    fx_fig.update_yaxes(title_text="匯率", title_font=dict(color=theme["text"]))
    st.header("匯率趨勢")
    st.caption("匯率資料與股價資料依日期對齊，用於觀察外匯變動與市場波動的關聯。")
    if fx_filtered.empty:
        st.info("所選日期區間沒有匯率資料。")
    else:
        st.plotly_chart(fx_fig, width="stretch", config=PLOTLY_CONFIG)

    with st.expander("查看區間圖表資料"):
        chart_table = filtered[
            ["date", "symbol", "close", "volatility_20", "exchange_rate", "model_anomaly"]
        ].copy()
        chart_table["symbol"] = chart_table["symbol"].map(lambda symbol: anomaly_symbol_label(symbol, stock_lookup))
        chart_table = chart_table.rename(columns=DISPLAY_COLUMN_MAP).sort_values("日期", ascending=False)
        st.dataframe(chart_table.head(500), width="stretch", hide_index=True)

    st.header("異常波動日期列表")
    st.caption("列表顯示模型標記的異常事件，欄位已轉為中文名稱以利閱讀。")
    anomalies = filtered[filtered["model_anomaly"] == 1].sort_values("date", ascending=False)
    visible_columns = ["date", "symbol", "close", "daily_return", "volume_zscore_20", "risk_score_baseline", "anomaly_score"]
    table = anomalies[visible_columns].copy()
    table["symbol"] = table["symbol"].map(lambda symbol: anomaly_symbol_label(symbol, stock_lookup))
    table = table.rename(columns=DISPLAY_COLUMN_MAP)
    if table.empty:
        st.info("目前區間沒有模型標記的異常事件。")
    else:
        st.dataframe(style_anomaly_table(table.head(30), theme), width="stretch", hide_index=True)

    st.markdown(
        """
        <div class="warning-box">
        <b>專案限制：</b>本專案不做價格預測，也不提供買進、賣出或持有建議。
        異常標籤使用 pseudo-label，並非真實市場事件標籤；模型結果僅適合展示資料工程、特徵工程與異常偵測流程。
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    if not require_streamlit():
        return

    cfg = load_config()
    st.set_page_config(page_title="股票分析與追蹤 Dashboard", layout="wide", initial_sidebar_state="collapsed")

    context_theme_type = st.context.theme.get("type") if hasattr(st.context, "theme") else None
    theme_name = resolve_dashboard_theme_name(cfg, context_theme_type)
    theme = get_theme(theme_name)
    validation = validate_theme_contrast(theme)
    if not validation["passed"]:
        fallback_name = "paper_orange" if context_theme_type == "light" else "charcoal_orange"
        theme = get_theme(fallback_name)
    inject_global_css(theme)

    if "active_page" not in st.session_state:
        st.session_state["active_page"] = page_label_from_route(
            st.query_params.get("page", "stocks")
        )
    page_name = st.radio(
        "主功能",
        list(PAGE_ROUTES.values()),
        horizontal=True,
        key="active_page",
        label_visibility="collapsed",
    )
    st.query_params["page"] = route_from_page_label(page_name)

    if page_name != "快照比較":
        with st.sidebar:
            st.header("篩選條件")

    if page_name == "\u80a1\u7968\u5206\u6790":
        render_stock_analysis_page(theme)
    elif page_name == "市場雷達":
        render_market_radar_page(theme)
    elif page_name == "\u5feb\u7167\u6bd4\u8f03":
        render_snapshot_comparison_page(theme)
    else:
        render_anomaly_page(cfg, theme)

    render_product_footer()


if __name__ == "__main__":
    main()
