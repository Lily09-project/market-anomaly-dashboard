# Market Regime Lab — 市場狀態實驗室

[![Quality Gate](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/quality.yml/badge.svg?branch=main)](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/quality.yml)
[![Quality & Security](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/Lily09-project/market-anomaly-dashboard/actions/workflows/security.yml)

> 一個「不會騙你」的量化研究實驗室：找出市場處於哪一種狀態、檢驗異常日之後是否真的有可預測的報酬、揭穿漂亮回測背後的過度擬合，並在瀏覽器裡做壓力測試。研究與教學用途，**不構成任何投資建議**。

**[▶ 開啟線上實驗室](https://lily09-project.github.io/market-anomaly-dashboard/)**：靜態分析網站，頁面讀取 GitHub Actions 定期更新的臺股歷史行情快照。

![總覽：價格與市場狀態](docs/screenshots/pages-desktop.png)

## 30 秒看懂這個專案

| 如果你想看… | 證據在哪裡 |
| --- | --- |
| **資料科學**：量化方法與統計誠實 | 高斯 HMM（Baum-Welch、Viterbi）用 numpy 自己寫，狀態還原準確率 87–92%；事件研究用 bootstrap 找回注入的反彈（區間 [0.5%, 2.4%]、真實值 1.2%）；PBO 與 Deflated Sharpe 揭穿漂亮回測 |
| **後端／資料工程**：可重現與可部署 | 確定性匯出與 SHA-256 manifest；Python 與 TypeScript 共用 mulberry32，壓力測試結果逐位一致（誤差 < 1e-9）；多階段 Docker、非 root nginx、健康檢查；Python 覆蓋率 99% |
| **前端／UI-UX**：複雜分析可以互動 | 可點選的參數熱力圖、Web Worker 模擬（可取消並顯示進度）、研究快照可匯出與比對、被竄改的快照會被拒絕；首屏 JS 86 KB（gzip） |

### 幾個刻意的設計取捨

- **自己實作 HMM，不用 hmmlearn。** 才能把跳空日當作缺值處理，避免模型把一次跳空誤當成一個獨立狀態；代價是要自己證明正確，所以測試涵蓋對數概似單調不遞減、轉移矩陣每列和為 1。
- **誠實呈現回測。** 0050 樣本內最佳 Sharpe 0.78，walk-forward 樣本外變成 −0.34；網站把這個落差直接放在畫面上，而不是只秀最漂亮的淨值曲線。
- **事件偵測只用過去的資訊。** 用 HMM 一步預測計算 z 分數，避免用到未來資料造成前視偏誤，並附自動檢查（測試會刻意注入未來資訊確認被拒絕）。
- **合成測試資料用來驗證程式。** 已知的狀態鏈與注入事件讓測試可檢查方法；正式網站資料則來自公開行情來源。

## 為什麼做這個

多數「股票分析儀表板」只畫 K 線與技術指標，而大多數回測文章只展示樣本內最漂亮的那條淨值曲線。這個專案反過來：**每個方法都先在已知答案的資料上驗證，再誠實呈現它在樣本外的表現。**

線上展示使用 FinMind 免登入公開 API 的臺股日行情（0050、2330、2317），每日產生靜態快照，並非即時報價。 FinMind 免費端每小時免 token 可查 300 次，限非商業用途且需標示來源；詳見[官方方案與授權](https://finmind.github.io/Pricing/)。固定種子的合成資料僅用於本機與 CI 的已知答案測試，不作為正式網站資料。

## 六個實驗

| 實驗 | 回答的問題 | 方法（numpy 自行實作） | 驗證結果 |
| --- | --- | --- | --- |
| **市場狀態偵測** | 現在是平穩、震盪還是高波動？會持續多久？ | 高斯隱藏馬可夫模型：縮放的前向後向、Baum-Welch、多組初始化、Viterbi；跳空日視為缺值；BIC 比較 1–3 個狀態 | 真實狀態還原準確率 87%–92%（門檻 80%）；對照組 BIC 正確地選 1 個狀態 |
| **異常事件研究** | 異常日之後的報酬可以預測嗎？ | 以 HMM 一步預測（只用過去）計算 z 分數；平均調整模型的 CAR；重抽事件的 bootstrap 95% 區間 | 注入跳空召回率 83%、精確率 98%；找回負向衝擊後的反彈（+3 日 CAR 1.5%，區間 [0.5%, 2.4%]，真實值 1.2%）；正向衝擊正確地不顯著；對照組 0 誤報 |
| **誠實回測** | 「最佳參數」是真本事還是運氣？ | 48 組均線交叉、樣本內／樣本外熱力圖、walk-forward、CSCV 計算 PBO、Deflated Sharpe Ratio、前視偏誤自動檢查 | 0050 樣本內最佳 Sharpe 0.78 → walk-forward 樣本外 −0.34；隨機漫步上 PBO 平均 ≥ 0.4、含真實訊號時明顯較低（單元測試） |
| **壓力測試** | 未來 60 天最糟會虧多少？ | 區塊 bootstrap 在 Web Worker 執行、可取消；扇形圖、VaR／CVaR 95%／99% | TypeScript 引擎與 Python 參考實作逐位一致（共用 mulberry32，誤差 < 1e-9） |
| **研究快照** | 怎麼證明一份分析結果沒被改過？ | 資料指紋＋參數＋結果的 canonical JSON，以 SHA-256 簽名；匯入時驗證結構、大小與指紋並逐項比較 | 竄改任何數字都會被拒絕並說明原因（E2E） |
| **資料可信度** | 數字從哪來、能重現嗎？ | 確定性匯出＋manifest、瀏覽器端 SHA-256 驗證 | CI 連跑兩次 `diff -r` 完全相同 |

<table>
  <tr>
    <td><img src="docs/screenshots/regimes.png" alt="HMM 判定的狀態與真實狀態並排" /></td>
    <td><img src="docs/screenshots/backtest.png" alt="樣本內與樣本外 Sharpe 熱力圖" /></td>
  </tr>
  <tr>
    <td colspan="2"><img src="docs/screenshots/stress.png" alt="區塊 bootstrap 扇形圖與期末報酬分布" /></td>
  </tr>
</table>

## 架構

```mermaid
flowchart LR
  A[FinMind 公開臺股日行情<br/>本機／CI 合成測試資料] --> B[preprocess<br/>欄位正規化・去重]
  B --> C[src/analytics<br/>HMM・事件研究・回測與 PBO/DSR・VaR]
  C --> D[export_web<br/>確定性 JSON + SHA-256 manifest]
  D --> E[React + TypeScript 靜態網站]
  E --> F[Web Worker<br/>區塊 bootstrap]
  E --> G[Web Crypto<br/>完整性驗證・研究快照]
  D --> H[Docker：非 root nginx]
```

- **資料科學**：所有演算法在 `src/analytics/` 以 numpy 自行實作（不使用 hmmlearn、statsmodels 等黑盒），每個都有手算小例子與「能否找回已知答案」的測試。
- **後端工程**：一條指令完成資料、分析與匯出；正式 Pages 工作流程只在公開行情通過驗證後才建置並部署，無法取得資料就失敗，不會回退成合成資料。Docker 與本機預覽仍可使用可重現的 sample mode。
- **前端**：React 19 + TypeScript + Vite、d3-scale 手寫 SVG（依容器寬度量測）、可點選的參數熱力圖、Web Worker 模擬可取消並顯示進度、Hash 路由保存標的與參數、固定淺色配色，不隨系統外觀偏好切換；首屏 JS 86 KB（gzip）。
- **可及性與安全**：每張圖都有等價資料表、熱力圖格子是可聚焦的按鈕、axe-core 零 serious/critical；嚴格 CSP、無 inline script、執行期不呼叫第三方；快照匯入有大小、結構與指紋驗證。

## 本機啟動

需求：Python 3.12、Node.js 22。

**Windows**

```powershell
git clone https://github.com/Lily09-project/market-anomaly-dashboard.git
cd market-anomaly-dashboard
.\run_project.bat            # 產生資料、跑測試、建置並開啟 http://127.0.0.1:4173
.\run_project.bat --validate # 只跑全部檢查，不啟動網站
```

**macOS／Linux**

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.lock.txt
.venv/bin/python run_all.py --mode sample
cd web && npm ci && npm run build && npm run preview
```

**Docker**

```bash
docker build -t market-regime-lab . && docker run --rm -p 8080:8080 market-regime-lab   # http://127.0.0.1:8080
```

## 測試與驗收

驗收標準在重做開始前就訂在 [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md)：

| 層級 | 指令 | 標準 |
| --- | --- | --- |
| Python 分析 | `python -W error -m pytest -q --cov=src.analytics --cov=src.export_web --cov-fail-under=90` | 全數通過；覆蓋率 ≥ 90%（目前 99%） |
| 前端邏輯 | `npm run typecheck && npm run lint && npm run coverage` | 0 錯誤；`web/src/lib` 覆蓋率 ≥ 85%；含 TS／Python 壓力測試一致性與快照竄改測試 |
| 端對端 | `npm run e2e` | 4 種視窗／系統色彩組合（1440 淺色與深色偏好、768 平板、390 手機）× F1–F7 旅程；檢查固定品牌配色、axe、鍵盤及 0 console error |
| 效能 | `npm run size` | 首屏 JS ≤ 200 KB、首屏資料 ≤ 800 KB |
| 安全與容器 | `ruff`、`bandit`、`pip-audit`、`npm audit`、gitleaks、CI 建置映像並檢查健康與 CSP 標頭 | 無問題 |

## 限制

- 網站資料是公開來源的歷史行情；回測與風險估計不代表未來表現，測試用合成資料結果也不代表實際報酬。
- 回測忽略滑價、流動性、稅與融資限制。
- VaR 只描述歷史報酬重組後的分布，無法涵蓋沒發生過的危機。
- 本站不提供投資建議或交易訊號。

方法細節見 [docs/METHODS.md](docs/METHODS.md)，部署見 [docs/deployment.md](docs/deployment.md)、[docs/GITHUB_PAGES.md](docs/GITHUB_PAGES.md)，安全通報見 [SECURITY.md](SECURITY.md)。
