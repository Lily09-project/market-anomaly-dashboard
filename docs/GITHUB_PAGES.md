# GitHub Pages

[開啟 Market Regime Lab](https://lily09-project.github.io/market-anomaly-dashboard/)

## 發布流程

`.github/workflows/pages.yml`：

1. 安裝鎖定的 Python 與前端依賴。
2. PR 只用固定種子資料建置預覽，不會部署到正式網站。
3. main、排程與手動正式建置執行 `python run_all.py --mode api --require-api`，取得並驗證免註冊的 FinMind 歷史行情。
4. 真實資料 E2E 通過後才建置並上傳 `web/dist/`。
5. 部署後 smoke test 驗證網站、資料 manifest 與 FinMind provenance；API 或來源驗證失敗即停止，不回退到合成資料。

## 資料與執行界線

- 正式頁面使用經驗證的臺股歷史日行情快照，不是即時報價。
- 資料在建置時從 FinMind 公開 API 取得；瀏覽器執行期間不呼叫第三方服務。
- 每個資料檔以 manifest 的 SHA-256 驗證；provenance 標示 FinMind 來源及非合成狀態。
- 合成資料只供離線方法測試與 PR 預覽，不能作為正式發布資料。
- 固定品牌配色、支援鍵盤操作，圖表提供等價資料表。
- FinMind 免費方案限非商業用途，需標示來源；使用限制以[官方方案說明](https://finmind.github.io/Pricing/)為準。
