# Research Trust Workbench

> A stock-analysis workspace that makes data quality and technical evidence visible before asking anyone to interpret a chart.

繁體中文名稱：股票研究可信度工作台。這是一個以台股與美股為範圍的資料產品 side project；異常偵測保留在獨立頁面，作為資料工程與模型流程展示。

## Why This Exists

多數金融儀表板能快速畫出價格與技術指標，卻很少先回答四個必要問題：資料是否可用、結論依據是什麼、哪些訊號正在改變、以及這支股票和可比較標的相比位於何處。

本專案把這四件事放到個股頁的第一層。它不是股價預測器，也不把單一分數包裝成投資建議；它是一個讓研究者能追溯資料狀態與技術證據的工作台。

## 可解釋研究工作台

選定個股後，頁面依序呈現：

1. **資料可信度**：來源、最新可用交易日、觀測筆數、欄位覆蓋率與 fallback 警示。
2. **證據矩陣**：趨勢、動能、量能、風險各自的狀態、數值與判讀理由。
3. **本期變化**：收盤價、RSI、MA20 距離與 20 日波動率的近期變化。
4. **同業脈絡**：以當日漲跌、52 週位置與量能倍率呈現相對排名；資料不足時直接標示無法比較。

研究摘要由 [`src/research_brief.py`](src/research_brief.py) 產生。它是純函式，不讀寫檔案、不發送網路請求，也不依賴 Streamlit，因此能以固定資料直接測試。

## 研究工作流

```text
Market history + company context
            |
            v
Data quality checks and fallback state
            |
            v
Explainable evidence: trend / momentum / participation / risk
            |
            v
Change summary + peer context
            |
            v
Streamlit research workspace
```

完整行為與狀態定義見 [docs/research-workflow.md](docs/research-workflow.md)。

## 資料來源與降級

| 資料 | 主要來源 | 用途 | 無法取得時的行為 |
| --- | --- | --- | --- |
| 台股與美股歷史行情 | yfinance | OHLCV、K 線、均線、RSI、成交量 | 使用明確標示的 `sample data` |
| 上市公司清單與公司脈絡 | TWSE OpenAPI | 台股名稱、類別與公司資料 | 保留可用本機資料，並顯示來源狀態 |
| 異常偵測展示資料 | 本機資料流程 | 特徵工程、Z-score 與 Isolation Forest 展示 | 使用可重現的 sample pipeline |

資料狀態會分為 `ready`、`caution`、`unavailable`。技術證據只在至少有 20 筆有效收盤價時才產生；若資料不足、欄位缺失或使用 fallback，頁面會直接揭露限制。

## 系統架構

- `src/market_api.py`：市場資料、TWSE 來源、fallback 與技術指標。
- `src/research_brief.py`：可測試的資料可信度、證據、變化與同業脈絡邏輯。
- `app.py`：Streamlit 介面、深淺主題、圖表與可及性樣式。
- `run_all.py`：可重現的 sample data、前處理、特徵、模型評估與 smoke test 流程。
- `tests/`：資料流程、前端契約、Streamlit runtime、模型 fallback 與安全行為測試。

### Local Run

```powershell
.venv\Scripts\python.exe run_all.py --mode sample
.venv\Scripts\python.exe -m streamlit run app.py --server.port 8765
```

Windows 可直接執行 `run_project.bat`；它會印出專案路徑與固定網址 `http://localhost:8765`。

## 品質驗證

本專案將可靠性視為產品功能的一部分：

- `pytest` 與 Streamlit `AppTest` 覆蓋資料流程與主要互動。
- `run_all.py --mode sample` 會完成資料、特徵、模型、評估與 smoke test。
- `Bandit` 掃描 Python 安全問題，`pip-audit` 檢查已知依賴漏洞。
- GitHub Actions 在 push 與 pull request 執行安全檢查；Dependabot 追蹤 Python 與 Actions 更新。
- `.gitignore` 排除憑證、原始資料、處理後資料、模型、快取、報表、日誌與本機環境。

## 限制與不做的事

本專案不提供買賣建議、目標價、保證式評分或報酬預測。技術指標僅描述可觀察的價格與成交量狀態，不能代表因果關係或未來結果。

yfinance 與 TWSE OpenAPI 的可用性、交易時段與資料延遲會影響畫面內容；當系統使用 fallback 或 sample data 時，研究摘要會顯示警示。此專案不包含帳號、投組同步、資料庫或 LLM 生成投資結論，刻意將範圍限制在可驗證的資料產品能力。

## Interview Talking Points

- 為什麼不以單一「健診分數」作為核心？因為資料品質、證據來源與不確定性比看似精準的分數更能支持負責任的研究。
- 如何處理外部來源失敗？以來源狀態與 sample fallback 保持可操作，同時把降級狀態公開顯示。
- 如何讓分析邏輯可驗證？研究摘要拆成沒有 UI 或網路副作用的純模組，使用 deterministic pandas fixtures 測試短資料、缺欄位、fallback 與同業不足情境。
- 為什麼保留異常偵測頁但不混在個股頁？兩者服務不同問題：個股頁支援可解釋研究，異常頁展示資料工程與模型工作流。
- 公開倉庫如何維持可信度？只追蹤重現與理解所需的程式、測試、公開範例資料與文件；執行產物與私密資料一律排除。
## Research Snapshot

Each stock detail can produce two offline exports from the exact research context currently shown in the dashboard:

- **JSON** is a machine-readable contract for inspection, automation, or future comparison.
- **Printable HTML** is a self-contained report that can be opened or printed without the dashboard.

Every export includes a `snapshot_id`, market `as_of_date`, capture timestamp, source label, data-quality warnings, derived evidence, change summary, peer context, and an SHA-256 fingerprint of the normalised OHLCV input. The `snapshot_id` is calculated from canonical research content and deliberately excludes the capture timestamp, so equal inputs produce the same ID.

Snapshots are generated in memory and downloaded by the browser. The application does not create a cloud record, account, database row, or shareable public URL. Raw OHLCV rows are not embedded in either export; the provenance fingerprint keeps the report small while making the exact input dataset auditable. A `sample data`, cache, or unavailable source is retained as an explicit warning in both formats.
