# 股票分析與追蹤 Dashboard

英文名稱：Stock Analysis and Market Tracking Dashboard

本專案是一個可作為後續產品開發起點的股票分析網頁，主軸是台股與美股追蹤、個股技術分析、熱門股儀表板、TWSE/yfinance 資料整合與深色前端展示；異常波動偵測保留為獨立頁面，作為資料工程與模型展示。

## 免責聲明

本專案僅供資料分析與技術展示，不構成任何投資建議。

本專案不輸出「買進 / 賣出 / 持有」建議，不承諾模型能準確預測股價，也不應作為任何投資操作依據。

## 專案目標

- 整合或讀取台股、美股與匯率資料。
- 建立股票追蹤儀表板，包含大盤、熱門股、個股行情與技術圖表。
- 補齊個股分析摘要，包含 MA5/MA20/MA60、RSI、成交量、52 週區間、近期報酬與股票健診評分。
- 建立欄位 alias mapping、數值清理、民國日期轉換與交易日時間序列處理。
- 建立日報酬率、rolling volatility、移動平均、成交量 z-score、匯率變動等特徵。
- 保留 Z-score baseline 與 Isolation Forest 或 fallback baseline 的異常波動展示。
- 建立繁體中文 Streamlit Dashboard。
- 提供 smoke test、pytest 測試與 Windows BAT 一鍵執行。

## 使用資料來源

本專案目前整合兩類資料來源：

- `yfinance`：用於取得台股與美股行情、歷史價格、成交量與指標圖表資料。
- TWSE OpenAPI：使用 `t187ap03_L` 取得完整上市公司基本資料清單，並保留使用者指定的 `t187ap46_L_20` ESG 反競爭行為法律訴訟資料端點。

`config.yaml` 保留 TWSE、央行、Bank of Taiwan 或 data.gov.tw 等 API URL。若 API 失敗、無網路或未設定 URL，系統會自動使用 `src/generate_sample_data.py` 產生 sample data，輸出：

- `data/sample/sample_market.csv`
- `data/sample/sample_fx.csv`

預設股票代號為 `0050`、`2330`、`2317`，匯率組合為 `USD_TWD`。

## 系統架構

```text
API / local CSV / sample data
        ↓
src/preprocess.py
        ↓
src/features.py
        ↓
src/train_anomaly_model.py
        ↓
src/evaluate.py
        ↓
app.py Streamlit Dashboard
```

## Repo 結構

```text
market-anomaly-dashboard/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
├── config.yaml
├── run_all.py
├── run_project.bat
├── app.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
├── models/
├── reports/
│   ├── figures/
│   └── metrics/
├── notebooks/
│   └── 01_eda.ipynb
├── src/
│   ├── fetch_market_data.py
│   ├── fetch_fx_data.py
│   ├── generate_sample_data.py
│   ├── preprocess.py
│   ├── features.py
│   ├── train_anomaly_model.py
│   ├── evaluate.py
│   ├── app_helpers.py
│   ├── smoke_test.py
│   ├── theme.py
│   └── utils.py
└── tests/
    ├── test_sample_data.py
    ├── test_preprocess.py
    ├── test_features.py
    ├── test_model_training.py
    ├── test_evaluate.py
    ├── test_app_import.py
    └── test_run_all.py
```

## 安裝方式

```bash
python -m venv .venv

# Windows:
.venv\Scripts\activate

# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Windows 一鍵執行

請將 `run_project.bat` 放在專案根目錄，也就是 `requirements.txt`、`run_all.py`、`app.py` 同一層。

如果你使用 Windows，可以直接雙擊：

```text
run_project.bat
```

這個檔案會自動完成：

1. 檢查 Python，順序為 PATH `python`、Windows `py -3`、Codex bundled Python fallback
2. 建立 `.venv`
3. 用 `.venv` 內的 Python 安裝 `requirements.txt`
4. 執行 `python run_all.py --mode sample`
5. 執行 `python src/smoke_test.py`
6. 執行 `pytest -q`
7. 用 `.venv` 內的 Python 在固定 port `8765` 啟動 Streamlit

啟動時終端機會印出目前專案路徑與固定網址：

```text
Project path: <你的專案根目錄>
Fixed dashboard URL: http://localhost:8765
```

如果不能雙擊執行，也可以在專案根目錄用 PowerShell 或 CMD 執行：

```bat
run_project.bat
```

若 Windows 阻擋執行，請在檔案上按右鍵，選擇「解除封鎖」，或改用終端機手動執行 README 中的指令。

如果出現 `No module named streamlit`，代表你不是用 `.venv` 內的 Python 啟動。請刪除舊的 `run_project.bat`，改用本專案提供的新版本；新版本會固定使用 `.venv\Scripts\python.exe -m streamlit run app.py --server.port 8765`。

## 執行方式

```bash
python run_all.py --mode sample
```

API mode 會先嘗試 API，失敗時自動切回 sample data：

```bash
python run_all.py --mode api
```

## Streamlit 執行方式

```bash
python -m streamlit run app.py --server.port 8765
```

## 模型方法

特徵工程以每個股票代號分組計算，rolling 特徵只使用過去資料，不做 random split，不跨股票混用時間序列。

主要特徵包含：

- `daily_return`
- `abs_return`
- `log_return`
- `volume_change_rate`
- `moving_avg_5`
- `moving_avg_20`
- `volatility_5`
- `volatility_20`
- `price_ma_gap`
- `volume_zscore_20`
- `fx_return`
- `fx_rolling_volatility_5`
- `risk_score_baseline`

異常偵測方法：

- Z-score baseline
- Isolation Forest
- 若目前環境未安裝 scikit-learn，使用可重現的 quantile baseline fallback，確保 demo 不因缺套件中斷

## 評估方式

本專案沒有真實人工標註異常事件，因此使用 pseudo-label 評估偵測行為。pseudo-label 來自高絕對報酬率、成交量爆量、匯率異常變動等啟發式規則。輸出包含 precision、recall、F1、anomaly rate、top anomaly cases，以及 baseline 比較。

金融版不做價格預測模型，因此不使用 MAE、RMSE、R2 作為必要指標。

## 前端功能

Dashboard 為繁體中文網站，包含：

- 專案介紹與免責聲明
- yfinance / TWSE OpenAPI 資料來源狀態
- 大盤指數卡片
- 熱門股卡片
- 股票分析頁與異常偵測展示頁分離
- 前端預設使用炭黑橘深色主題，未另外放置自訂主題選單
- 依 Streamlit 目前的深色／淺色狀態，自動套用 `charcoal_orange` 或 `paper_orange` 的完整元件與 Plotly 配色
- 產業篩選與自訂 yfinance 股票代號輸入
- 產業同類比較：同產業股票最新價、漲跌、量能倍率與 52 週位置
- 技術指標切換：MA5、MA20、MA60、布林通道、成交量、RSI、MACD
- 個股 K 線、均線、成交量均線、RSI 與 MACD
- 股票分析總覽：趨勢、RSI、量能、波動狀態
- 股票健診：趨勢、動能、量能、穩定度、價格位置 5 維評分
- 近期表現：5 日、20 日、60 日、120 日報酬
- 52 週區間、20 日支撐與壓力
- 股票基本資料與 TWSE 上市公司資訊
- TWSE 完整上市公司清單、常用台股 ETF／美股清單，以及合法自訂 yfinance 股票代號
- 股票代號與日期區間篩選
- 最新收盤價、近期波動率、異常事件數、平均成交量
- 股價趨勢圖
- 匯率趨勢圖
- 波動率趨勢圖
- 異常波動日期列表
- 異常點視覺化
- 專案限制說明

## 測試方式

```bash
pip install -r requirements.txt
python run_all.py --mode sample
python src/smoke_test.py
pytest -q
python -m streamlit run app.py --server.port 8765
```

## 測試與驗證

測試檔案固定為：

- `tests/test_sample_data.py`
- `tests/test_preprocess.py`
- `tests/test_features.py`
- `tests/test_model_training.py`
- `tests/test_evaluate.py`
- `tests/test_app_import.py`
- `tests/test_app_runtime.py`
- `tests/test_market_api.py`
- `tests/test_run_all.py`

測試涵蓋 sample data 產生、preprocess、feature engineering、模型訓練、評估輸出、主題對比、股票來源、Streamlit 兩頁載入、表單輸入、日期交換、BAT 檔案存在與 sample mode pipeline。

## 常見錯誤排除

- 找不到 Python：請安裝 Python 3.10 以上版本，並勾選 Add Python to PATH；若在 Codex 環境中執行，`run_project.bat` 會嘗試使用 Codex bundled Python。
- 找不到資料：請先執行 `python run_all.py --mode sample`。
- 找不到模型檔案：請先完成訓練流程，也就是執行 `python run_all.py --mode sample`。
- 找不到 metrics 檔案：請執行 `python run_all.py --mode sample` 或 `python src/smoke_test.py` 檢查產物。
- API 讀取失敗：系統會切換到 sample data，不會中斷 demo。
- Streamlit 無法啟動：請確認已執行 `pip install -r requirements.txt`。
- `.venv` 已存在但無法啟動：新版 `run_project.bat` 會自動偵測壞掉的 `.venv` 並重建。

## 深色/淺色主題與可讀性

Dashboard 前端預設使用炭黑橘深色主題，頁面本身不再提供額外主題選單。

主題 token 集中於 `src/theme.py` 的 `THEME_OPTIONS`，目前只保留實際使用的 `charcoal_orange` 與 `paper_orange`。程式會讀取 `st.context.theme`，讓 CSS、輸入元件、表格與 Plotly 圖表同步切換，避免淺色模式出現淡字或深色圖表殘留。

若部署環境沒有回報目前主題，才使用 `config.yaml` 的預設值：

```yaml
dashboard:
  theme_name: paper_orange
```

前端不另外建立重複的主題選擇器。

專案提供 `validate_theme_contrast()` 檢查文字與背景對比，避免文字看不清楚。至少檢查：

- `text` vs `background`
- `text` vs `card`
- `muted_text` vs `background`
- `muted_text` vs `card`
- `danger` vs `background`
- `success` vs `background`
- `accent` vs `background`

異常點、警告、正常狀態分別使用 `danger`、`warning`、`success`。若要新增主題，需要通過 `validate_theme_contrast` 測試。

## 專案限制

- sample data 是模擬資料，只用於展示 pipeline。
- yfinance 或 TWSE 無法連線時會改用本機快取或 sample data，因此離線數值不代表即時市場行情。
- pseudo-label 不是市場真實標籤。
- 異常偵測結果不代表價格預測或投資績效。
- 本專案不使用 Docker、GPU、大型 LLM、LSTM、Transformer 或大型深度學習模型。

## 未來改進

- 接入具服務等級承諾的即時行情與匯率資料來源。
- 加入更多總經、產業與市場廣度特徵。
- 建立真實事件標註資料，提高評估可信度。
- 增加 SHAP 或特徵貢獻分析。
- 擴充 EDA notebook 與資料版本控管。

## 履歷描述

簡短版：

- 建置台股與匯率異常波動偵測 Dashboard，整合 Open Data/API fallback、金融時間序列特徵工程、異常偵測、Streamlit 與 pytest 自動測試。

詳細版：

- 使用 pandas、numpy、scikit-learn 與 Streamlit 建立本地端金融資料分析專案，支援 API fallback、sample data generator、欄位 alias mapping、民國日期與逗號數值清理。
- 設計日報酬率、rolling volatility、成交量 z-score、匯率變動與風險分數等特徵，以 Isolation Forest 與 Z-score baseline 偵測異常波動。
- 補齊 run_all、smoke test、pytest 與 Windows `run_project.bat`，確保求職作品可在本地端重現執行。

面試 1 分鐘介紹稿：

> 這個專案是股票分析與追蹤 Dashboard，定位是可繼續開發的金融資料網頁，不是投資建議工具。我整合 yfinance 與 TWSE OpenAPI，前端提供大盤、熱門股、產業篩選、產業同類比較、個股 K 線、MA/布林通道/成交量/RSI/MACD 指標切換、52 週區間、近期報酬與股票健診評分。資料工程部分處理 API fallback、中文欄位 alias mapping、逗號數值清理、民國日期解析與交易日不連續。異常偵測展示獨立成另一頁，用 Isolation Forest 與 Z-score baseline 展示 pseudo-label 評估流程。最後用 Streamlit 做可配置深色/淺色主題的繁體中文互動式 Dashboard，搭配 run_all、smoke test、pytest 和 Windows BAT，讓整個專案能在本地端一鍵重現。
