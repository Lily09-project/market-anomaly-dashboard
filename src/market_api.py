from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import requests
except Exception:
    requests = None

try:
    import yfinance as yf
except Exception:
    yf = None

from src.utils import atomic_write_dataframe, clean_numeric, project_path


TWSE_COMPANY_PROFILE_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
TWSE_ESG_LEGAL_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap46_L_20"
# Backward-compatible alias for existing callers and tests.
TWSE_GOVERNANCE_URL = TWSE_ESG_LEGAL_URL
YFINANCE_TIMEOUT_SECONDS = 15

TWSE_INDUSTRY_MAP = {
    "01": "水泥工業",
    "02": "食品工業",
    "03": "塑膠工業",
    "04": "紡織纖維",
    "05": "電機機械",
    "06": "電器電纜",
    "07": "化學生技醫療",
    "08": "玻璃陶瓷",
    "09": "造紙工業",
    "10": "鋼鐵工業",
    "11": "橡膠工業",
    "12": "汽車工業",
    "13": "電子工業",
    "14": "建材營造",
    "15": "航運業",
    "16": "觀光餐旅",
    "17": "金融保險",
    "18": "貿易百貨",
    "19": "綜合",
    "20": "其他",
    "21": "化學工業",
    "22": "生技醫療業",
    "23": "油電燃氣業",
    "24": "半導體業",
    "25": "電腦及週邊設備業",
    "26": "光電業",
    "27": "通信網路業",
    "28": "電子零組件業",
    "29": "電子通路業",
    "30": "資訊服務業",
    "31": "其他電子業",
    "32": "文化創意業",
    "33": "農業科技業",
    "34": "電子商務業",
    "35": "綠能環保",
    "36": "數位雲端",
    "37": "運動休閒",
    "38": "居家生活",
}


def configure_yfinance_cache() -> None:
    if yf is None or not hasattr(yf, "set_tz_cache_location"):
        return
    try:
        cache_dir = project_path("data/cache/yfinance")
        cache_dir.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache_dir))
    except Exception:
        pass


configure_yfinance_cache()

WATCHLIST = [
    {"symbol": "2330.TW", "display": "台積電", "category": "台股上市"},
    {"symbol": "2454.TW", "display": "聯發科", "category": "台股上市"},
    {"symbol": "0050.TW", "display": "元大台灣50", "category": "ETF"},
    {"symbol": "2317.TW", "display": "鴻海", "category": "台股上市"},
    {"symbol": "AAPL", "display": "Apple Inc.", "category": "美股"},
    {"symbol": "NVDA", "display": "NVIDIA", "category": "美股"},
]

STOCK_UNIVERSE = [
    *WATCHLIST,
    {"symbol": "2303.TW", "display": "聯電", "category": "半導體"},
    {"symbol": "2308.TW", "display": "台達電", "category": "電子零組件"},
    {"symbol": "2382.TW", "display": "廣達", "category": "電腦週邊"},
    {"symbol": "2412.TW", "display": "中華電", "category": "電信"},
    {"symbol": "2881.TW", "display": "富邦金", "category": "金融"},
    {"symbol": "2882.TW", "display": "國泰金", "category": "金融"},
    {"symbol": "2891.TW", "display": "中信金", "category": "金融"},
    {"symbol": "2886.TW", "display": "兆豐金", "category": "金融"},
    {"symbol": "2884.TW", "display": "玉山金", "category": "金融"},
    {"symbol": "2603.TW", "display": "長榮", "category": "航運"},
    {"symbol": "2609.TW", "display": "陽明", "category": "航運"},
    {"symbol": "2615.TW", "display": "萬海", "category": "航運"},
    {"symbol": "2002.TW", "display": "中鋼", "category": "鋼鐵"},
    {"symbol": "1301.TW", "display": "台塑", "category": "塑化"},
    {"symbol": "1303.TW", "display": "南亞", "category": "塑化"},
    {"symbol": "1326.TW", "display": "台化", "category": "塑化"},
    {"symbol": "1216.TW", "display": "統一", "category": "食品"},
    {"symbol": "1101.TW", "display": "台泥", "category": "水泥"},
    {"symbol": "1402.TW", "display": "遠東新", "category": "紡織"},
    {"symbol": "3008.TW", "display": "大立光", "category": "光電"},
    {"symbol": "3034.TW", "display": "聯詠", "category": "半導體"},
    {"symbol": "3711.TW", "display": "日月光投控", "category": "半導體"},
    {"symbol": "3231.TW", "display": "緯創", "category": "電腦週邊"},
    {"symbol": "2356.TW", "display": "英業達", "category": "電腦週邊"},
    {"symbol": "2324.TW", "display": "仁寶", "category": "電腦週邊"},
    {"symbol": "2395.TW", "display": "研華", "category": "工業電腦"},
    {"symbol": "5871.TW", "display": "中租-KY", "category": "金融租賃"},
    {"symbol": "5880.TW", "display": "合庫金", "category": "金融"},
    {"symbol": "0056.TW", "display": "元大高股息", "category": "ETF"},
    {"symbol": "00878.TW", "display": "國泰永續高股息", "category": "ETF"},
    {"symbol": "00919.TW", "display": "群益台灣精選高息", "category": "ETF"},
    {"symbol": "006208.TW", "display": "富邦台50", "category": "ETF"},
    {"symbol": "00692.TW", "display": "富邦公司治理", "category": "ETF"},
    {"symbol": "00713.TW", "display": "元大台灣高息低波", "category": "ETF"},
    {"symbol": "MSFT", "display": "Microsoft", "category": "美股"},
    {"symbol": "GOOGL", "display": "Alphabet", "category": "美股"},
    {"symbol": "AMZN", "display": "Amazon", "category": "美股"},
    {"symbol": "META", "display": "Meta", "category": "美股"},
    {"symbol": "TSLA", "display": "Tesla", "category": "美股"},
    {"symbol": "AMD", "display": "AMD", "category": "美股"},
    {"symbol": "AVGO", "display": "Broadcom", "category": "美股"},
    {"symbol": "NFLX", "display": "Netflix", "category": "美股"},
    {"symbol": "JPM", "display": "JPMorgan", "category": "美股"},
    {"symbol": "V", "display": "Visa", "category": "美股"},
    {"symbol": "SPY", "display": "SPDR S&P 500 ETF", "category": "美股 ETF"},
    {"symbol": "QQQ", "display": "Invesco QQQ ETF", "category": "美股 ETF"},
]

MARKET_INDEXES = [
    {"symbol": "^TWII", "display": "台灣加權", "region": "台灣"},
    {"symbol": "^GSPC", "display": "S&P 500", "region": "美國"},
    {"symbol": "^IXIC", "display": "NASDAQ", "region": "美國"},
    {"symbol": "^DJI", "display": "Dow Jones", "region": "美國"},
]


def to_yfinance_symbol(symbol: str) -> str:
    clean = str(symbol).strip()
    if clean.isdigit() and 4 <= len(clean) <= 6:
        return f"{clean}.TW"
    return clean.upper()


def build_twse_stock_universe(company_profiles: pd.DataFrame | None) -> list[dict[str, str]]:
    if company_profiles is None or company_profiles.empty:
        return []
    code_aliases = ["公司代號", "股票代號", "證券代號", "Code", "stockNo", "symbol"]
    name_aliases = ["公司簡稱", "公司名稱", "Name", "name", "簡稱"]
    industry_aliases = ["產業別", "產業類別", "Industry", "industry"]
    code_col = next((col for col in code_aliases if col in company_profiles.columns), None)
    name_col = next((col for col in name_aliases if col in company_profiles.columns), None)
    industry_col = next((col for col in industry_aliases if col in company_profiles.columns), None)
    if code_col is None or name_col is None:
        return []

    stocks = []
    for _, row in company_profiles.iterrows():
        code = str(row.get(code_col, "")).strip()
        if code.endswith(".0"):
            code = code[:-2]
        name = str(row.get(name_col, "")).strip()
        if not code.isdigit() or not 4 <= len(code) <= 6 or not name or name.lower() == "nan":
            continue
        raw_industry = str(row.get(industry_col, "")).strip() if industry_col else ""
        if raw_industry.lower() == "nan":
            raw_industry = ""
        industry = TWSE_INDUSTRY_MAP.get(raw_industry.zfill(2), raw_industry or "台股上市")
        stocks.append({"symbol": f"{code}.TW", "display": name, "category": industry})
    return stocks


def get_stock_universe(company_profiles: pd.DataFrame | None = None) -> list[dict[str, str]]:
    dynamic_stocks = build_twse_stock_universe(company_profiles)
    dynamic_lookup = {item["symbol"]: item for item in dynamic_stocks}
    seen = set()
    unique = []
    for item in STOCK_UNIVERSE:
        symbol = to_yfinance_symbol(item["symbol"])
        if symbol in seen:
            continue
        seen.add(symbol)
        merged = {**item, "symbol": symbol}
        dynamic = dynamic_lookup.get(symbol)
        if dynamic and (merged.get("category") == "台股上市" or not merged.get("category")):
            merged["category"] = dynamic["category"]
        unique.append(merged)
    for item in sorted(dynamic_stocks, key=lambda stock: stock["symbol"]):
        if item["symbol"] in seen:
            continue
        seen.add(item["symbol"])
        unique.append(item)
    return unique


def _fallback_rows_for_period(period: str) -> int:
    return {
        "1mo": 24,
        "2mo": 44,
        "3mo": 66,
        "6mo": 132,
        "1y": 260,
        "2y": 520,
    }.get(str(period).lower(), 90)


def _fallback_history(symbol: str, rows: int = 90) -> pd.DataFrame:
    sample_path = project_path("data/processed/market_anomaly_results.csv")
    clean_symbol = symbol.replace(".TW", "")
    if sample_path.exists():
        data = pd.read_csv(sample_path, parse_dates=["date"])
        match = data[data["symbol"].astype(str) == clean_symbol].copy()
        if not match.empty:
            match = match.tail(rows)
            return pd.DataFrame(
                {
                    "date": match["date"],
                    "open": match["open"],
                    "high": match["high"],
                    "low": match["low"],
                    "close": match["close"],
                    "volume": match["volume"],
                    "symbol": symbol,
                }
            )

    rng = np.random.default_rng(42)
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=rows)
    price = 100 + np.cumsum(rng.normal(0.2, 1.8, size=len(dates)))
    price = np.maximum(price, 10)
    return pd.DataFrame(
        {
            "date": dates,
            "open": price * (1 + rng.normal(0, 0.008, len(dates))),
            "high": price * (1 + rng.uniform(0.002, 0.018, len(dates))),
            "low": price * (1 - rng.uniform(0.002, 0.018, len(dates))),
            "close": price,
            "volume": rng.integers(700_000, 8_000_000, len(dates)),
            "symbol": symbol,
        }
    )


def _normalize_yfinance_download(history: pd.DataFrame | None, symbol: str) -> pd.DataFrame:
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame()
    data = history.copy()
    if isinstance(data.columns, pd.MultiIndex):
        first_level = data.columns.get_level_values(0)
        second_level = data.columns.get_level_values(1)
        if symbol in first_level:
            data = data[symbol].copy()
        elif symbol in second_level:
            data = data.xs(symbol, axis=1, level=1).copy()
        else:
            data.columns = first_level
    data = data.reset_index().rename(
        columns={
            "Date": "date",
            "Datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    required = ["date", "open", "high", "low", "close", "volume"]
    if any(col not in data.columns for col in required):
        return pd.DataFrame()
    data = data[required].dropna()
    data["symbol"] = symbol
    return data


def fetch_yfinance_histories(
    symbols: list[str] | tuple[str, ...],
    period: str = "6mo",
    interval: str = "1d",
) -> dict[str, tuple[pd.DataFrame, str]]:
    yf_symbols = list(dict.fromkeys(to_yfinance_symbol(symbol) for symbol in symbols))
    fallback_rows = _fallback_rows_for_period(period)
    if not yf_symbols:
        return {}
    if yf is None:
        return {symbol: (_fallback_history(symbol, fallback_rows), "sample") for symbol in yf_symbols}

    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            downloaded = yf.download(
                yf_symbols,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=len(yf_symbols) > 1,
                group_by="ticker",
                timeout=YFINANCE_TIMEOUT_SECONDS,
            )
    except Exception:
        downloaded = pd.DataFrame()

    histories = {}
    for symbol in yf_symbols:
        normalized = _normalize_yfinance_download(downloaded, symbol)
        if normalized.empty:
            histories[symbol] = (_fallback_history(symbol, fallback_rows), "sample")
        else:
            histories[symbol] = (normalized, "yfinance")
    return histories


def fetch_yfinance_history(symbol: str, period: str = "6mo", interval: str = "1d") -> tuple[pd.DataFrame, str]:
    yf_symbol = to_yfinance_symbol(symbol)
    return fetch_yfinance_histories([yf_symbol], period=period, interval=interval)[yf_symbol]


def summarize_history(history: pd.DataFrame) -> dict[str, Any]:
    if history.empty:
        return {}
    data = history.sort_values("date").copy()
    latest = data.iloc[-1]
    previous = data.iloc[-2] if len(data) > 1 else latest
    change = float(latest["close"] - previous["close"])
    change_pct = float(change / previous["close"] * 100) if previous["close"] else 0.0
    return {
        "latest_close": float(latest["close"]),
        "change": change,
        "change_pct": change_pct,
        "volume": float(latest.get("volume", 0)),
        "avg_volume": float(data["volume"].tail(20).mean()) if "volume" in data else 0.0,
        "high_52w": float(data["high"].max()),
        "low_52w": float(data["low"].min()),
        "currency": "TWD" if str(latest.get("symbol", "")).endswith(".TW") else "USD",
    }


def build_market_cards() -> list[dict[str, Any]]:
    cards = []
    histories = fetch_yfinance_histories([item["symbol"] for item in MARKET_INDEXES], period="2mo")
    for item in MARKET_INDEXES:
        history, source = histories[to_yfinance_symbol(item["symbol"])]
        summary = summarize_history(history)
        if not summary:
            continue
        cards.append({**item, **summary, "source": source})
    return cards


def build_watchlist_cards(symbols: list[str] | None = None) -> list[dict[str, Any]]:
    cards = []
    if symbols is None:
        watchlist = WATCHLIST
    else:
        universe_lookup = {item["symbol"]: item for item in get_stock_universe()}
        watchlist = []
        for symbol in symbols:
            yf_symbol = to_yfinance_symbol(symbol)
            item = universe_lookup.get(yf_symbol, {"symbol": yf_symbol, "display": "自訂標的", "category": "自訂"})
            watchlist.append(item)
    histories = fetch_yfinance_histories([item["symbol"] for item in watchlist], period="1y")
    for item in watchlist:
        history, source = histories[to_yfinance_symbol(item["symbol"])]
        summary = summarize_history(history)
        if not summary:
            continue
        spark = history.sort_values("date").tail(24)["close"].round(2).tolist()
        cards.append({**item, **summary, "sparkline": spark, "source": source})
    return cards


def _fetch_twse_dataset(url: str, raw_path: Path, timeout: int) -> tuple[pd.DataFrame, str]:
    if requests is not None:
        try:
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                for key in ("data", "records", "result"):
                    if isinstance(payload.get(key), list):
                        payload = payload[key]
                        break
            data = pd.DataFrame(payload)
            if not data.empty:
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_dataframe(data, raw_path)
                return data, "twse_openapi"
        except Exception:
            pass
    if raw_path.exists():
        return pd.read_csv(raw_path), "local_cache"
    return pd.DataFrame(), "unavailable"


def fetch_twse_company_profiles(timeout: int = 8) -> tuple[pd.DataFrame, str]:
    return _fetch_twse_dataset(
        TWSE_COMPANY_PROFILE_URL,
        project_path("data/raw/twse_company_profiles.csv"),
        timeout,
    )


def fetch_twse_esg_legal_data(timeout: int = 8) -> tuple[pd.DataFrame, str]:
    data, source = _fetch_twse_dataset(
        TWSE_ESG_LEGAL_URL,
        project_path("data/raw/twse_esg_legal.csv"),
        timeout,
    )
    if not data.empty:
        return data, source
    legacy_path = project_path("data/raw/twse_governance.csv")
    if legacy_path.exists():
        return pd.read_csv(legacy_path), "local_cache"
    return data, source


def fetch_twse_governance_data(timeout: int = 8) -> tuple[pd.DataFrame, str]:
    """Backward-compatible alias for the former, inaccurate function name."""
    return fetch_twse_esg_legal_data(timeout)


def lookup_twse_company(symbol: str, governance_df: pd.DataFrame) -> dict[str, Any]:
    if governance_df.empty:
        return {}
    code_aliases = ["公司代號", "證券代號", "公司代碼", "stock_id", "symbol"]
    name_aliases = ["公司簡稱", "公司名稱", "name", "簡稱"]
    level_aliases = ["公司治理評鑑等級", "評鑑等級", "治理評鑑等級", "等級"]
    code_col = next((col for col in code_aliases if col in governance_df.columns), None)
    if code_col is None:
        return {}
    clean_symbol = str(symbol).replace(".TW", "")
    match = governance_df[governance_df[code_col].astype(str).str.strip() == clean_symbol]
    if match.empty:
        return {}
    row = match.iloc[0]
    name_col = next((col for col in name_aliases if col in governance_df.columns), None)
    level_col = next((col for col in level_aliases if col in governance_df.columns), None)
    return {
        "twse_name": row.get(name_col, "") if name_col else "",
        "governance_level": row.get(level_col, "") if level_col else "",
        "twse_source_columns": list(governance_df.columns),
    }


def format_number(value: float | int | None, digits: int = 2) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    value = float(value)
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.{digits}f}T"
    if abs_value >= 100_000_000:
        return f"{value / 100_000_000:.{digits}f}億"
    if abs_value >= 10_000:
        return f"{value / 10_000:.{digits}f}萬"
    return f"{value:,.{digits}f}"


def compute_technical_indicators(history: pd.DataFrame) -> pd.DataFrame:
    data = history.sort_values("date").copy()
    data["ma5"] = data["close"].rolling(5, min_periods=1).mean()
    data["ma20"] = data["close"].rolling(20, min_periods=1).mean()
    data["ma60"] = data["close"].rolling(60, min_periods=1).mean()
    data["daily_return"] = data["close"].pct_change().fillna(0)
    data["volatility_20"] = data["daily_return"].rolling(20, min_periods=2).std().fillna(0) * 100
    data["volume_ma20"] = data["volume"].rolling(20, min_periods=1).mean()
    data["volume_ratio_20"] = data["volume"] / data["volume_ma20"].replace(0, np.nan)
    data["high_20"] = data["high"].rolling(20, min_periods=1).max()
    data["low_20"] = data["low"].rolling(20, min_periods=1).min()
    delta = data["close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    data["rsi14"] = (100 - (100 / (1 + rs))).fillna(50)
    return data


def _return_over_sessions(data: pd.DataFrame, sessions: int) -> float:
    if len(data) <= sessions:
        base = float(data.iloc[0]["close"])
    else:
        base = float(data.iloc[-sessions - 1]["close"])
    latest = float(data.iloc[-1]["close"])
    return (latest / base - 1) * 100 if base else 0.0


def _score_to_label(score: float) -> str:
    if score >= 4.2:
        return "強勢"
    if score >= 3.4:
        return "偏強"
    if score >= 2.4:
        return "中性"
    if score >= 1.6:
        return "偏弱"
    return "弱勢"


def build_stock_analysis(history: pd.DataFrame) -> dict[str, Any]:
    data = compute_technical_indicators(history)
    if data.empty:
        return {}

    latest = data.iloc[-1]
    previous = data.iloc[-2] if len(data) > 1 else latest
    close = float(latest["close"])
    previous_close = float(previous["close"])
    change = close - previous_close
    change_pct = (change / previous_close * 100) if previous_close else 0.0
    ma5 = float(latest["ma5"])
    ma20 = float(latest["ma20"])
    ma60 = float(latest["ma60"])
    rsi14 = float(latest["rsi14"])
    volume_ratio = float(latest["volume_ratio_20"]) if not pd.isna(latest["volume_ratio_20"]) else 1.0
    volatility_20 = float(latest["volatility_20"])
    high_52w = float(data["high"].max())
    low_52w = float(data["low"].min())
    range_position = ((close - low_52w) / (high_52w - low_52w) * 100) if high_52w > low_52w else 50.0
    ma20_distance = (close / ma20 - 1) * 100 if ma20 else 0.0

    if close >= ma5 >= ma20 >= ma60:
        trend_label, trend_note, trend_score = "多頭排列", "價格站上短中長期均線", 5.0
    elif close >= ma20 and ma20 >= ma60:
        trend_label, trend_note, trend_score = "偏多整理", "價格維持在中期均線上方", 4.0
    elif close >= ma20:
        trend_label, trend_note, trend_score = "站回均線", "價格站上 MA20，但長期趨勢仍待確認", 3.2
    elif close >= ma60:
        trend_label, trend_note, trend_score = "中性震盪", "價格低於 MA20 但仍守住 MA60", 2.6
    else:
        trend_label, trend_note, trend_score = "弱勢整理", "價格跌破主要均線", 1.4

    if rsi14 >= 70:
        momentum_label, momentum_note, momentum_score = "RSI 過熱", "短線動能強，但需留意拉回", 3.2
    elif rsi14 >= 55:
        momentum_label, momentum_note, momentum_score = "動能偏強", "RSI 維持在偏強區", 4.2
    elif rsi14 >= 45:
        momentum_label, momentum_note, momentum_score = "動能中性", "買賣力道接近平衡", 3.0
    elif rsi14 >= 30:
        momentum_label, momentum_note, momentum_score = "動能偏弱", "短線買盤力道不足", 2.0
    else:
        momentum_label, momentum_note, momentum_score = "RSI 超賣", "價格可能處於弱勢或反彈前段", 2.4

    if volume_ratio >= 1.5:
        volume_label, volume_note, volume_score = "明顯放量", "成交量高於 20 日均量", 4.0
    elif volume_ratio >= 0.8:
        volume_label, volume_note, volume_score = "量能正常", "成交量接近近期均量", 3.2
    else:
        volume_label, volume_note, volume_score = "量縮觀望", "市場參與度低於近期均量", 2.2

    if volatility_20 >= 3.5:
        risk_label, risk_note, risk_score = "高波動", "近期價格波動較大", 1.8
    elif volatility_20 >= 2.0:
        risk_label, risk_note, risk_score = "中波動", "波動處於可觀察區間", 3.0
    else:
        risk_label, risk_note, risk_score = "低波動", "近期走勢相對平穩", 4.2

    valuation_score = 4.0 if range_position <= 80 else 2.8
    valuation_note = "價格距離區間高點仍有空間" if range_position <= 80 else "價格接近區間高位"
    health_dimensions = [
        {"label": "趨勢", "score": trend_score, "note": trend_note},
        {"label": "動能", "score": momentum_score, "note": momentum_note},
        {"label": "量能", "score": volume_score, "note": volume_note},
        {"label": "穩定", "score": risk_score, "note": risk_note},
        {"label": "位置", "score": valuation_score, "note": valuation_note},
    ]
    overall_score = float(np.mean([item["score"] for item in health_dimensions]))

    return {
        "data": data,
        "latest": {
            "close": close,
            "change": change,
            "change_pct": change_pct,
            "volume": float(latest["volume"]),
            "currency": "TWD" if str(latest.get("symbol", "")).endswith(".TW") else "USD",
        },
        "technical": {
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "rsi14": rsi14,
            "volume_ratio_20": volume_ratio,
            "volatility_20": volatility_20,
            "ma20_distance": ma20_distance,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "range_position": max(0.0, min(100.0, range_position)),
            "support_20d": float(latest["low_20"]),
            "resistance_20d": float(latest["high_20"]),
        },
        "signals": [
            {"label": "趨勢", "value": trend_label, "note": trend_note, "score": trend_score},
            {"label": "RSI", "value": momentum_label, "note": momentum_note, "score": momentum_score},
            {"label": "量能", "value": volume_label, "note": volume_note, "score": volume_score},
            {"label": "波動", "value": risk_label, "note": risk_note, "score": risk_score},
        ],
        "performance": {
            "5 日": _return_over_sessions(data, 5),
            "20 日": _return_over_sessions(data, 20),
            "60 日": _return_over_sessions(data, 60),
            "120 日": _return_over_sessions(data, 120),
        },
        "health": {
            "overall_score": overall_score,
            "overall_label": _score_to_label(overall_score),
            "dimensions": health_dimensions,
        },
    }
