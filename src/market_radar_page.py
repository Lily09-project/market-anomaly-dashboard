from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
import html
from urllib.parse import quote

import pandas as pd
import streamlit as st

from src.market_api import get_stock_universe
from src.market_screener import (
    FACTOR_LABELS,
    SCORING_PROFILES,
    build_market_candidates,
    rank_market_candidates,
)
from src.product_state import build_data_service_state


RADAR_POOL_SIZES = (6, 10, 14)
DEFAULT_RADAR_PROFILE = "balanced"
DEFAULT_RADAR_SCORE = 50
DEFAULT_RADAR_POOL_SIZE = 10


def _query_param_value(name: str, default: object) -> object:
    value = st.query_params.get(name, default)
    if isinstance(value, (list, tuple)):
        return value[0] if value else default
    return value


def _query_choice(name: str, options: list[str], default: str) -> str:
    value = str(_query_param_value(name, default)).strip()
    return value if value in options else default


def _query_score() -> int:
    try:
        value = int(str(_query_param_value("min_score", DEFAULT_RADAR_SCORE)))
    except ValueError:
        return DEFAULT_RADAR_SCORE
    return max(0, min(100, value))


def _query_pool_size() -> int:
    try:
        value = int(str(_query_param_value("pool_size", DEFAULT_RADAR_POOL_SIZE)))
    except ValueError:
        return DEFAULT_RADAR_POOL_SIZE
    return value if value in RADAR_POOL_SIZES else DEFAULT_RADAR_POOL_SIZE


def _source_label(source: object) -> str:
    return {"yfinance": "LIVE", "sample": "DEMO"}.get(str(source), str(source or "未知"))


def _industry_options(universe: list[dict[str, str]]) -> list[str]:
    categories = sorted({item.get("category", "").strip() for item in universe if item.get("category", "").strip()})
    return ["全部", *categories]


def _candidate_pool(universe: list[dict[str, str]], industry: str, limit: int) -> list[dict[str, str]]:
    pool = universe if industry == "全部" else [item for item in universe if item.get("category") == industry]
    return pool[:limit]


def _score_markup(candidate: Mapping[str, Any]) -> str:
    factors = candidate.get("factor_scores", {})
    detail_url = f'?page=stocks&amp;symbol={quote(str(candidate["symbol"]), safe=".^_-")}'
    factor_markup = "".join(
        f'<div><span>{html.escape(FACTOR_LABELS[key])}</span><strong>{float(factors.get(key, 0)):.0f}</strong></div>'
        for key in FACTOR_LABELS
    )
    return f"""
        <article class="radar-card">
            <div class="radar-rank">#{int(candidate['rank'])}</div>
            <div class="radar-card-main">
                <div class="radar-stock">{html.escape(str(candidate['stock_label']))}</div>
                <div class="radar-meta">{html.escape(str(candidate['category']))} · {html.escape(_source_label(candidate['source']))} · 截至 {html.escape(str(candidate['latest_date']))}</div>
                <div class="radar-reason">{html.escape(str(candidate['ranking_reason']))}</div>
                <a class="radar-link" href="{detail_url}" target="_self">查看個股分析</a>
            </div>
            <div class="radar-score"><strong>{float(candidate['total_score']):.1f}</strong><span>{html.escape(str(candidate['label']))}</span></div>
            <div class="radar-factors">{factor_markup}</div>
        </article>
    """


def _ranking_table(candidates: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for candidate in candidates:
        factors = candidate["factor_scores"]
        metrics = candidate["metrics"]
        rows.append(
            {
                "排序": candidate["rank"],
                "股票": candidate["stock_label"],
                "產業": candidate["category"],
                "總分": candidate["total_score"],
                "趨勢": factors["trend"],
                "動能": factors["momentum"],
                "量能": factors["participation"],
                "波動韌性": factors["resilience"],
                "RSI(14)": metrics["rsi14"],
                "量比": metrics["volume_ratio_20"],
                "20 日波動率": f'{metrics["volatility_20"]:.2f}%',
                "資料來源": _source_label(candidate["source"]),
                "資料日": candidate["latest_date"],
            }
        )
    return pd.DataFrame(rows)


def _render_radar_css() -> None:
    st.markdown(
        """
        <style>
        .radar-method-bar {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
            padding: 1rem 1.1rem;
            margin: 1rem 0 1.25rem;
            border: 1px solid var(--ui-border);
            border-left: 4px solid var(--ui-accent);
            border-radius: var(--ui-radius);
            background: var(--ui-surface);
        }
        .radar-method-bar strong { display: block; font-size: 1.05rem; }
        .radar-method-bar span { color: var(--ui-muted); font-size: 0.92rem; }
        .radar-list { display: grid; gap: 0.75rem; margin: 0.75rem 0 1.5rem; }
        .radar-card {
            display: grid;
            grid-template-columns: 3rem minmax(14rem, 1.4fr) 6.5rem minmax(18rem, 1fr);
            gap: 1rem;
            align-items: center;
            min-height: 108px;
            padding: 1rem 1.1rem;
            border: 1px solid var(--ui-border);
            border-radius: var(--ui-radius);
            background: var(--ui-card);
        }
        .radar-rank { color: var(--ui-accent); font: 800 1rem/1 var(--ui-data-font); }
        .radar-stock { font-size: 1.08rem; font-weight: 800; overflow-wrap: anywhere; }
        .radar-meta, .radar-reason { color: var(--ui-muted); font-size: 0.88rem; margin-top: 0.2rem; }
        .radar-link { display: inline-block; margin-top: 0.35rem; color: var(--ui-accent) !important; font-size: 0.86rem; font-weight: 750; text-decoration: none; }
        .radar-link:hover, .radar-link:focus-visible { text-decoration: underline; }
        .radar-score { text-align: right; border-right: 1px solid var(--ui-border); padding-right: 1rem; }
        .radar-score strong { display: block; color: var(--ui-accent); font: 850 1.75rem/1 var(--ui-data-font); }
        .radar-score span { color: var(--ui-muted); font-size: 0.82rem; }
        .radar-factors { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.4rem 1rem; }
        .radar-factors div { display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.85rem; }
        .radar-factors span { color: var(--ui-muted); }
        .radar-factors strong { font-family: var(--ui-data-font); }
        @media (max-width: 900px) {
            .radar-card { grid-template-columns: 2.5rem 1fr 5.5rem; }
            .radar-factors { grid-column: 2 / -1; }
        }
        @media (max-width: 600px) {
            .radar-method-bar { display: block; }
            .radar-card { grid-template-columns: 2rem minmax(0, 1fr); padding: 0.9rem; }
            .radar-score { grid-column: 2; text-align: left; border-right: 0; padding-right: 0; }
            .radar-factors { grid-column: 1 / -1; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_market_radar(
    load_twse_sources: Callable[[], tuple[pd.DataFrame, str, pd.DataFrame, str]],
    load_histories: Callable[[tuple[str, ...]], dict[str, tuple[pd.DataFrame, str]]],
    render_page_header: Callable[[str, str, str, bool], None],
    render_data_notice: Callable[[dict[str, Any]], None],
) -> None:
    """Render a transparent, source-aware ranking of the selected market universe."""
    with st.spinner("正在載入公司清單與市場資料..."):
        company_profiles, company_source, _, _ = load_twse_sources()
    universe = get_stock_universe(company_profiles)

    industry_options = _industry_options(universe)
    if "radar_industry" not in st.session_state:
        st.session_state["radar_industry"] = _query_choice("industry", industry_options, "全部")
    if "radar_profile" not in st.session_state:
        st.session_state["radar_profile"] = _query_choice(
            "profile",
            list(SCORING_PROFILES),
            DEFAULT_RADAR_PROFILE,
        )
    if "radar_minimum_score" not in st.session_state:
        st.session_state["radar_minimum_score"] = _query_score()
    if "radar_pool_size" not in st.session_state:
        st.session_state["radar_pool_size"] = _query_pool_size()

    with st.sidebar:
        industry = st.selectbox("產業篩選", industry_options, key="radar_industry")
        profile = st.selectbox(
            "研究配置",
            list(SCORING_PROFILES),
            format_func=lambda key: SCORING_PROFILES[key]["label"],
            key="radar_profile",
        )
        minimum_score = st.slider(
            "最低證據分數",
            0,
            100,
            step=5,
            key="radar_minimum_score",
        )
        pool_size = st.selectbox(
            "候選池規模",
            RADAR_POOL_SIZES,
            key="radar_pool_size",
        )
        st.caption("從熱門代表清單建立候選池；提高規模會增加行情下載時間。")

    st.query_params["industry"] = industry
    st.query_params["profile"] = profile
    st.query_params["min_score"] = str(minimum_score)
    st.query_params["pool_size"] = str(pool_size)

    pool = _candidate_pool(universe, industry, pool_size)
    symbols = tuple(item["symbol"] for item in pool)
    with st.spinner(f"正在計算 {len(symbols)} 檔股票的四項證據..."):
        histories = load_histories(symbols)
        candidates = build_market_candidates(pool, histories, profile)

    state = build_data_service_state(company_source, candidates)
    status = state["label"] + (f' · 截至 {state["as_of_date"]}' if state.get("as_of_date") else "")
    render_page_header("市場雷達", "可解釋篩選 · 研究優先序 · 資料品質", status, bool(state["is_live"]))
    render_data_notice(state)
    _render_radar_css()

    profile_config = SCORING_PROFILES[profile]
    weights = profile_config["weights"]
    weight_text = " · ".join(f"{FACTOR_LABELS[key]} {weight * 100:.0f}%" for key, weight in weights.items())
    st.markdown(
        f"""
        <div class="radar-method-bar">
            <div><strong>研究優先序 · {html.escape(profile_config['label'])}</strong><span>{html.escape(profile_config['description'])}</span></div>
            <span>{html.escape(weight_text)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("分數用於整理研究順序，不預測報酬，也不構成買進、賣出或持有建議。")
    st.caption("同批資料同時含 LIVE 與 DEMO 時，排名只比較 LIVE；全數離線時才以 DEMO 保留操作體驗。")

    ranked = rank_market_candidates(candidates, minimum_score)
    ready_count = sum(candidate["data_quality"] == "ready" for candidate in candidates)
    live_count = sum(candidate["source"] == "yfinance" for candidate in candidates)
    metrics = st.columns(4)
    metrics[0].metric("分析範圍", f"{len(candidates)} 檔")
    metrics[1].metric("可比較", f"{ready_count} 檔")
    metrics[2].metric("通過門檻", f"{len(ranked)} 檔")
    metrics[3].metric("LIVE 覆蓋", f"{live_count}/{len(candidates)}" if candidates else "0/0")

    st.header("排序結果")
    if not ranked:
        st.warning("目前沒有標的通過此分數門檻。可降低門檻，或調整產業與研究配置。")
        return

    card_markup = "".join(_score_markup(candidate).strip() for candidate in ranked[:3])
    st.markdown(f'<div class="radar-list">{card_markup}</div>', unsafe_allow_html=True)
    st.dataframe(_ranking_table(ranked), width="stretch", hide_index=True)

    with st.expander("評分方法與限制"):
        st.markdown(
            """
            - **趨勢**：比較收盤價、MA20 與 MA60 的相對位置。
            - **動能**：RSI 50–70 視為較完整的正向動能證據，過熱或偏弱會降低分數。
            - **量能**：比較最新成交量與 20 日均量，判斷價格變化是否有市場參與。
            - **波動韌性**：20 日報酬波動越低，分數越高；這不是低風險保證。
            - 至少需要 60 個交易日，缺漏或非有限指標不納入排名。所有分數均可由原始 OHLCV 重算。
            """
        )
