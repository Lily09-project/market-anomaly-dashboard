import { useContext, useEffect, useState } from "react";
import { LoaderContext, useDataset, useDocumentTitle } from "../app/hooks";
import { ScrollRegion } from "../components/ScrollRegion";
import { Gate } from "../components/States";
import { formatPercent } from "../lib/format";
import type { DataFiles, Events, Manifest, Provenance, Regimes } from "../lib/types";
import "./DataTrust.css";

const FILES: (keyof DataFiles)[] = ["overview.json", "regimes.json", "events.json", "backtest.json", "stress.json", "provenance.json"];

type Check = { file: string; status: "pending" | "ok" | "failed"; hash?: string };

function useIntegrityChecks(): { manifest: Manifest | null; checks: Check[] } {
  const loader = useContext(LoaderContext);
  const [manifest, setManifest] = useState<Manifest | null>(null);
  const [checks, setChecks] = useState<Check[]>(FILES.map((file) => ({ file, status: "pending" })));
  useEffect(() => {
    if (!loader) return;
    let alive = true;
    loader.manifest().then((m) => alive && setManifest(m));
    FILES.forEach((file, i) => {
      loader.load(file).then(
        () => alive && setChecks((prev) => prev.map((c, j) => (j === i ? { ...c, status: "ok" } : c))),
        () => alive && setChecks((prev) => prev.map((c, j) => (j === i ? { ...c, status: "failed" } : c))),
      );
    });
    return () => {
      alive = false;
    };
  }, [loader]);
  return { manifest, checks: checks.map((c) => ({ ...c, hash: manifest?.files[c.file] })) };
}

function Trust({ provenance, regimes, events }: { provenance: Provenance; regimes: Regimes; events: Events }) {
  const { manifest, checks } = useIntegrityChecks();
  const passed = checks.filter((c) => c.status === "ok").length;
  const v = events.validation;
  return (
    <div className="stack">
      <header>
        <span className="eyebrow">資料工程</span>
        <h1>資料可信度</h1>
        <p className="lede">
          {provenance.is_simulated
            ? "展示站使用固定種子的合成行情：每次重跑都得到位元組完全相同的結果，而且我們知道「正確答案」，因此能檢查每個方法是否真的找得到它。"
            : provenance.provider === "finmind"
              ? "網站資料來自 FinMind 免登入公開 API 的臺股日行情快照；資料不是即時報價，涵蓋範圍與指紋列於下方。"
              : "這份資料來自設定的市場資料來源，以下是它的指紋。"}
        </p>
      </header>

      <p className="notice">{provenance.disclaimer}</p>

      <section className="grid grid-3">
        <div className="card">
          <span className="stat-label">資料來源</span>
          <p className="stat-value" data-testid="data-source">
            {provenance.is_simulated ? "合成資料" : provenance.data_source}
          </p>
          <span className="muted small">
            {provenance.is_simulated
              ? `測試種子 ${provenance.seed}`
              : provenance.provider === "finmind"
                ? `公開歷史日資料 · 非即時 · 排除零成交 ${provenance.source_quality?.excluded_no_trade_rows ?? 0} 筆`
                : "公開歷史日資料 · 非即時"}
          </span>
        </div>
        <div className="card">
          <span className="stat-label">涵蓋範圍</span>
          <p className="stat-value">{provenance.symbols.length} 檔</p>
          <span className="muted small">
            {provenance.range.start} 至 {provenance.range.end}，{provenance.trading_days} 個交易日
          </span>
        </div>
        <div className="card">
          <span className="stat-label">瀏覽器端完整性驗證</span>
          <p className="stat-value" data-testid="integrity-summary">
            {passed}/{checks.length}
          </p>
          <span className="muted small">以 Web Crypto 重新計算 SHA-256 並與 manifest 比對</span>
        </div>
      </section>

      <section className="card">
        <h2>完整性檢查</h2>
        <ScrollRegion label="完整性檢查結果">
          <table data-testid="integrity-table">
            <thead>
              <tr>
                <th scope="col">檔案</th>
                <th scope="col">狀態</th>
                <th scope="col">SHA-256（schema {manifest?.schema_version ?? "—"}）</th>
              </tr>
            </thead>
            <tbody>
              {checks.map((c) => (
                <tr key={c.file}>
                  <th scope="row" className="mono">
                    {c.file}
                  </th>
                  <td>
                    <span className={`badge check-${c.status}`}>{c.status === "ok" ? "✓ 相符" : c.status === "failed" ? "✕ 不符" : "驗證中"}</span>
                  </td>
                  <td className="mono hash">{c.hash ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
        <dl className="fingerprints">
          <dt>輸入資料 SHA-256</dt>
          <dd className="mono" data-testid="input-sha">
            {provenance.input_sha256}
          </dd>
        </dl>
      </section>

      {provenance.is_simulated && (
        <section className="card" aria-labelledby="truth-title">
          <h2 id="truth-title">已知答案與驗證結果</h2>
          <p>合成資料刻意放進三種可驗證的結構。分析程式不知道答案，答案只用來評分。</p>
          <ScrollRegion label="已知答案">
            <table data-testid="truth-table">
              <thead>
                <tr>
                  <th scope="col">放進去的結構</th>
                  <th scope="col">方法找回了多少</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">一條全市場的狀態鏈（平穩／震盪／高波動，各自持續數十天）</th>
                  <td>
                    HMM 還原準確率：
                    {Object.entries(regimes.symbols)
                      .filter(([, r]) => r.accuracy !== null)
                      .map(([symbol, r]) => `${symbol} ${formatPercent(r.accuracy, 0)}`)
                      .join("、")}
                  </td>
                </tr>
                <tr>
                  <th scope="row">
                    每檔 {v?.truth_rebound.jumps_per_stock ?? "—"} 個跳空；負向跳空後連續 {v?.truth_rebound.days ?? "—"} 天各多 {formatPercent(v?.truth_rebound.per_day ?? null, 1)}
                  </th>
                  <td>
                    偵測召回率 {formatPercent(v?.recall ?? null, 0)}、精確率 {formatPercent(v?.precision ?? null, 0)}；事件研究找到的反彈見「異常事件」頁
                  </td>
                </tr>
                <tr>
                  <th scope="row">一條報酬去除平均值的隨機漫步（對照組）</th>
                  <td>
                    BIC 選 {regimes.symbols.RANDOM?.bic_choice ?? "—"} 個狀態、異常誤報 {events.control_events} 天；回測的 PBO 見「誠實回測」頁
                  </td>
                </tr>
              </tbody>
            </table>
          </ScrollRegion>
        </section>
      )}

      <section className="card method" id="methods">
        <h2>方法與限制</h2>
        {!provenance.is_simulated && provenance.provider === "finmind" && (
          <section aria-label="價格還原基準">
            <h3>價格還原基準</h3>
            <p>0050 已依官方公告還原 2025-06-18 的 1 拆 4：分割前 OHLC 除以 4、成交股數乘以 4，原始下載檔保持不變。分析使用還原後價格；未再投入現金股息，不是含息總報酬，其他公司行動仍可能影響結果。</p>
          </section>
        )}
        <h3>市場狀態（隱藏馬可夫模型）</h3>
        <p>
          以 numpy 自行實作高斯 HMM：縮放的前向後向演算法（避免數值下溢）、Baum-Welch 估計（每次疊代對數概似不遞減）、多組種子初始化取最佳、Viterbi 解碼，並依波動排序狀態。跳空日先以 60 日穩健 z 分數排除，視為缺值。以 BIC 比較 1–3 個狀態。
        </p>
        <h3>異常事件研究</h3>
        <p>異常偵測先保留 252 個交易日暖機，之後每 63 日只用此前最多 504 日重估 HMM，對未參與擬合的下一區段計算一步預測 z 分數；暖機期不評分。回顧性的全期間 HMM 圖不參與異常偵測；異常報酬採平均調整模型，信賴區間以重抽事件的 bootstrap 計算。</p>
        <h3>誠實回測</h3>
        <p>
          均線交叉（只做多或空手、每次換倉 0.1% 成本），部位以當日收盤決定、賺取次日報酬，並以截短資料重跑檢查前視偏誤。Walk-forward（2 年訓練、半年測試、不重疊）、CSCV 計算 PBO（Bailey 等人，2017）、Deflated Sharpe Ratio（Bailey 與 López de Prado，2014）。
        </p>
        <h3>壓力測試</h3>
        <p>區塊 bootstrap 在 Web Worker 中執行，使用與 Python 參考實作逐位相同的 mulberry32 亂數；VaR 為損失分位數，CVaR 為超過 VaR 的平均損失。</p>
        <h3>不應該怎麼用</h3>
        <ul>
          <li>不是投資建議，也不是交易訊號；測試用合成資料不代表真實市場表現。</li>
          <li>回測忽略滑價、流動性、稅與融資限制；樣本外表現差，正是這一頁想教的事。</li>
          <li>VaR 只描述歷史報酬重組後的分布，無法涵蓋歷史上沒出現過的危機。</li>
        </ul>
      </section>

      <section className="card">
        <h2>參考與重現方式</h2>
        <ul className="sources">
          {provenance.sources.map((s) => (
            <li key={s.url}>
              <a href={s.url} target="_blank" rel="noopener noreferrer">
                {s.label}
                <span className="visually-hidden">（在新分頁開啟）</span>
              </a>
            </li>
          ))}
        </ul>
        <p>
          <code>python run_all.py --mode sample</code> 只產生可重現的測試資料；正式網站使用上列公開歷史行情，部署時若來源不可用會停止，不以合成資料替代。
        </p>
      </section>
    </div>
  );
}

export default function DataTrust() {
  useDocumentTitle("資料可信度");
  const provenance = useDataset("provenance.json");
  const regimes = useDataset("regimes.json");
  const events = useDataset("events.json");
  return (
    <div className="page">
      <Gate<[Provenance, Regimes, Events]> states={[provenance, regimes, events]}>{(p, r, e) => <Trust provenance={p} regimes={r} events={e} />}</Gate>
    </div>
  );
}
