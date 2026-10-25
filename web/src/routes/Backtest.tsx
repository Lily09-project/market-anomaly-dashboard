import type { CSSProperties } from "react";
import { useDataset, useDocumentTitle, useRoute } from "../app/hooks";
import { ChartFrame, DivergingBars, Histogram, Legend, LineChart } from "../components/charts";
import { pickSymbol, SymbolPicker } from "../components/Common";
import { ScrollRegion } from "../components/ScrollRegion";
import { Gate } from "../components/States";
import { formatNumber, formatPercent } from "../lib/format";
import { heatmap, rankCorrelation, sampledDates } from "../lib/market";
import type { Route } from "../lib/router";
import { histogram } from "../lib/stress";
import type { Backtest, BacktestResult, Overview } from "../lib/types";
import "./Backtest.css";

type BacktestRoute = Extract<Route, { name: "backtest" }>;

function pboVerdict(pbo: number): { tone: string; text: string } {
  if (pbo >= 0.5) return { tone: "bad", text: "樣本內冠軍有一半以上的機會在樣本外落到後段班：這套參數搜尋基本上是在擬合雜訊。" };
  if (pbo >= 0.25) return { tone: "warn", text: "相當比例的切分中，樣本內冠軍在樣本外表現平庸：過度擬合的風險不小。" };
  return { tone: "good", text: "樣本內表現好的參數，在樣本外多半仍維持前段：選參數的過程大致可靠。" };
}

function HeatTable({ result, values, title, selected, onSelect, testId }: { result: BacktestResult; values: number[]; title: string; selected: number; onSelect: (i: number) => void; testId: string }) {
  const rows = heatmap(result, values);
  const extent = Math.max(...values.map(Math.abs), 0.01);
  return (
    <ScrollRegion label={title}>
      <table className="heat" data-testid={testId}>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">短 \ 長均線</th>
            {result.slow.map((s) => (
              <th scope="col" key={s}>
                {s}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={result.fast[r]}>
              <th scope="row">{result.fast[r]}</th>
              {row.map((cell, c) =>
                cell ? (
                  <td key={c} style={{ "--v": cell.value / extent } as CSSProperties} data-sign={cell.value >= 0 ? "pos" : "neg"}>
                    <button
                      type="button"
                      aria-pressed={selected === cell.index}
                      aria-label={`短均線 ${cell.fast}、長均線 ${cell.slow}：Sharpe ${formatNumber(cell.value, 2)}${cell.index === result.best_is ? "（樣本內最佳）" : ""}`}
                      onClick={() => onSelect(cell.index)}
                    >
                      {formatNumber(cell.value, 2)}
                      {cell.index === result.best_is && <span aria-hidden="true">★</span>}
                    </button>
                  </td>
                ) : (
                  <td key={c} className="heat-empty" aria-label="不適用（短均線需小於長均線）">
                    ·
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </ScrollRegion>
  );
}

function BacktestView({ overview, backtest, route }: { overview: Overview; backtest: Backtest; route: BacktestRoute }) {
  const [, navigate] = useRoute();
  const symbol = pickSymbol(overview, route.symbol);
  const result = backtest.symbols[symbol]!;
  const selected = route.cell !== undefined && route.cell < result.grid.length ? route.cell : result.best_is;
  const [fast, slow] = result.grid[selected]!;
  const verdict = pboVerdict(result.pbo);
  const rho = rankCorrelation(result.is_sharpe, result.oos_sharpe);
  const equityDates = sampledDates(overview.dates, result.equity.start, result.equity.step, result.equity.walk_forward.length);
  const logitBins = histogram(result.logits, 12);
  const select = (cell: number) => navigate({ ...route, symbol, cell }, { replace: true });

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">回測過度擬合</span>
        <h1>誠實回測實驗室</h1>
        <p className="lede">
          試夠多組參數，總有一組在歷史上看起來很賺錢。這一頁對 {result.grid.length} 組均線交叉策略做網格搜尋，再用三種方法檢查那個「最佳參數」是真的有效，還是只是運氣。
        </p>
      </header>

      <SymbolPicker overview={overview} value={symbol} route={{ ...route, symbol, cell: undefined }} />

      <section className="kpis" aria-label="過度擬合檢定">
        <div className="card kpi">
          <span className="stat-label">回測過度擬合機率（PBO）</span>
          <span className="stat-value" data-testid="pbo">
            {formatPercent(result.pbo, 0)}
          </span>
          <span className="tag" data-tone={verdict.tone}>
            {result.pbo >= 0.5 ? "高度過擬合" : result.pbo >= 0.25 ? "需要警惕" : "較可信"}
          </span>
        </div>
        <div className="card kpi">
          <span className="stat-label">樣本內最佳 → walk-forward 樣本外</span>
          <span className="stat-value" data-testid="sharpe-drop">
            {formatNumber(result.full_sharpe[result.best_full], 2)} → {formatNumber(result.oos_sharpe_stitched, 2)}
          </span>
          <span className="muted small">同期間買進持有 Sharpe {formatNumber(result.buy_hold_sharpe_oos, 2)}</span>
        </div>
        <div className="card kpi">
          <span className="stat-label">Deflated Sharpe Ratio</span>
          <span className="stat-value" data-testid="dsr">
            {formatPercent(result.dsr.dsr, 0)}
          </span>
          <span className="muted small">
            考慮試了 {result.dsr.trials} 組之後，最佳 Sharpe {formatNumber(result.dsr.sharpe, 2)} 要超過運氣門檻 {formatNumber(result.dsr.benchmark_sharpe, 2)} 的信心
          </span>
        </div>
      </section>
      <p className="callout">{verdict.text}</p>

      <section className="card">
        <h2>同一組參數，樣本內與樣本外判若兩人</h2>
        <p className="muted small">
          前 60%（至 {result.split_date}）為樣本內、後 40% 為樣本外。點選任一格看看它在兩段的表現；★ 是樣本內最佳，它在樣本外排第 {result.best_is_oos_rank} 名（共 {result.grid.length} 組）。兩段排名的 Spearman 相關係數為{" "}
          <strong data-testid="rank-correlation">{formatNumber(rho, 2)}</strong>。
        </p>
        <div className="heat-pair">
          <HeatTable result={result} values={result.is_sharpe} title="樣本內 Sharpe" selected={selected} onSelect={select} testId="heat-is" />
          <HeatTable result={result} values={result.oos_sharpe} title="樣本外 Sharpe" selected={selected} onSelect={select} testId="heat-oos" />
        </div>
        <p className="selected-cell" aria-live="polite" data-testid="selected-cell">
          已選 {fast}／{slow} 日均線：樣本內 Sharpe {formatNumber(result.is_sharpe[selected], 2)}、樣本外 {formatNumber(result.oos_sharpe[selected], 2)}、全期 {formatNumber(result.full_sharpe[selected], 2)}。
        </p>
      </section>

      <section className="split">
        <div className="card">
          <ChartFrame
            title="Walk-forward：每段只用過去選參數"
            summary={result.walk_forward.map((f) => `${f.test_start} 起用 ${f.params.join("/")}，樣本外 Sharpe ${formatNumber(f.test_sharpe, 2)}`).join("；")}
            table={
              <table data-testid="folds-table">
                <thead>
                  <tr>
                    <th scope="col">測試期間</th>
                    <th scope="col">選出的參數</th>
                    <th scope="col">訓練 Sharpe</th>
                    <th scope="col">測試 Sharpe</th>
                  </tr>
                </thead>
                <tbody>
                  {result.walk_forward.map((f) => (
                    <tr key={f.test_start}>
                      <th scope="row">
                        {f.test_start}～{f.test_end}
                      </th>
                      <td>{f.params.join("／")}</td>
                      <td className="num">{formatNumber(f.train_sharpe, 2)}</td>
                      <td className="num">{formatNumber(f.test_sharpe, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          >
            <DivergingBars rows={result.walk_forward.map((f) => ({ key: f.test_start, label: `${f.test_start.slice(0, 7)} 測試`, value: f.test_sharpe }))} format={(v) => formatNumber(v, 2)} />
          </ChartFrame>
          <p className="muted small">每一段用前 2 年訓練、接下來半年測試，測試窗彼此不重疊；訓練 Sharpe 平均 {formatNumber(result.walk_forward.reduce((s, f) => s + f.train_sharpe, 0) / Math.max(result.walk_forward.length, 1), 2)}，測試卻只有 {formatNumber(result.oos_sharpe_stitched, 2)}。</p>
        </div>
        <div className="card">
          <ChartFrame
            title="Walk-forward 淨值 vs. 買進持有（樣本外）"
            summary={`從 ${result.equity.start} 起，walk-forward 淨值終值 ${formatNumber(result.equity.walk_forward.at(-1), 2)}，買進持有 ${formatNumber(result.equity.buy_hold.at(-1), 2)}。`}
            table={
              <table>
                <thead>
                  <tr>
                    <th scope="col">日期</th>
                    <th scope="col">Walk-forward</th>
                    <th scope="col">買進持有</th>
                  </tr>
                </thead>
                <tbody>
                  {equityDates
                    .map((d, i) => ({ d, i }))
                    .filter(({ i }) => i % 4 === 0)
                    .map(({ d, i }) => (
                      <tr key={`${d}-${i}`}>
                        <th scope="row">{d}</th>
                        <td className="num">{formatNumber(result.equity.walk_forward[i], 3)}</td>
                        <td className="num">{formatNumber(result.equity.buy_hold[i], 3)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            }
          >
            <LineChart
              series={[
                { key: "wf", label: "Walk-forward", values: result.equity.walk_forward, tone: 1 },
                { key: "bh", label: "買進持有", values: result.equity.buy_hold, tone: 2 },
              ]}
              labels={equityDates}
              reference={{ value: 1, label: "起點" }}
              format={(v) => formatNumber(v, 2)}
              height={220}
            />
          </ChartFrame>
          <Legend
            items={[
              { key: "wf", label: "Walk-forward（含每次換倉 0.1% 成本）", tone: 1 },
              { key: "bh", label: "買進持有", tone: 2 },
            ]}
          />
        </div>
      </section>

      <section className="split">
        <div className="card">
          <ChartFrame
            title="CSCV：樣本內冠軍在樣本外的相對排名（logit）"
            summary={`${result.logits.length} 種切分中，${formatPercent(result.pbo, 0)} 的 logit ≤ 0，也就是冠軍在樣本外落到中位數以下。`}
            table={
              <table>
                <thead>
                  <tr>
                    <th scope="col">logit 區間</th>
                    <th scope="col">切分數</th>
                  </tr>
                </thead>
                <tbody>
                  {logitBins.map((b) => (
                    <tr key={b.lo}>
                      <th scope="row">
                        {formatNumber(b.lo, 2)}～{formatNumber(b.hi, 2)}
                      </th>
                      <td className="num">{b.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          >
            <Histogram bins={logitBins} format={(v) => formatNumber(v, 1)} highlight={0} />
          </ChartFrame>
          <p className="muted small">把資料切成 10 塊，取其中 5 塊當樣本內、其餘當樣本外，共 252 種組合。紅色是冠軍「掉到後段」的切分，它們的比例就是 PBO。</p>
        </div>
        <div className="card">
          <h2>防止偷看未來</h2>
          <p>
            <span className="tag" data-tone="good" data-testid="causal-check">
              前視偏誤檢查：通過
            </span>
          </p>
          <p>
            每個交易日的部位只用當天收盤以前的價格決定，並賺取下一天的報酬。匯出前會把價格序列截短 8 次重跑策略，只要任何一天的歷史部位因為「拿掉未來」而改變，管線就會失敗（測試裡刻意放了一個偷看明天價格的策略，確認它會被抓到）。
          </p>
          <h3>最佳參數的風險</h3>
          <p>
            全期最佳 {result.grid[result.best_full]!.join("／")} 日均線的最大回撤 <strong>{formatPercent(result.max_drawdown_best, 1)}</strong>，每次換倉成本 {formatPercent(result.cost_per_trade, 1)}。
          </p>
        </div>
      </section>
    </div>
  );
}

export default function BacktestPage({ route }: { route: BacktestRoute }) {
  useDocumentTitle("誠實回測實驗室");
  const overview = useDataset("overview.json");
  const backtest = useDataset("backtest.json");
  return (
    <div className="page">
      <Gate<[Overview, Backtest]> states={[overview, backtest]}>{(o, b) => <BacktestView overview={o} backtest={b} route={route} />}</Gate>
    </div>
  );
}
