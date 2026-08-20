from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import date, datetime, timezone
from html import escape
from typing import Any

import pandas as pd

from src.research_methodology import build_methodology_manifest, methodology_fingerprint
from src.research_memo import normalize_research_memo


SNAPSHOT_SCHEMA_VERSION = "1.0"
HISTORY_COLUMNS = ("date", "open", "high", "low", "close", "volume")
LIMITATIONS = (
    "This snapshot records historical data observations and derived technical evidence.",
    "It does not predict prices, recommend trades, or measure investment performance.",
    "The export excludes raw OHLCV rows; use the history fingerprint to verify its input dataset.",
)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "item"):
        return _json_value(value.item())
    return str(value)


def _canonical_json(value: Mapping[str, Any] | list[dict[str, Any]]) -> bytes:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _normalised_history(history: pd.DataFrame) -> list[dict[str, Any]]:
    if not isinstance(history, pd.DataFrame) or "date" not in history:
        return []

    data = history.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    for column in HISTORY_COLUMNS[1:]:
        data[column] = pd.to_numeric(data[column], errors="coerce") if column in data else pd.NA
    data = data.dropna(subset=["date"]).sort_values("date")
    records: list[dict[str, Any]] = []
    for row in data.loc[:, HISTORY_COLUMNS].to_dict(orient="records"):
        records.append(
            {
                "date": pd.Timestamp(row["date"]).date().isoformat(),
                **{column: _json_value(row[column]) for column in HISTORY_COLUMNS[1:]},
            }
        )
    return records


def _utc_timestamp(value: datetime | pd.Timestamp) -> str:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    else:
        timestamp = timestamp.tz_convert(timezone.utc)
    return timestamp.isoformat().replace("+00:00", "Z")


def _asset_payload(asset: Mapping[str, Any]) -> dict[str, str]:
    return {
        "symbol": str(asset.get("symbol", "")).strip(),
        "display_name": str(asset.get("display_name", "")).strip(),
        "industry": str(asset.get("industry", "")).strip(),
        "currency": str(asset.get("currency", "")).strip(),
    }


def calculate_snapshot_id(snapshot: Mapping[str, Any]) -> str:
    """Calculate the deterministic ID for snapshot research content."""

    content = {
        str(key): value
        for key, value in snapshot.items()
        if key not in {"snapshot_id", "captured_at_utc"}
    }
    return hashlib.sha256(_canonical_json(content)).hexdigest()

def build_research_snapshot(
    asset: Mapping[str, Any],
    history: pd.DataFrame,
    source: str,
    brief: Mapping[str, Any],
    captured_at: datetime | pd.Timestamp,
) -> dict[str, Any]:
    """Create a deterministic, JSON-safe research snapshot without I/O."""
    records = _normalised_history(history)
    quality = _json_value(brief.get("data_quality", {}))
    quality_mapping = dict(quality) if isinstance(quality, Mapping) else {}
    quality_mapping["source"] = source or "unavailable"
    as_of_date = str(quality_mapping.get("latest_date", "") or (records[-1]["date"] if records else ""))
    provenance = {
        "source": source or "unavailable",
        "quality_state": str(quality_mapping.get("state", "unavailable")),
        "observations": int(quality_mapping.get("observations", len(records)) or 0),
        "coverage_pct": _json_value(quality_mapping.get("coverage_pct")),
        "warnings": list(quality_mapping.get("warnings", [])),
        "history_start_date": records[0]["date"] if records else "",
        "history_end_date": records[-1]["date"] if records else "",
        "history_fingerprint": hashlib.sha256(_canonical_json(records)).hexdigest(),
    }
    methodology = brief.get("methodology")
    if not isinstance(methodology, Mapping):
        methodology = build_methodology_manifest()
    methodology = _json_value(methodology)
    methodology_mapping = dict(methodology) if isinstance(methodology, Mapping) else build_methodology_manifest()
    methodology_hash = methodology_fingerprint(methodology_mapping)
    memo = normalize_research_memo(brief.get("memo"))
    content = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "as_of_date": as_of_date,
        "asset": _asset_payload(asset),
        "provenance": provenance,
        "research": {
            "evidence": _json_value(brief.get("evidence", [])),
            "coherence": _json_value(brief.get("coherence", {})),
            "methodology": methodology,
            "methodology_fingerprint": methodology_hash,
            "changes": _json_value(brief.get("changes", {})),
            "peer_context": _json_value(brief.get("peer_context", {})),
            "memo": memo,
        },
        "limitations": list(LIMITATIONS),
    }
    snapshot_id = calculate_snapshot_id(content)
    return {**content, "snapshot_id": snapshot_id, "captured_at_utc": _utc_timestamp(captured_at)}


def snapshot_to_json_bytes(snapshot: Mapping[str, Any]) -> bytes:
    """Serialise a snapshot as UTF-8 JSON without non-finite numeric values."""
    return json.dumps(_json_value(snapshot), ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8")



def _html_text(value: Any) -> str:
    return escape(str(value if value is not None else ""))


def _html_table(rows: Any) -> str:
    safe_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    if not safe_rows:
        return '<p class="empty">No comparable data is available.</p>'
    columns = list(dict.fromkeys(str(key) for row in safe_rows for key in row))
    header = "".join(f"<th>{_html_text(column)}</th>" for column in columns)
    body = "".join(
        "<tr>" + "".join(f"<td>{_html_text(row.get(column, ''))}</td>" for column in columns) + "</tr>"
        for row in safe_rows
    )
    return f"<table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"


def render_snapshot_html(snapshot: Mapping[str, Any]) -> bytes:
    """Render a self-contained, printable HTML research snapshot."""
    asset = snapshot.get("asset", {})
    provenance = snapshot.get("provenance", {})
    research = snapshot.get("research", {})
    safe_asset = asset if isinstance(asset, Mapping) else {}
    safe_provenance = provenance if isinstance(provenance, Mapping) else {}
    safe_research = research if isinstance(research, Mapping) else {}
    warnings = safe_provenance.get("warnings", [])
    warning_items = "".join(f"<li>{_html_text(item)}</li>" for item in warnings) if isinstance(warnings, list) else ""
    evidence = safe_research.get("evidence", [])
    evidence_cards = "".join(
        "<article class=\"evidence\">"
        f"<h3>{_html_text(item.get('label', item.get('id', 'Evidence')))}</h3>"
        f"<p class=\"state\">{_html_text(item.get('state', 'unavailable'))}</p>"
        f"<strong>{_html_text(item.get('headline', ''))}</strong>"
        f"<p>{_html_text(item.get('detail', ''))}</p>"
        f"<p class=\"metrics\">{_html_text(' | '.join(str(metric) for metric in item.get('metrics', [])))}</p>"
        "</article>"
        for item in evidence
        if isinstance(item, Mapping)
    )
    changes = safe_research.get("changes", {})
    peers = safe_research.get("peer_context", {})
    coherence = safe_research.get("coherence", {})
    memo = safe_research.get("memo", {})
    methodology = safe_research.get("methodology", {})
    methodology_section = ""
    if isinstance(methodology, Mapping):
        indicators = methodology.get("technical_indicators", {})
        thresholds = methodology.get("research_thresholds", {})
        methodology_section = (
            f'<section><h2>Methodology</h2>'
            f'<p>Version: {_html_text(methodology.get("version", ""))}<br>'
            f'Methodology fingerprint: {_html_text(safe_research.get("methodology_fingerprint", ""))}<br>'
            f'MA windows: {_html_text(indicators.get("moving_average_windows", ""))}<br>'
            f'RSI period: {_html_text(indicators.get("rsi_period", ""))}<br>'
            f'Volatility window: {_html_text(indicators.get("volatility_window", ""))}<br>'
            f'Stock minimum observations: {_html_text(thresholds.get("stock_min_observations", ""))}</p></section>'
        )
    coherence_counts = coherence.get("counts", {}) if isinstance(coherence, Mapping) else {}
    coherence_section = ""
    if isinstance(coherence, Mapping) and coherence.get("label"):
        count_text = " · ".join(
            f"{_html_text(label)} {_html_text(coherence_counts.get(key, 0))}"
            for key, label in (("positive", "Positive"), ("neutral", "Neutral"), ("risk", "Risk"), ("unavailable", "Unavailable"))
        )
        coherence_section = (
            f'<section><h2>Evidence coherence</h2>'
            f'<p><strong>{_html_text(coherence.get("label"))}</strong><br>'
            f'{_html_text(coherence.get("summary", ""))}<br>'
            f'<span class="meta">{count_text}</span></p></section>'
        )
    memo_section = ""
    if isinstance(memo, Mapping):
        memo_status = memo.get("status", "draft")
        memo_rows = (
            ("Hypothesis", memo.get("hypothesis", "")),
            ("Supporting evidence", memo.get("supporting_evidence", "")),
            ("Counter-evidence", memo.get("counter_evidence", "")),
            ("Risks and unknowns", memo.get("risks_unknowns", "")),
            ("Next question", memo.get("next_question", "")),
            ("Next review date", memo.get("next_review_date", "")),
        )
        memo_items = "".join(
            f"<dt>{_html_text(label)}</dt><dd>{_html_text(value) or '<span class=\"meta\">Not recorded</span>'}</dd>"
            for label, value in memo_rows
        )
        memo_section = (
            f'<section><h2>Research memo</h2><p class="meta">Status: {_html_text(memo_status)}</p>'
            f'<dl class="memo-list">{memo_items}</dl></section>'
        )
    change_rows = changes.get("rows", []) if isinstance(changes, Mapping) else []
    peer_rows = peers.get("rows", []) if isinstance(peers, Mapping) else []
    limitations = snapshot.get("limitations", [])
    limitation_items = "".join(f"<li>{_html_text(item)}</li>" for item in limitations) if isinstance(limitations, list) else ""
    title = f"{_html_text(safe_asset.get('symbol', ''))} {_html_text(safe_asset.get('display_name', ''))}".strip()
    document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} Research Snapshot</title>
<style>
:root {{ color-scheme: light; --ink:#17202b; --muted:#536170; --line:#cfd7df; --surface:#f7f9fb; --accent:#b55a18; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:#fff; color:var(--ink); font:15px/1.55 Arial,"Microsoft JhengHei",sans-serif; }}
main {{ max-width:900px; margin:0 auto; padding:40px; }} h1,h2,h3,p {{ margin-top:0; }} h1 {{ font-size:30px; }} h2 {{ margin-top:32px; font-size:18px; }}
.eyebrow,.state {{ color:var(--accent); font-weight:700; text-transform:uppercase; letter-spacing:.04em; }} .meta {{ color:var(--muted); }}
.provenance,.warning {{ border:1px solid var(--line); background:var(--surface); padding:16px; }} .warning {{ border-left:4px solid var(--accent); }}
.evidence-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }} .evidence {{ border:1px solid var(--line); padding:16px; }} .evidence h3 {{ margin-bottom:4px; }} .metrics {{ color:var(--muted); font-family:monospace; }} .memo-list {{ display:grid; grid-template-columns:minmax(150px,0.35fr) minmax(0,1fr); gap:10px 18px; border:1px solid var(--line); padding:16px; background:var(--surface); }} .memo-list dt {{ font-weight:700; color:var(--accent); }} .memo-list dd {{ margin:0; white-space:pre-wrap; }}
table {{ width:100%; border-collapse:collapse; }} th,td {{ border:1px solid var(--line); padding:8px; text-align:left; vertical-align:top; }} th {{ background:var(--surface); }} .empty {{ color:var(--muted); }}
@media print {{ body {{ font-size:11pt; }} main {{ max-width:none; padding:0; }} .evidence {{ break-inside:avoid; }} }}
@media (max-width:640px) {{ main {{ padding:24px; }} .evidence-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body><main>
<p class="eyebrow">Research Snapshot</p>
<h1>{title}</h1>
<p class="meta">Snapshot ID: {_html_text(snapshot.get('snapshot_id', ''))}<br>Captured: {_html_text(snapshot.get('captured_at_utc', ''))}<br>Market as of: {_html_text(snapshot.get('as_of_date', ''))}</p>
<section class="provenance"><h2>Data provenance</h2><p>Source: {_html_text(safe_provenance.get('source', 'unavailable'))}<br>Quality: {_html_text(safe_provenance.get('quality_state', 'unavailable'))}<br>History fingerprint: {_html_text(safe_provenance.get('history_fingerprint', ''))}</p></section>
{f'<section class="warning"><h2>Warnings</h2><ul>{warning_items}</ul></section>' if warning_items else ''}
<section><h2>Evidence</h2><div class="evidence-grid">{evidence_cards or '<p class="empty">No evidence is available.</p>'}</div></section>
{coherence_section}
{memo_section}
{methodology_section}
<section><h2>Recent changes</h2>{_html_table(change_rows)}</section>
<section><h2>Peer context</h2>{_html_table(peer_rows)}</section>
<section><h2>Limitations</h2><ul>{limitation_items}</ul></section>
</main></body></html>"""
    return document.encode("utf-8")