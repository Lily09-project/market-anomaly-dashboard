from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import math

import pandas as pd

from src.market_api import compute_technical_indicators


MIN_SCREENING_OBSERVATIONS = 60
REQUIRED_HISTORY_COLUMNS = frozenset({"date", "high", "low", "close", "volume"})

SCORING_PROFILES: dict[str, dict[str, Any]] = {
    "balanced": {
        "label": "均衡研究",
        "description": "同時檢視趨勢、動能、量能與波動韌性。",
        "weights": {"trend": 0.30, "momentum": 0.25, "participation": 0.20, "resilience": 0.25},
    },
    "trend": {
        "label": "趨勢優先",
        "description": "提高均線結構權重，適合尋找趨勢較明確的標的。",
        "weights": {"trend": 0.40, "momentum": 0.25, "participation": 0.15, "resilience": 0.20},
    },
    "momentum": {
        "label": "動能量價",
        "description": "提高 RSI 與成交量確認度，聚焦近期市場參與。",
        "weights": {"trend": 0.25, "momentum": 0.35, "participation": 0.25, "resilience": 0.15},
    },
    "defensive": {
        "label": "波動控制",
        "description": "提高波動韌性權重，優先檢視近期走勢較穩定的標的。",
        "weights": {"trend": 0.25, "momentum": 0.20, "participation": 0.15, "resilience": 0.40},
    },
}

FACTOR_LABELS = {
    "trend": "趨勢",
    "momentum": "動能",
    "participation": "量能",
    "resilience": "波動韌性",
}


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _score_label(score: float) -> str:
    if score >= 80:
        return "證據完整"
    if score >= 65:
        return "值得追蹤"
    if score >= 50:
        return "證據分歧"
    return "優先補證"


def _factor_scores(latest: pd.Series) -> dict[str, float] | None:
    values = {
        "close": _finite_float(latest.get("close")),
        "ma20": _finite_float(latest.get("ma20")),
        "ma60": _finite_float(latest.get("ma60")),
        "rsi14": _finite_float(latest.get("rsi14")),
        "volume_ratio": _finite_float(latest.get("volume_ratio_20")),
        "volatility": _finite_float(latest.get("volatility_20")),
    }
    if any(value is None for value in values.values()):
        return None

    close = float(values["close"])
    ma20 = float(values["ma20"])
    ma60 = float(values["ma60"])
    rsi = float(values["rsi14"])
    volume_ratio = float(values["volume_ratio"])
    volatility = float(values["volatility"])

    trend = (50.0 if close >= ma20 else 10.0) + (50.0 if ma20 >= ma60 else 10.0)
    if 50 <= rsi <= 70:
        momentum = 100.0
    elif 40 <= rsi < 50 or 70 < rsi <= 75:
        momentum = 70.0
    else:
        momentum = 35.0

    participation = 100.0 if volume_ratio >= 1.2 else 70.0 if volume_ratio >= 0.8 else 35.0
    resilience = 100.0 if volatility <= 2.0 else 70.0 if volatility <= 3.5 else 35.0
    return {
        "trend": trend,
        "momentum": momentum,
        "participation": participation,
        "resilience": resilience,
    }


def _unavailable_candidate(base: Mapping[str, Any], quality_note: str) -> dict[str, Any]:
    return {
        **base,
        "data_quality": "unavailable",
        "quality_note": quality_note,
        "factor_scores": {},
        "total_score": None,
        "label": "資料不足",
        "ranking_reason": "無法比較",
        "metrics": {},
        "latest_date": None,
    }


def _prepare_history(history: pd.DataFrame) -> pd.DataFrame:
    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for column in ("high", "low", "close", "volume"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=list(REQUIRED_HISTORY_COLUMNS))


def build_market_candidate(
    history: pd.DataFrame,
    metadata: Mapping[str, object],
    source: str,
    profile: str = "balanced",
) -> dict[str, Any]:
    """Build one transparent market-screening result from OHLCV history."""
    selected_profile = profile if profile in SCORING_PROFILES else "balanced"
    symbol = str(metadata.get("symbol", "")).strip()
    display = str(metadata.get("display", "")).strip() or "名稱待確認"
    category = str(metadata.get("category", "")).strip() or "未分類"
    observations = len(history) if isinstance(history, pd.DataFrame) else 0
    coverage = min(1.0, observations / MIN_SCREENING_OBSERVATIONS)
    base = {
        "symbol": symbol,
        "display": display,
        "stock_label": f"{symbol} · {display}",
        "category": category,
        "source": str(source or "unavailable"),
        "profile": selected_profile,
        "observations": observations,
        "coverage": round(coverage, 3),
    }
    if not isinstance(history, pd.DataFrame):
        return _unavailable_candidate(base, "歷史資料格式無效，無法進行比較。")
    missing_columns = sorted(REQUIRED_HISTORY_COLUMNS.difference(history.columns))
    if missing_columns:
        return _unavailable_candidate(
            base,
            f"歷史資料缺少必要欄位：{', '.join(missing_columns)}。",
        )
    duplicate_columns = sorted(
        {
            str(column)
            for column in history.columns[history.columns.duplicated()]
            if column in REQUIRED_HISTORY_COLUMNS
        }
    )
    if duplicate_columns:
        return _unavailable_candidate(
            base,
            f"歷史資料包含重複必要欄位：{', '.join(duplicate_columns)}。",
        )

    history = _prepare_history(history)
    observations = len(history)
    base["observations"] = observations
    base["coverage"] = round(min(1.0, observations / MIN_SCREENING_OBSERVATIONS), 3)
    if observations < MIN_SCREENING_OBSERVATIONS:
        return _unavailable_candidate(
            base,
            f"至少 60 個有效交易日才能穩定計算長期均線與風險，目前只有 {observations} 筆。",
        )

    indicators = compute_technical_indicators(history)
    latest = indicators.iloc[-1]
    factor_scores = _factor_scores(latest)
    if factor_scores is None:
        return _unavailable_candidate(base, "最新一筆技術指標不完整，暫不納入排名。")

    weights = SCORING_PROFILES[selected_profile]["weights"]
    total_score = round(sum(factor_scores[key] * weights[key] for key in factor_scores), 1)
    strongest = sorted(factor_scores, key=lambda key: (-factor_scores[key], key))[:2]
    latest_date = pd.to_datetime(latest.get("date"), errors="coerce")
    metrics = {
        "close": round(float(latest["close"]), 2),
        "rsi14": round(float(latest["rsi14"]), 1),
        "volume_ratio_20": round(float(latest["volume_ratio_20"]), 2),
        "volatility_20": round(float(latest["volatility_20"]), 2),
    }
    return {
        **base,
        "data_quality": "ready",
        "quality_note": f"{observations} 個交易日，四項因子均可計算。",
        "factor_scores": factor_scores,
        "total_score": total_score,
        "label": _score_label(total_score),
        "ranking_reason": "、".join(FACTOR_LABELS[key] for key in strongest) + "證據相對完整",
        "metrics": metrics,
        "latest_date": None if pd.isna(latest_date) else latest_date.date().isoformat(),
    }


def build_market_candidates(
    universe: Iterable[Mapping[str, object]],
    histories: Mapping[str, tuple[pd.DataFrame, str]],
    profile: str = "balanced",
) -> list[dict[str, Any]]:
    """Build screening candidates in the same deterministic order as the universe."""
    candidates = []
    for metadata in universe:
        symbol = str(metadata.get("symbol", "")).strip()
        history, source = histories.get(symbol, (pd.DataFrame(), "unavailable"))
        candidates.append(build_market_candidate(history, metadata, source, profile))
    return candidates


def rank_market_candidates(
    candidates: Iterable[Mapping[str, Any]],
    minimum_score: float = 0,
) -> list[dict[str, Any]]:
    """Return comparable candidates ordered by score with deterministic tie-breaking."""
    candidate_list = [dict(candidate) for candidate in candidates]
    live_candidates = [
        candidate
        for candidate in candidate_list
        if candidate.get("data_quality") == "ready" and candidate.get("source") == "yfinance"
    ]
    comparison_pool = live_candidates or candidate_list

    comparable = []
    for candidate in comparison_pool:
        score = _finite_float(candidate.get("total_score"))
        if candidate.get("data_quality") != "ready" or score is None or score < minimum_score:
            continue
        candidate["total_score"] = score
        comparable.append(candidate)
    comparable.sort(key=lambda item: (-item["total_score"], str(item.get("symbol", ""))))
    return [{**item, "rank": index} for index, item in enumerate(comparable, start=1)]
