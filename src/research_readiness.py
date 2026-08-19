from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from typing import Any


DIMENSION_MAX_SCORES = {
    "provenance": 30,
    "freshness": 25,
    "coverage": 25,
    "depth": 20,
}


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _bounded_number(value: object, lower: float, upper: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return lower
    return max(lower, min(upper, numeric))


def _dimension(identifier: str, label: str, score: int, detail: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "score": score,
        "max_score": DIMENSION_MAX_SCORES[identifier],
        "detail": detail,
    }


def build_research_readiness(
    data_quality: Mapping[str, Any],
    reference_date: date | datetime | str | None = None,
) -> dict[str, Any]:
    """Convert data provenance and completeness into a transparent readiness gate."""
    current_date = _as_date(reference_date) or datetime.now(timezone.utc).date()
    source = str(data_quality.get("source", "unavailable") or "unavailable").strip().lower()
    observations = max(0, int(data_quality.get("observations", 0) or 0))
    coverage_pct = _bounded_number(data_quality.get("coverage_pct", 0.0), 0.0, 100.0)
    latest_date = _as_date(data_quality.get("latest_date"))

    if source == "yfinance":
        provenance_score = 30
        provenance_detail = "yfinance 行情來源可追溯。"
    elif source == "sample":
        provenance_score = 8
        provenance_detail = "DEMO 示範資料，不代表真實行情。"
    elif source not in {"", "unknown", "unavailable"}:
        provenance_score = 15
        provenance_detail = f"來源為 {source}，需人工確認更新規則。"
    else:
        provenance_score = 0
        provenance_detail = "資料來源無法確認。"

    age_days: int | None = None
    if latest_date is None:
        freshness_score = 0
        freshness_detail = "沒有可驗證的最新資料日期。"
    else:
        age_days = max(0, (current_date - latest_date).days)
        if age_days <= 3:
            freshness_score = 25
            freshness_detail = f"資料日期 {latest_date.isoformat()}，距參考日 {age_days} 天。"
        elif age_days <= 7:
            freshness_score = 18
            freshness_detail = f"資料已間隔 {age_days} 天，需確認交易日與供應商延遲。"
        elif age_days <= 14:
            freshness_score = 8
            freshness_detail = f"資料已間隔 {age_days} 天，時效性偏低。"
        else:
            freshness_score = 0
            freshness_detail = f"資料已間隔 {age_days} 天，不應直接解讀近期訊號。"

    coverage_score = round(coverage_pct / 100 * DIMENSION_MAX_SCORES["coverage"])
    coverage_detail = f"OHLCV 欄位覆蓋率 {coverage_pct:.1f}%。"
    depth_score = round(min(observations, 60) / 60 * DIMENSION_MAX_SCORES["depth"])
    depth_detail = f"{observations} 筆有效觀測；60 筆可完整支援長期均線。"

    dimensions = [
        _dimension("provenance", "資料來源", provenance_score, provenance_detail),
        _dimension("freshness", "更新時效", freshness_score, freshness_detail),
        _dimension("coverage", "欄位完整", coverage_score, coverage_detail),
        _dimension("depth", "樣本深度", depth_score, depth_detail),
    ]
    score = sum(item["score"] for item in dimensions)

    if source != "yfinance":
        score = min(score, 59)
    if latest_date is None or (age_days is not None and age_days > 14):
        score = min(score, 59)
    elif age_days is not None and age_days > 7:
        score = min(score, 79)
    if observations < 20 or coverage_pct < 80:
        score = min(score, 49)

    actions: list[str] = []
    if source != "yfinance":
        actions.append("重新連線 yfinance 後再解讀價格與漲跌。")
    if latest_date is None:
        actions.append("取得可驗證的資料日期，確認目前研究期間。")
    elif age_days is not None and age_days > 3:
        actions.append(f"確認資料日期 {latest_date.isoformat()} 是否符合目前交易日與供應商延遲。")
    if coverage_pct < 95:
        actions.append("檢查 OHLCV 缺值與欄位正規化，再判讀技術證據。")
    if observations < 60:
        actions.append("累積至少 60 筆有效觀測，完整支援 MA60 與風險比較。")

    if score >= 80:
        level = "ready"
        label = "資料條件完整"
        summary = "來源、更新時間、欄位覆蓋與樣本深度符合技術研究門檻。"
    elif score >= 60:
        level = "review"
        label = "可研究，需覆核"
        summary = "核心資料可用，但至少一項品質條件需要人工確認。"
    else:
        level = "limited"
        label = "資料條件受限"
        summary = "目前資料條件不足，請先完成修正項目再解讀技術證據。"

    if not actions:
        actions.append("資料條件已符合門檻；仍需依頁面證據逐項判讀。")

    return {
        "score": int(score),
        "level": level,
        "label": label,
        "summary": summary,
        "dimensions": dimensions,
        "actions": actions,
        "reference_date": current_date.isoformat(),
        "latest_date": latest_date.isoformat() if latest_date else "",
        "age_days": age_days,
    }