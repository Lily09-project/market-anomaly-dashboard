# GitHub Pages

[開啟 Market Regime Lab](https://lily09-project.github.io/market-anomaly-dashboard/)

## 發布流程

`.github/workflows/pages.yml`：

1. 安裝鎖定的執行期依賴，`python run_all.py --mode sample` 產生合成資料、分析並寫出 `web/public/data/`。
2. `npm ci && npm run build && npm run size` 建置網站並檢查效能預算。
3. 只上傳 `web/dist/`。
4. 合併到 `main` 後部署，並以 `curl` 對線上網址做冒煙測試（首頁標題與 `manifest.json` 的 schema 版本）。

## 網站邊界

- 純靜態：沒有後端，壓力測試與快照驗證都在瀏覽器執行。
- 執行期不呼叫任何第三方服務；CSP 只允許同源資源。
- 每個資料檔載入時以 SHA-256 與 manifest 比對。
- 使用固定品牌配色、支援純鍵盤操作；所有圖表都有等價資料表。
