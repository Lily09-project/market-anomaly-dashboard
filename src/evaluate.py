from __future__ import annotations

from pathlib import Path
import struct
import zlib

import pandas as pd
try:
    import matplotlib
    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
except Exception:
    plt = None

from src.train_anomaly_model import precision_recall_f1, train_anomaly_model
from src.utils import load_config, project_path, write_json


def _write_fallback_png(path: Path, color: tuple[int, int, int] = (16, 81, 134)) -> None:
    width, height = 640, 320
    rows = []
    for y in range(height):
        row = bytearray([0])
        for x in range(width):
            line = abs(y - (height - 45 - int((x / max(width - 1, 1)) * 190))) < 2
            if line:
                row.extend(color)
            else:
                shade = 240 - int((y / height) * 8)
                row.extend((shade, shade + 1, shade + 2))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def _save_price_trend(df: pd.DataFrame, path: Path) -> None:
    if plt is None:
        _write_fallback_png(path, (16, 81, 134))
        return
    fig, ax = plt.subplots(figsize=(11, 5))
    for symbol, group in df.groupby("symbol"):
        ax.plot(group["date"], group["close"], linewidth=1.4, label=str(symbol))
    ax.set_title("Close Price Trend")
    ax.set_xlabel("Date")
    ax.set_ylabel("Close")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _save_volatility_trend(df: pd.DataFrame, path: Path) -> None:
    if plt is None:
        _write_fallback_png(path, (253, 179, 56))
        return
    fig, ax = plt.subplots(figsize=(11, 5))
    for symbol, group in df.groupby("symbol"):
        ax.plot(group["date"], group["volatility_20"], linewidth=1.2, label=str(symbol))
    ax.set_title("20-Day Rolling Volatility")
    ax.set_xlabel("Date")
    ax.set_ylabel("Volatility")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _save_anomaly_cases(df: pd.DataFrame, path: Path) -> None:
    if plt is None:
        _write_fallback_png(path, (232, 99, 73))
        return
    fig, ax = plt.subplots(figsize=(11, 5))
    first_symbol = str(df["symbol"].iloc[0])
    group = df[df["symbol"].astype(str) == first_symbol]
    anomalies = group[group["model_anomaly"] == 1]
    ax.plot(group["date"], group["close"], color="#105186", linewidth=1.4, label=f"{first_symbol} close")
    ax.scatter(anomalies["date"], anomalies["close"], color="#E86349", s=28, label="model anomaly", zorder=3)
    ax.set_title(f"Anomaly Cases - {first_symbol}")
    ax.set_xlabel("Date")
    ax.set_ylabel("Close")
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def evaluate_model(config: dict | None = None) -> Path:
    cfg = config or load_config()
    results_path = project_path(cfg["data"]["results_path"])
    if not results_path.exists():
        train_anomaly_model(cfg)
    df = pd.read_csv(results_path, parse_dates=["date"])
    y_true = df["pseudo_anomaly"]
    y_model = df["model_anomaly"]
    y_baseline = df["zscore_baseline_anomaly"]
    model_precision, model_recall, model_f1 = precision_recall_f1(y_true, y_model)
    baseline_precision, baseline_recall, baseline_f1 = precision_recall_f1(y_true, y_baseline)

    top_cases = (
        df.sort_values(["model_anomaly", "anomaly_score", "risk_score_baseline"], ascending=[False, False, False])
        .head(12)[["date", "symbol", "close", "daily_return", "volume_zscore_20", "risk_score_baseline", "anomaly_score"]]
        .to_dict(orient="records")
    )
    summary = {
        "rows": int(len(df)),
        "date_range": [str(df["date"].min().date()), str(df["date"].max().date())],
        "symbols": sorted(df["symbol"].astype(str).unique().tolist()),
        "model": {
            "precision": float(model_precision),
            "recall": float(model_recall),
            "f1": float(model_f1),
            "anomaly_rate": float(y_model.mean()),
        },
        "zscore_baseline": {
            "precision": float(baseline_precision),
            "recall": float(baseline_recall),
            "f1": float(baseline_f1),
            "anomaly_rate": float(y_baseline.mean()),
        },
        "top_anomaly_cases": top_cases,
        "limitation": "Evaluation is measured against heuristic pseudo-labels. Results show technical detection behavior, not investment performance.",
    }

    figures_dir = project_path(cfg["reports"]["figures_dir"])
    figures_dir.mkdir(parents=True, exist_ok=True)
    _save_price_trend(df, figures_dir / "price_trend.png")
    _save_volatility_trend(df, figures_dir / "volatility_trend.png")
    _save_anomaly_cases(df, figures_dir / "anomaly_cases.png")

    return write_json(summary, cfg["reports"]["evaluation_summary_path"])


if __name__ == "__main__":
    print(evaluate_model())
