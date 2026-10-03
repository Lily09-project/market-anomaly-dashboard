"""Build a minimal, allowlisted static release; never publish the repository root."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ASSETS = ("index.html", "styles.css", "app.js")
OUTPUT_FILES = frozenset((*ASSETS, "data.json", "integrity.json", ".nojekyll"))
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 20000


def safe_path(root: Path, relative: str) -> Path:
    candidate = root / relative
    resolved_root = root.resolve()
    candidate.resolve().relative_to(resolved_root)
    if any(path.is_symlink() for path in (candidate, *candidate.parents) if path != resolved_root.parent):
        raise ValueError("Symlinks are not valid public inputs")
    if not candidate.is_file() or candidate.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Missing or oversized public input: " + relative)
    return candidate


def number(value: str | None) -> float | None:
    if value is None or value.strip().lower() in {"", "nan", "none", "null"}:
        return None
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite public number")
    return result


def read_rows(root: Path, path: str, columns: list[tuple[str, str, str]]) -> list[dict]:
    source = safe_path(root, path)
    with source.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {key for key, _, _ in columns}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing required public columns: " + path)
        rows = []
        for raw in reader:
            if len(rows) >= MAX_ROWS:
                raise ValueError("Public row limit exceeded")
            row = {}
            for key, _, kind in columns:
                value = raw.get(key)
                if kind == "number":
                    row[key] = number(value)
                else:
                    text = str(value or "").strip()
                    if len(text) > 500:
                        raise ValueError("Oversized public cell")
                    if kind == "date" and text:
                        datetime.fromisoformat(text)
                    row[key] = text or None
            rows.append(row)
    if not rows:
        raise ValueError("Empty public dataset: " + path)
    return rows


def dataset(root: Path, key: str, label: str, path: str, columns: list[tuple[str, str, str]],
            *, identity: list[str], group: str, group_label: str, value: str, date: str | None,
            chart_label: str, sort: str | None = None, name: str | None = None,
            secondary: str | None = None, minimum: dict | None = None) -> dict:
    rows = read_rows(root, path, columns)
    ids = [json.dumps([row[column] for column in identity], ensure_ascii=False) for row in rows]
    if any(any(row[column] is None for column in identity) for row in rows) or len(ids) != len(set(ids)):
        raise ValueError("Missing or duplicate public identity: " + key)
    return {"id": key, "label": label, "fields": [{"key": k, "label": title, "kind": kind} for k, title, kind in columns],
            "identity": identity, "group": group, "groupLabel": group_label, "value": value,
            "date": date, "chartLabel": chart_label, "sort": sort or date or value,
            "name": name or identity[-1], "secondary": secondary, "minimum": minimum, "rows": rows}


def read_json(root: Path, path: str) -> dict:
    value = json.loads(safe_path(root, path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("Public metadata must be an object")
    return value


def metric_dataset(root: Path, path: str, keys: tuple[str, ...], group_key: str | None = None) -> dict:
    payload = read_json(root, path)
    rows = []
    if group_key:
        payload = payload[group_key]
    for key in keys:
        value = payload.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            rows.append({"model": "預先計算結果", "metric": key.upper(), "value": float(value)})
    if not rows:
        raise ValueError("Missing public evaluation metrics")
    return {"id": "metrics", "label": "模型評估", "fields": [
        {"key": "model", "label": "模型", "kind": "text"},
        {"key": "metric", "label": "指標", "kind": "text"},
        {"key": "value", "label": "指標值", "kind": "number"}],
        "identity": ["metric"], "group": "model", "groupLabel": "模型", "value": "value",
        "date": None, "chartLabel": "評估結果（各指標單位不同，請以明細解讀）", "sort": "metric",
        "name": "metric", "secondary": None, "minimum": None, "rows": rows}


def validate_payload(payload: dict) -> None:
    if payload["schema_version"] != "pages-data/1" or not payload["datasets"]:
        raise ValueError("Invalid public schema")
    for item in payload["datasets"]:
        keys = {field["key"] for field in item["fields"]}
        if not {item["group"], item["value"], *item["identity"]}.issubset(keys):
            raise ValueError("Dataset configuration references unpublished columns")
        if item["date"] and item["date"] not in keys:
            raise ValueError("Missing public date")
        for row in item["rows"]:
            if set(row) != keys:
                raise ValueError("Row violates public column allowlist")
    json.dumps(payload, allow_nan=False)


def write_release(root: Path, payload: dict) -> Path:
    validate_payload(payload)
    destination = root / "pages-dist"
    if destination.is_symlink():
        raise ValueError("Invalid output symlink")
    destination.mkdir(exist_ok=True)
    if any(path.name not in OUTPUT_FILES or path.is_symlink() or not path.is_file() for path in destination.iterdir()):
        raise ValueError("Unexpected output inventory; refusing to publish")
    for name in ASSETS:
        shutil.copyfile(safe_path(root, "web/" + name), destination / name)
    content = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("Public bundle too large")
    (destination / "data.json").write_text(content, encoding="utf-8", newline="\n")
    integrity = {"schema_version": "pages-integrity/1",
                 "data_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                 "files": list((*ASSETS, "data.json", ".nojekyll"))}
    (destination / "integrity.json").write_text(json.dumps(integrity, indent=2) + "\n", encoding="utf-8")
    (destination / ".nojekyll").write_text("", encoding="utf-8")
    if {path.name for path in destination.iterdir()} != OUTPUT_FILES:
        raise ValueError("Incomplete public output")
    return destination


def build_payload(root: Path) -> dict:
    columns = [("date", "日期", "date"), ("symbol", "股票代碼", "text"), ("close", "收盤價", "number"),
               ("volume", "成交量", "number"), ("daily_return", "日報酬率", "number"),
               ("volatility_20", "20 日波動率", "number"), ("model_anomaly", "異常標記", "number"),
               ("anomaly_score", "異常分數", "number"), ("risk_score_baseline", "風險分數", "number")]
    overview = dataset(root, "overview", "市場總覽", "data/processed/market_anomaly_results.csv", columns,
                       identity=["date", "symbol"], group="symbol", group_label="股票代碼",
                       value="close", date="date", chart_label="歷史示範收盤價")
    volatility = {**overview, "id": "volatility", "label": "波動分析", "value": "volatility_20",
                  "chartLabel": "20 日滾動波動率"}
    anomaly = {**overview, "id": "anomaly", "label": "異常事件",
               "rows": [row for row in overview["rows"] if row["model_anomaly"] == 1],
               "chartLabel": "模型標記的異常日期與價格"}
    if not anomaly["rows"]:
        raise ValueError("Expected reproducible demo anomaly cases")
    views = [overview, volatility, anomaly,
             metric_dataset(root, "reports/metrics/evaluation_summary.json", ("precision", "recall", "f1"), "model")]
    dates = [row["date"][:10] for row in overview["rows"]]
    return {"schema_version": "pages-data/1", "kind": "market", "project": "market-anomaly-dashboard",
            "title": "市場研究工作台", "brand": "MARKET RESEARCH DESK",
            "source": {"mode": "DEMO · 示範資料", "range": min(dates) + "–" + max(dates), "captured_at": None},
            "notice": "以合成行情展示市場分析，非即時報價；可在瀏覽器篩選、比較與下載。",
            "disclaimer": "僅供資料分析與技術展示，不構成投資建議。模型評估使用啟發式標籤，非投資績效。",
            "quality": {"資料來源": "固定亂數種子生成的合成市場與匯率資料", "資料筆數": len(overview["rows"]),
                        "分析標的": "、".join(sorted({row["symbol"] for row in overview["rows"]})),
                        "日報酬率單位": "小數，例如 0.01 代表 1%", "模型評估": "啟發式標籤 Precision／Recall／F1",
                        "執行方式": "發布前計算；不在瀏覽器呼叫行情 API"},
            "datasets": views}

def build(root: Path = ROOT) -> Path:
    return write_release(root, build_payload(root))


if __name__ == "__main__":
    print("Built verified static release:", build())
