# Market Regime Lab

[![Quality Gate](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/quality.yml)
[![Quality & Security](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/security.yml)

用臺股歷史行情探索市場狀態、異常事件、回測風險與壓力情境的互動式研究網站。研究用途，不構成投資建議。

**[開啟線上展示](https://lily09-project.github.io/market-anomaly-dashboard/)**

![Market Regime Lab 桌面畫面](docs/screenshots/pages-desktop.png)

## 功能

- 市場狀態偵測與異常事件研究
- 樣本內／樣本外回測與過度擬合檢查
- 可取消的瀏覽器端風險模擬
- 研究快照匯出、比對與完整性驗證

## 正式資料

正式網站使用 TWSE 公開 JSON 歷史日成交資料（0050、2330、2317），建置時驗證後發布靜態快照，並非即時報價。提供機關為金融監督管理委員會證券期貨局，原始來源為臺灣證券交易所；資料集為[上市個股日成交資訊（11549）](https://data.gov.tw/dataset/11549)，依[政府資料開放授權條款第 1 版](https://data.gov.tw/license)標示來源與授權。

合成資料只供本機方法測試與 PR 預覽；正式 Pages 與 Docker 必須成功擷取並驗證真實來源，失敗即停止，不以合成資料替代。

## 技術

Python、NumPy、React、TypeScript、Vite、Web Worker；GitHub Pages 提供靜態展示，另有非 root Docker 映像。

![回測研究畫面](docs/screenshots/backtest.png)

## 本機執行與驗證

需求：Python 3.12、Node.js 22。

```powershell
.\run_project.bat
.\run_project.bat --validate
```

方法、部署與驗收細節見 [方法說明](docs/METHODS.md)、[GitHub Pages](docs/GITHUB_PAGES.md)、[部署指南](docs/deployment.md)、[驗收標準](docs/ACCEPTANCE.md)及[安全政策](SECURITY.md)。