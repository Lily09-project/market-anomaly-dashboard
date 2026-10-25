# 部署指南

## 本機預覽

需求：Python 3.12、Node.js 22。

```bash
python -m venv .venv
python -m pip install -r requirements-dev.lock.txt
python run_all.py --mode sample
cd web && npm ci && npm run build && npm run preview
```

`--mode sample` 會產生固定種子的合成測試資料，只供本機離線研究與預覽，不是正式產品資料。若要在本機產生真實來源快照，使用：

```bash
python run_all.py --mode api --require-api
```

產品正式資料使用不需 token 的 TWSE 公開 JSON 歷史日成交查詢。嚴格模式在 API 不可用、資料不完整或驗證失敗時會停止，不輸出合成資料。不要在正式發布流程使用未加 `--require-api` 的一般 API 模式，因該模式可能回退到 sample。

Windows 執行 `run_project.bat`；`run_project.bat --validate` 會跑 pytest、Bandit、Ruff、pip-audit、TypeScript、ESLint、Vitest 覆蓋率與效能預算，但不啟動網站。

## Docker 正式映像

```bash
docker build -t market-regime-lab .
docker run --rm -p 8080:8080 market-regime-lab
```

Docker build 需要網路連線，會在建置階段執行 `python run_all.py --mode api --require-api` 並取得經驗證的 TWSE 快照；來源失敗會讓建置失敗。映像包含建置當時的靜態資料，執行時不連線至 TWSE；要更新資料需重新建置映像。

最終映像使用 `nginx-unprivileged`、UID 101、8080 port、`/healthz`，並提供 CSP、`X-Content-Type-Options: nosniff`、`frame-ancestors 'none'` 與 no-referrer 標頭。CI 會建置並啟動容器，檢查健康端點、安全標頭及 TWSE 非合成 provenance。

## GitHub Pages

PR 只用固定種子資料建立預覽；main、排程及手動正式部署必須成功取得並驗證 TWSE 資料，再執行真實資料 E2E 與部署 smoke。API 失敗不會回退至 sample。部署後網站以同源靜態快照運作，不需要使用者瀏覽器連接資料 API。

## 回復與更新

資料快照由建置輸入決定。正式回復應重新部署上一個已驗證的來源資料版本；sample 輸出僅供預覽，不可作為正式回復版本。
