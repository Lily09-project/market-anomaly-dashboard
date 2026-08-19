from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from src.market_api import compute_technical_indicators
from src.research_coherence import build_evidence_coherence
from src.research_methodology import build_methodology_manifest
from src.research_readiness import build_research_readiness


EVIDENCE_ORDER = ("trend", "momentum", "participation", "risk")
EVIDENCE_LABELS = {
    "trend": "趨勢",
    "momentum": "動能",
    "participation": "量能",
    "risk": "風險",
}
QUALITY_COLUMNS = ("open", "high", "low", "close", "volume")
CORE_PRICE_COLUMNS = ("open", "high", "low", "close")
MIN_TECHNICAL_OBSERVATIONS = 20


def _finite_float(value: object) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if np.isfinite(numeric) else None


def _format_percent(value: float | None) -> str:
    return "資料不足" if value is None else f"{value:+.2f}%"


def _format_number(value: float | None, digits: int = 2) -> str:
    return "資料不足" if value is None else f"{value:,.{digits}f}"


def _normalize_history(history: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    if not isinstance(history, pd.DataFrame):
        return pd.DataFrame(columns=["date", *QUALITY_COLUMNS]), ["date", *CORE_PRICE_COLUMNS]

    data = history.copy()
    missing_columns = [column for column in ("date", *CORE_PRICE_COLUMNS) if column not in data]
    if missing_columns:
        return pd.DataFrame(columns=["date", *QUALITY_COLUMNS]), missing_columns

    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for column in QUALITY_COLUMNS:
        if column in data:
            data[column] = pd.to_numeric(data[column], errors="coerce")
        else:
            data[column] = np.nan
    data = data.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return data, missing_columns


def _source_warning(source: str) -> str | None:
    if source == "sample":
        return "目前使用 DEMO 示範資料，所有價格與漲跌均非真實行情。"
    if source in {"", "unavailable", "unknown"}:
        return "資料來源目前不可確認，請先檢查來源狀態。"
    if source != "yfinance":
        return f"目前資料來源為 {source}，請確認更新頻率與適用範圍。"
    return None


def _build_data_quality(data: pd.DataFrame, source: str, missing_columns: list[str]) -> dict[str, Any]:
    observations = int(len(data))
    expected_cells = observations * len(QUALITY_COLUMNS)
    available_cells = sum(int(data[column].notna().sum()) for column in QUALITY_COLUMNS if column in data)
    coverage_pct = (available_cells / expected_cells * 100) if expected_cells else 0.0
    latest_date = ""
    if observations:
        latest_date = pd.Timestamp(data.iloc[-1]["date"]).date().isoformat()

    warnings: list[str] = []
    source_warning = _source_warning(source)
    if source_warning:
        warnings.append(source_warning)
    if missing_columns:
        warnings.append(f"缺少必要價格欄位：{', '.join(missing_columns)}。")
    if observations < MIN_TECHNICAL_OBSERVATIONS:
        warnings.append(f"僅有 {observations} 筆有效收盤價，少於技術判讀所需的 {MIN_TECHNICAL_OBSERVATIONS} 筆。")
    missing_core = [column for column in CORE_PRICE_COLUMNS if column not in data or data[column].isna().any()]
    if missing_core:
        warnings.append(f"OHLC 欄位不完整：{', '.join(missing_core)}。")
    if "volume" not in data or data["volume"].isna().all():
        warnings.append("成交量欄位不足，量能證據無法判讀。")

    ready = source == "yfinance" and observations >= MIN_TECHNICAL_OBSERVATIONS and not missing_core
    return {
        "state": "ready" if ready else "caution",
        "source": source or "unavailable",
        "latest_date": latest_date,
        "observations": observations,
        "coverage_pct": round(float(coverage_pct), 1),
        "warnings": warnings,
    }


def _unavailable_evidence(identifier: str, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": EVIDENCE_LABELS[identifier],
        "state": "unavailable",
        "headline": "資料不足",
        "detail": detail,
        "metrics": [],
    }


def _trend_evidence(latest: pd.Series) -> dict[str, Any]:
    close = _finite_float(latest.get("close"))
    ma5 = _finite_float(latest.get("ma5"))
    ma20 = _finite_float(latest.get("ma20"))
    ma60 = _finite_float(latest.get("ma60"))
    if None in (close, ma5, ma20, ma60):
        return _unavailable_evidence("trend", "均線資料不足，無法判讀趨勢。")
    if close >= ma5 >= ma20 >= ma60:
        state, headline, detail = "positive", "均線呈多頭排列", "收盤價位於短、中、長期均線之上。"
    elif close >= ma20 >= ma60:
        state, headline, detail = "positive", "價格守住中期趨勢", "收盤價與 MA20 均高於 MA60。"
    elif close >= ma60:
        state, headline, detail = "neutral", "趨勢仍待確認", "收盤價位於 MA60 上方，但短中期均線未完全一致。"
    else:
        state, headline, detail = "risk", "價格低於主要均線", "收盤價未站回長期均線，趨勢證據偏弱。"
    return {
        "id": "trend",
        "label": EVIDENCE_LABELS["trend"],
        "state": state,
        "headline": headline,
        "detail": detail,
        "metrics": [f"收盤 {_format_number(close)}", f"MA5 {_format_number(ma5)}", f"MA20 {_format_number(ma20)}"],
    }


def _momentum_evidence(latest: pd.Series) -> dict[str, Any]:
    rsi14 = _finite_float(latest.get("rsi14"))
    if rsi14 is None:
        return _unavailable_evidence("momentum", "RSI 資料不足，無法判讀動能。")
    if rsi14 >= 70:
        state, headline, detail = "risk", "動能偏熱", "RSI 高於 70，短線強勢但波動風險提高。"
    elif rsi14 >= 55:
        state, headline, detail = "positive", "動能偏強", "RSI 位於 55 至 70 的偏強區間。"
    elif rsi14 >= 45:
        state, headline, detail = "neutral", "動能中性", "RSI 接近中性區，沒有明確方向訊號。"
    else:
        state, headline, detail = "risk", "動能偏弱", "RSI 低於 45，短線買盤力道較弱。"
    return {
        "id": "momentum",
        "label": EVIDENCE_LABELS["momentum"],
        "state": state,
        "headline": headline,
        "detail": detail,
        "metrics": [f"RSI(14) {rsi14:.1f}"],
    }


def _participation_evidence(latest: pd.Series) -> dict[str, Any]:
    volume_ratio = _finite_float(latest.get("volume_ratio_20"))
    if volume_ratio is None:
        return _unavailable_evidence("participation", "成交量或 20 日均量不足，無法判讀量能。")
    if volume_ratio >= 1.5:
        state, headline, detail = "positive", "成交量明顯放大", "成交量高於 20 日均量，市場參與度提高。"
    elif volume_ratio >= 0.8:
        state, headline, detail = "neutral", "成交量接近均值", "成交量落在近期可比較範圍。"
    else:
        state, headline, detail = "risk", "成交量低於均值", "市場參與度偏低，價格變化的確認度較弱。"
    return {
        "id": "participation",
        "label": EVIDENCE_LABELS["participation"],
        "state": state,
        "headline": headline,
        "detail": detail,
        "metrics": [f"量能倍率 {volume_ratio:.2f}x"],
    }


def _risk_evidence(latest: pd.Series) -> dict[str, Any]:
    volatility = _finite_float(latest.get("volatility_20"))
    if volatility is None:
        return _unavailable_evidence("risk", "波動率資料不足，無法判讀風險。")
    if volatility >= 3.5:
        state, headline, detail = "risk", "近期波動偏高", "20 日波動率高於 3.5%，近期價格變化較大。"
    elif volatility >= 2.0:
        state, headline, detail = "neutral", "近期波動中性", "20 日波動率處於可觀察區間。"
    else:
        state, headline, detail = "positive", "近期波動較低", "20 日波動率低於 2%，價格變化相對平穩。"
    return {
        "id": "risk",
        "label": EVIDENCE_LABELS["risk"],
        "state": state,
        "headline": headline,
        "detail": detail,
        "metrics": [f"20 日波動率 {volatility:.2f}%"],
    }


def _build_evidence(indicators: pd.DataFrame) -> list[dict[str, Any]]:
    if indicators.empty:
        return [_unavailable_evidence(identifier, "技術資料不足。") for identifier in EVIDENCE_ORDER]
    latest = indicators.iloc[-1]
    return [_trend_evidence(latest), _momentum_evidence(latest), _participation_evidence(latest), _risk_evidence(latest)]


def _empty_changes() -> dict[str, list[dict[str, str]]]:
    return {
        "rows": [
            {"項目": "收盤價", "本期變化": "資料不足"},
            {"項目": "RSI(14)", "本期變化": "資料不足"},
            {"項目": "MA20 距離", "本期變化": "資料不足"},
            {"項目": "20 日波動率", "本期變化": "資料不足"},
        ]
    }


def _build_changes(indicators: pd.DataFrame) -> dict[str, list[dict[str, str]]]:
    if len(indicators) < 2:
        return _empty_changes()
    latest = indicators.iloc[-1]
    previous = indicators.iloc[-2]
    close = _finite_float(latest.get("close"))
    previous_close = _finite_float(previous.get("close"))
    price_change = ((close / previous_close - 1) * 100) if close is not None and previous_close not in (None, 0) else None
    rsi_change = _finite_float(latest.get("rsi14"))
    previous_rsi = _finite_float(previous.get("rsi14"))
    rsi_delta = rsi_change - previous_rsi if rsi_change is not None and previous_rsi is not None else None
    ma20 = _finite_float(latest.get("ma20"))
    previous_ma20 = _finite_float(previous.get("ma20"))
    ma20_distance = ((close / ma20 - 1) * 100) if close is not None and ma20 not in (None, 0) else None
    previous_distance = ((previous_close / previous_ma20 - 1) * 100) if previous_close is not None and previous_ma20 not in (None, 0) else None
    volatility = _finite_float(latest.get("volatility_20"))
    previous_volatility = _finite_float(previous.get("volatility_20"))
    volatility_delta = volatility - previous_volatility if volatility is not None and previous_volatility is not None else None
    return {
        "rows": [
            {"項目": "收盤價", "本期變化": _format_percent(price_change)},
            {"項目": "RSI(14)", "本期變化": "資料不足" if rsi_delta is None else f"{rsi_delta:+.1f} 點"},
            {"項目": "MA20 距離", "本期變化": _format_percent(ma20_distance) if ma20_distance is not None else "資料不足"},
            {"項目": "20 日波動率", "本期變化": "資料不足" if volatility_delta is None else f"{volatility_delta:+.2f} 個百分點"},
        ]
    }


def _range_position(card: Mapping[str, Any]) -> float | None:
    latest = _finite_float(card.get("latest_close"))
    high = _finite_float(card.get("high_52w"))
    low = _finite_float(card.get("low_52w"))
    if latest is None or high is None or low is None or high <= low:
        return None
    return max(0.0, min(100.0, (latest - low) / (high - low) * 100))


def _volume_ratio(card: Mapping[str, Any]) -> float | None:
    volume = _finite_float(card.get("volume"))
    average = _finite_float(card.get("avg_volume"))
    if volume is None or average in (None, 0):
        return None
    return volume / average


def _rank_metric(values: list[tuple[str, float]], selected_symbol: str) -> dict[str, int] | None:
    if len(values) < 2:
        return None
    ordered = sorted(values, key=lambda item: item[1], reverse=True)
    for index, (symbol, _) in enumerate(ordered, start=1):
        if symbol == selected_symbol:
            return {"rank": index, "total": len(ordered)}
    return None


def _build_peer_context(peer_cards: Iterable[Mapping[str, Any]], industry: str) -> dict[str, Any]:
    cards = [dict(card) for card in peer_cards if isinstance(card, Mapping) and str(card.get("symbol", "")).strip()]
    selected_symbol = str(cards[0].get("symbol", "")) if cards else ""
    metrics = {
        "daily_change": [(str(card["symbol"]), value) for card in cards if (value := _finite_float(card.get("change_pct"))) is not None],
        "range_position": [(str(card["symbol"]), value) for card in cards if (value := _range_position(card)) is not None],
        "volume_ratio": [(str(card["symbol"]), value) for card in cards if (value := _volume_ratio(card)) is not None],
    }
    ranks = {name: rank for name, values in metrics.items() if (rank := _rank_metric(values, selected_symbol)) is not None}
    if not ranks:
        return {
            "state": "unavailable",
            "industry": industry or "同業",
            "sample_size": len(cards),
            "ranks": {},
            "summary": "資料不足以比較同業脈絡。",
            "rows": [],
        }

    label_lookup = {
        "daily_change": "當日漲跌",
        "range_position": "52 週位置",
        "volume_ratio": "量能倍率",
    }
    value_lookup = {
        "daily_change": lambda value: _format_percent(value),
        "range_position": lambda value: _format_percent(value),
        "volume_ratio": lambda value: f"{value:.2f}x",
    }
    rows = []
    for name, rank in ranks.items():
        selected_value = next((value for symbol, value in metrics[name] if symbol == selected_symbol), None)
        rows.append(
            {
                "比較項目": label_lookup[name],
                "目前值": value_lookup[name](selected_value),
                "同業排名": f"{rank['rank']} / {rank['total']}",
            }
        )
    sample_size = max(rank["total"] for rank in ranks.values())
    return {
        "state": "ready",
        "industry": industry or "同業",
        "sample_size": sample_size,
        "ranks": ranks,
        "summary": f"{industry or '同業'}：以 {sample_size} 檔可比較標的呈現相對位置。",
        "rows": rows,
    }


def build_research_brief(
    history: pd.DataFrame,
    source: str,
    peer_cards: Iterable[Mapping[str, Any]] | None = None,
    industry: str = "",
    reference_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Build display-ready research evidence without network or UI dependencies."""
    data, missing_columns = _normalize_history(history)
    quality = _build_data_quality(data, source, missing_columns)
    if len(data) < MIN_TECHNICAL_OBSERVATIONS:
        evidence = [_unavailable_evidence(identifier, "至少需要 20 筆有效收盤價才能判讀。") for identifier in EVIDENCE_ORDER]
        changes = _empty_changes()
    else:
        indicators = compute_technical_indicators(data)
        evidence = _build_evidence(indicators)
        changes = _build_changes(indicators)
    return {
        "data_quality": quality,
        "readiness": build_research_readiness(quality, reference_date),
        "coherence": build_evidence_coherence(evidence),
        "methodology": build_methodology_manifest(),
        "evidence": evidence,
        "changes": changes,
        "peer_context": _build_peer_context(peer_cards or [], industry),
    }