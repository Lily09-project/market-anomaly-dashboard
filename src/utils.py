from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
from numbers import Number
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import yaml
except Exception:
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config.yaml"

DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "name": "Taiwan Stock and Exchange Rate Anomaly Detection Dashboard",
        "short_name": "market-anomaly-dashboard",
        "random_state": 42,
        "sample_mode": True,
        "disclaimer": "本專案僅供資料分析與技術展示，不構成任何投資建議。",
    },
    "data": {
        "stock_symbols": ["0050", "2330", "2317"],
        "currency_pair": "USD_TWD",
        "start_date": "2021-01-01",
        "end_date": "2025-12-31",
        "raw_dir": "data/raw",
        "sample_dir": "data/sample",
        "processed_dir": "data/processed",
        "sample_market_path": "data/sample/sample_market.csv",
        "sample_fx_path": "data/sample/sample_fx.csv",
        "cleaned_path": "data/processed/market_cleaned.csv",
        "features_path": "data/processed/market_features.csv",
        "results_path": "data/processed/market_anomaly_results.csv",
    },
    "model": {
        "path": "models/market_anomaly_detector.joblib",
        "anomaly_contamination": 0.06,
        "random_state": 42,
    },
    "reports": {
        "metrics_dir": "reports/metrics",
        "figures_dir": "reports/figures",
        "anomaly_metrics_path": "reports/metrics/anomaly_metrics.json",
        "evaluation_summary_path": "reports/metrics/evaluation_summary.json",
    },
    "api": {
        "timeout_seconds": 15,
        "market_url": "",
        "fx_url": "",
        "twse_company_profile_url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
        "twse_esg_legal_url": "https://openapi.twse.com.tw/v1/opendata/t187ap46_L_20",
    },
    "dashboard": {
        "theme_name": "charcoal_orange",
        "dark_theme_name": "charcoal_orange",
        "light_theme_name": "paper_orange",
    },
}


def load_config(config_path: Path | str = CONFIG_PATH) -> dict[str, Any]:
    if yaml is None:
        return copy.deepcopy(DEFAULT_CONFIG)
    with Path(config_path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def project_path(path: str | Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else PROJECT_ROOT / path


def normalize_http_timeout(value: Any, default: float = 15.0) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = default
    if not pd.notna(timeout) or timeout <= 0:
        timeout = default
    return min(timeout, 60.0)


MAX_HTTP_RESPONSE_BYTES = 8 * 1024 * 1024


def read_http_response_bytes(response: Any, max_bytes: int = MAX_HTTP_RESPONSE_BYTES) -> bytes:
    """Read an HTTP response without allowing an unbounded body allocation."""
    if max_bytes <= 0:
        raise ValueError("HTTP response size limit must be positive.")
    headers = getattr(response, "headers", {}) or {}
    content_length = headers.get("content-length") or headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise ValueError(f"HTTP response exceeds the {max_bytes}-byte limit.")
        except (TypeError, ValueError) as exc:
            if isinstance(exc, ValueError) and "exceeds" in str(exc):
                raise

    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        chunks: list[bytes] = []
        total = 0
        for chunk in iterator(chunk_size=64 * 1024):
            if not chunk:
                continue
            chunk_bytes = bytes(chunk)
            total += len(chunk_bytes)
            if total > max_bytes:
                raise ValueError(f"HTTP response exceeds the {max_bytes}-byte limit.")
            chunks.append(chunk_bytes)
        return b"".join(chunks)

    raw = getattr(response, "content", None)
    if raw is not None:
        body = bytes(raw)
        if len(body) > max_bytes:
            raise ValueError(f"HTTP response exceeds the {max_bytes}-byte limit.")
        return body

    text = getattr(response, "text", None)
    if text is not None:
        body = str(text).encode(getattr(response, "encoding", None) or "utf-8")
        if len(body) > max_bytes:
            raise ValueError(f"HTTP response exceeds the {max_bytes}-byte limit.")
        return body

    raise TypeError("HTTP response does not expose a readable body.")


def safe_exception_message(error: BaseException, max_length: int = 240) -> str:
    """Return a bounded error message with URL credentials removed."""
    message = str(error).strip()
    message = re.sub(
        r"(?i)([?&](?:api[_-]?key|token|secret|password)=)[^&\s]+",
        r"\1[REDACTED]",
        message,
    )
    message = re.sub(r"(?i)(https?://[^\s?]+)\?[^\s]*", r"\1?[REDACTED]", message)
    message = message[:max(32, int(max_length))]
    return message or error.__class__.__name__


def ensure_parent(path: str | Path) -> Path:
    resolved = project_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def _atomic_write(path: str | Path, writer) -> Path:
    resolved = ensure_parent(path)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=resolved.parent,
            prefix=f".{resolved.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            writer(temporary)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, resolved)
    except Exception:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise
    return resolved


def atomic_write_dataframe(df: pd.DataFrame, path: str | Path) -> Path:
    return _atomic_write(path, lambda file: df.to_csv(file, index=False))


def ensure_project_dirs(config: dict[str, Any] | None = None) -> None:
    cfg = config or load_config()
    for key in ["raw_dir", "sample_dir", "processed_dir"]:
        project_path(cfg["data"][key]).mkdir(parents=True, exist_ok=True)
    project_path("models").mkdir(parents=True, exist_ok=True)
    project_path(cfg["reports"]["metrics_dir"]).mkdir(parents=True, exist_ok=True)
    project_path(cfg["reports"]["figures_dir"]).mkdir(parents=True, exist_ok=True)


def clean_numeric(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    if not isinstance(value, (str, Number)):
        return None
    text = str(value).strip()
    if not text or len(text) > 256 or text in {"--", "-", "NA", "N/A", "null", "None"}:
        return None
    text = re.sub(r"[,，$％%]", "", text)
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?[eE][+-]?\d+", text):
        try:
            numeric = float(text)
        except (TypeError, ValueError, OverflowError):
            return None
        return numeric if math.isfinite(numeric) else None
    text = re.sub(r"[^\d.\-]", "", text)
    if text in {"", "-", "."}:
        return None
    try:
        numeric = float(text)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if math.isfinite(numeric) else None


def parse_date(value: Any) -> pd.Timestamp | pd.NaT:
    try:
        if pd.isna(value):
            return pd.NaT
    except (TypeError, ValueError):
        return pd.NaT
    if isinstance(value, (list, tuple, dict, set)):
        return pd.NaT
    text = str(value).strip()
    if not text or len(text) > 128:
        return pd.NaT
    roc_match = re.match(r"^(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})$", text)
    if roc_match:
        year, month, day = map(int, roc_match.groups())
        if year < 1911:
            try:
                return pd.Timestamp(year + 1911, month, day)
            except (ValueError, OverflowError):
                return pd.NaT
    return pd.to_datetime(text, errors="coerce")


def write_json(data: dict[str, Any], path: str | Path) -> Path:
    return _atomic_write(
        path,
        lambda file: json.dump(data, file, ensure_ascii=False, indent=2, default=str),
    )


def read_existing_csv(paths: list[Path]) -> pd.DataFrame | None:
    for path in paths:
        if path.exists() and path.stat().st_size > 0:
            return pd.read_csv(path)
    return None
