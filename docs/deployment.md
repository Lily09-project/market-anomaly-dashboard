# 部署指南

## 本機

需求：Python 3.12、Node.js 22。

```bash
python -m venv .venv
python -m pip install -r requirements-dev.lock.txt
python run_all.py --mode sample
cd web && npm ci && npm run build && npm run preview   # http://127.0.0.1:4173
```

Windows 執行 `run_project.bat`；`run_project.bat --validate` 會跑完 pytest、Bandit、Ruff、pip-audit、TypeScript、ESLint、Vitest 覆蓋率與效能預算但不啟動網站。既有但版本不符或損壞的 `.venv` 不會被刪除，而是請使用者自行搬移；未知參數以結束碼 2 拒絕。

## 容器

```bash
docker build -t market-regime-lab .
docker run --rm -p 8080:8080 market-regime-lab
```

多階段建置：Python 階段產生資料與匯出、Node 階段建置網站、最終映像是 `nginx-unprivileged`，以 UID 101 執行、監聽 8080，提供 `/healthz` 健康檢查，並加上 CSP、`X-Content-Type-Options: nosniff`、`frame-ancestors 'none'` 與 no-referrer 標頭。CI 的 `container-build` 工作會實際建置映像、啟動容器並檢查這些項目。

## 真實資料（選用）

`config.yaml` 的 `api.provider`：

- `url`：設定 `api.market_url` 或環境變數 `MARKET_API_URL`，指向 CSV／JSON 端點（可辨識 TWSE 的中文欄位名稱）。只接受 HTTPS、拒絕 redirect、限制逾時與回應大小。
- `yfinance`：另外安裝 `pip install yfinance`，依 `api.symbols` 下載日線。

執行 `python run_all.py --mode api`；抓取失敗會退回合成資料並在網站標示。共同交易日少於 400 天時，匯出會以 `InsufficientHistoryError` 明確停止。

## 更新與回復

匯出是確定性的：相同輸入必定得到位元組相同的輸出。要回到基線，重新執行 `python run_all.py --mode sample`，或重新部署上一個成功的 `web/dist/`／映像。
