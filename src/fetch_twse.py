"""Fetch the latest TWSE OpenAPI after-hours snapshot for the tracked symbols.

The OpenAPI publishes only the most recent trading day (and the current month
for market totals), so this is a supplementary snapshot, not price history.
FinMind remains the analysis source; TWSE closes are used to cross-check it.
Failures never block the price release: the export then reports the snapshot
as unavailable instead of inventing values.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

try:
    import requests
except Exception:
    requests = None

from src.request_policy import RequestBudget, request_with_retry, validate_response_origin, validate_upstream_url
from src.utils import ensure_parent, load_config, normalize_http_timeout, project_path, read_http_response_bytes, safe_exception_message, write_json

BASE_URL = "https://openapi.twse.com.tw/v1/"
API_HOSTS = {"openapi.twse.com.tw"}
ENDPOINTS = {
    "daily": "exchangeReport/STOCK_DAY_ALL",
    "valuation": "exchangeReport/BWIBBU_ALL",
    "margin": "exchangeReport/MI_MARGN",
    "market": "exchangeReport/FMTQIK",
}
SNAPSHOT_FILE = "twse_snapshot.json"
ROC_DATE_PATTERN = re.compile(r"^(\d{3})(\d{2})(\d{2})$")
NUMBER_PATTERN = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def roc_to_iso(value: Any) -> str:
    """TWSE dates are ROC calendar strings such as 1151029 (2026-10-29)."""
    match = ROC_DATE_PATTERN.fullmatch(str(value).strip())
    if not match:
        raise ValueError("TWSE returned an invalid ROC date.")
    year, month, day = (int(part) for part in match.groups())
    return date(year + 1911, month, day).isoformat()


def parse_number(value: Any, *, blank: float | None = None) -> float | None:
    """Parse a TWSE numeric string; blank means "not applicable" unless told otherwise."""
    text = str(value if value is not None else "").replace(",", "").strip()
    if text in ("", "-", "--"):
        return blank
    if not NUMBER_PATTERN.fullmatch(text):
        raise ValueError("TWSE returned a non-numeric field.")
    number = float(text)
    if not math.isfinite(number):
        raise ValueError("TWSE returned a non-finite number.")
    return number


def _rows(payload: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list) or not payload or not all(isinstance(row, dict) for row in payload):
        raise ValueError(f"TWSE {name} returned no records.")
    return payload


def _by_code(rows: list[dict[str, Any]], key: str, symbols: list[str], name: str, *, required: bool) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get(key, "")).strip()
        if code in symbols:
            if code in found:
                raise ValueError(f"TWSE {name} returned duplicate rows for {code}.")
            found[code] = row
    missing = [s for s in symbols if s not in found]
    if required and missing:
        raise ValueError(f"TWSE {name} is missing {', '.join(missing)}.")
    return found


def normalize_twse_payloads(payloads: dict[str, Any], symbols: list[str]) -> dict[str, Any]:
    """Validate the four OpenAPI responses and keep only the tracked symbols."""
    daily_rows = _by_code(_rows(payloads["daily"], "daily"), "Code", symbols, "daily", required=True)
    trade_dates = {roc_to_iso(row.get("Date")) for row in daily_rows.values()}
    if len(trade_dates) != 1:
        raise ValueError("TWSE daily rows do not share one trading date.")
    trade_date = trade_dates.pop()
    daily = {}
    for symbol, row in daily_rows.items():
        close = parse_number(row.get("ClosingPrice"))  # blank: suspended or no trade today
        if close is not None and close <= 0:
            raise ValueError(f"TWSE daily close for {symbol} is not positive.")
        daily[symbol] = {
            "close": close,
            "change": parse_number(row.get("Change"), blank=0.0),
            "volume_shares": parse_number(row.get("TradeVolume"), blank=0.0),
            "value_twd": parse_number(row.get("TradeValue"), blank=0.0),
        }

    # ETFs such as 0050 have no P/E, yield or P/B row; that is not an error.
    valuation_rows = _by_code(_rows(payloads["valuation"], "valuation"), "Code", symbols, "valuation", required=False)
    if any(roc_to_iso(row.get("Date")) != trade_date for row in valuation_rows.values()):
        valuation_rows = {}  # a lagging valuation file is dropped, not shown under today's date
    valuation: dict[str, Any] = {}
    for symbol, row in valuation_rows.items():
        valuation[symbol] = {
            "pe": parse_number(row.get("PEratio")),
            "dividend_yield_pct": parse_number(row.get("DividendYield")),
            "pb": parse_number(row.get("PBratio")),
        }

    margin_rows = _by_code(_rows(payloads["margin"], "margin"), "股票代號", symbols, "margin", required=True)
    margin = {
        symbol: {
            "margin_balance": parse_number(row.get("融資今日餘額"), blank=0.0),
            "margin_previous": parse_number(row.get("融資前日餘額"), blank=0.0),
            "short_balance": parse_number(row.get("融券今日餘額"), blank=0.0),
            "short_previous": parse_number(row.get("融券前日餘額"), blank=0.0),
        }
        for symbol, row in margin_rows.items()
    }

    market = []
    for row in _rows(payloads["market"], "market"):
        taiex = parse_number(row.get("TAIEX"))
        if taiex is None or taiex <= 0:
            raise ValueError("TWSE market totals are missing TAIEX.")
        market.append(
            {
                "date": roc_to_iso(row.get("Date")),
                "taiex": taiex,
                "change": parse_number(row.get("Change"), blank=0.0),
                "value_twd": parse_number(row.get("TradeValue"), blank=0.0),
            }
        )
    market.sort(key=lambda item: item["date"])
    if len({item["date"] for item in market}) != len(market):
        raise ValueError("TWSE market totals contain duplicate dates.")
    if market and market[-1]["date"] != trade_date:
        market = []  # the month series lags the daily quotes; omit it rather than mislabel it
    return {"trade_date": trade_date, "daily": daily, "valuation": valuation, "margin": margin, "market": market}


MARKET_COLUMNS = ("code", "name", "close", "change", "change_pct", "value_twd", "pe", "dividend_yield_pct", "pb", "margin_balance", "margin_change")


def normalize_market_wide(payloads: dict[str, Any], trade_date: str) -> list[list[Any]]:
    """Every listed security for the trade date, as compact rows in MARKET_COLUMNS order."""
    valuation = {str(r.get("Code", "")).strip(): r for r in _rows(payloads["valuation"], "valuation")}
    if any(roc_to_iso(r.get("Date")) != trade_date for r in valuation.values()):
        valuation = {}
    margin = {str(r.get("股票代號", "")).strip(): r for r in _rows(payloads["margin"], "margin")}
    rows: list[list[Any]] = []
    seen: set[str] = set()
    daily = _rows(payloads["daily"], "daily")
    skipped = 0
    for row in daily:
        code = str(row.get("Code", "")).strip()
        name = str(row.get("Name", "")).strip()
        if not code or not name or code in seen:
            continue
        if roc_to_iso(row.get("Date")) != trade_date:
            raise ValueError("TWSE daily rows do not share one trading date.")
        seen.add(code)
        try:
            close = parse_number(row.get("ClosingPrice"))  # blank: no trade today
            change = parse_number(row.get("Change"))
            previous = None if close is None or change is None else close - change
            v = valuation.get(code, {})
            m = margin.get(code)
            balance = parse_number(m.get("融資今日餘額"), blank=0.0) if m else None
            prior = parse_number(m.get("融資前日餘額"), blank=0.0) if m else None
            value = parse_number(row.get("TradeValue"), blank=0.0)
            pe, dividend_yield, pb = (parse_number(v.get(k)) for k in ("PEratio", "DividendYield", "PBratio"))
        except ValueError:
            skipped += 1  # one malformed row must not drop the whole market page
            continue
        rows.append([
            code,
            name,
            close,
            change,
            None if not previous else round(change / previous, 6),
            value,
            pe,
            dividend_yield,
            pb,
            balance,
            None if balance is None or prior is None else balance - prior,
        ])
    if not rows or skipped > len(daily) * 0.05:
        raise ValueError(f"TWSE daily has too many malformed rows ({skipped} of {len(daily)}).")
    return sorted(rows, key=lambda r: r[0])


def fetch_twse(config: dict[str, Any] | None = None, *, client: Any = None) -> Path | None:
    cfg = config or load_config()
    api = cfg.get("api", {})
    symbols = [str(item).strip() for item in api.get("symbols", [])]
    target = project_path(Path(cfg["data"]["raw_dir"]) / SNAPSHOT_FILE)
    target.unlink(missing_ok=True)  # never let an old snapshot pass as today's
    try:
        http = client or requests
        if http is None:
            raise RuntimeError("requests is not installed.")
        timeout = normalize_http_timeout(api.get("timeout_seconds"), default=20.0)
        budget = RequestBudget(max_requests=len(ENDPOINTS) * 2)
        payloads: dict[str, Any] = {}
        for name, path in ENDPOINTS.items():
            url = validate_upstream_url(BASE_URL + path, allowed_hosts=API_HOSTS)
            response, _attempts = request_with_retry(http.get, url, timeout=timeout, budget=budget, provider="twse")
            try:
                validate_response_origin(response, url, allowed_hosts=API_HOSTS)
                response.raise_for_status()
                payloads[name] = json.loads(read_http_response_bytes(response).decode("utf-8-sig"))
            finally:
                close = getattr(response, "close", None)
                if callable(close):
                    close()
        snapshot = normalize_twse_payloads(payloads, symbols)
        snapshot["all"] = normalize_market_wide(payloads, snapshot["trade_date"])
        snapshot["endpoints"] = {name: BASE_URL + path for name, path in ENDPOINTS.items()}
        written = write_json(snapshot, ensure_parent(target))
        snapshot_digest = hashlib.sha256(written.read_bytes()).hexdigest()
        print(f"TWSE snapshot for {snapshot['trade_date']} written ({snapshot_digest[:12]}).")
        return written
    except Exception as exc:
        print(f"TWSE OpenAPI fetch failed; the site will mark the snapshot unavailable: {safe_exception_message(exc)}")
        return None
