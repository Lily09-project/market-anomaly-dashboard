# Research Trust Workbench

[![Quality & Security](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/security.yml)

面向台股與美股的可解釋研究工作台：把行情來源、資料品質、技術證據與可驗證研究快照放在同一個流程。支援桌面／行動版與深色／淺色主題。

> 本專案不是股價預測器、交易訊號或投資建議服務，不提供買賣建議。

## 介面預覽

![個股研究與技術證據](docs/screenshots/ui-stocks.png)
![市場雷達與研究排序](docs/screenshots/ui-radar.png)
![Research Snapshot 比較](docs/screenshots/ui-compare.png)

## Highlights

- 台股／美股代號正規化、OHLCV、均線、RSI、成交量與波動率。
- Research Readiness 與 Evidence Coherence，直接呈現來源、時效與樣本深度。
- 可解釋市場雷達：產業篩選、透明配置、最低證據門檻與穩定排序。
- `src/market_screener.py` 提供可重現的雷達排序與證據門檻。
- Z-score、Isolation Forest、價格波動與 pseudo-label 評估。
- Research Snapshot JSON、可列印 HTML 與 Snapshot Comparison，包含 `snapshot_id`、fingerprint 與 SHA-256。
- API 失敗時清楚標示 DEMO／cache／offline，不把示範資料偽裝成即時行情。

## Quick start

```powershell
git clone https://github.com/Lily09-project/market-anomaly-dashboard.git
cd market-anomaly-dashboard
.\run_project.bat
```

手動啟動與驗收：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_all.py --mode sample
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8765
.\run_project.bat --validate
```

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe quality\run_acceptance.py release
```

## 資料來源與降級

LIVE 仍需檢查交易日與完整度；DEMO／offline 只用於可重現驗證。API secrets、`.env`、使用者研究資料、cache 與本機產物不提交到 repository。研究工作流見 [docs/research-workflow.md](docs/research-workflow.md) 與 [docs/user-guide.md](docs/user-guide.md)，部署見 [docs/deployment.md](docs/deployment.md)，安全政策見 [SECURITY.md](SECURITY.md)。
