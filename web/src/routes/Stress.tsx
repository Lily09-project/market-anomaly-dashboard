import { useEffect, useState } from "react";
import { useDataset, useDocumentTitle, useRoute } from "../app/hooks";
import { ChartFrame, FanChart, Histogram } from "../components/charts";
import { pickSymbol } from "../components/Common";
import { PageHead } from "../components/PageHead";
import { Gate } from "../components/States";
import { SymbolBar } from "../components/SymbolBar";
import { formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import { STRESS_LIMITS, type Route } from "../lib/router";
import { histogramAround, logReturns, type StressSummary } from "../lib/stress";
import type { Overview, Stress, StressParams } from "../lib/types";
import { useStressWorker } from "../workers/useStressWorker";
import "./Stress.css";

type StressRoute = Extract<Route, { name: "stress" }>;
const HORIZONS = [20, 60, 120, 250];
const PATHS = [500, 2000, 5000, 10000, 20000];

/** A shared link may carry any in-range value; list it so the select shows what was simulated. */
function withValue(options: number[], value: number): number[] {
  return options.includes(value) ? options : [...options, value].sort((a, b) => a - b);
}

interface Result {
  key: string;
  symbol: string;
  params: StressParams;
  var95Daily: number;
  summary: StressSummary;
}

function StressView({ overview, stress, route }: { overview: Overview; stress: Stress; route: StressRoute }) {
  const [, navigate] = useRoute();
  const symbol = pickSymbol(overview, route.symbol);
  const series = overview.symbols.find((s) => s.symbol === symbol)!;
  const params = {
    horizon: route.horizon ?? stress.defaults.horizon,
    block: route.block ?? stress.defaults.block,
    paths: route.paths ?? stress.defaults.paths,
    seed: stress.defaults.seed,
  };
  const key = `${symbol}-${params.horizon}-${params.block}-${params.paths}-${params.seed}`;
  const { run, cancel, running, progress, error } = useStressWorker();
  const [result, setResult] = useState<Result | null>(null);
  const [requested, setRequested] = useState(key);
  const update = (patch: Partial<StressRoute>) => navigate({ ...route, symbol, ...patch }, { replace: true });

  // Run on first visit or an explicit request; result labels retain that request.
  useEffect(() => {
    let alive = true;
    run(logReturns(series.close), params).then(
      (summary) => alive && setResult({ key, symbol, params: { ...params }, var95Daily: series.var95_daily, summary }),
      () => undefined,
    );
    return () => {
      alive = false;
    };
    // `key` captures every input; params/series are derived from it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested]);

  const stale = result !== null && result.key !== key;
  const summary = result?.summary;
  const displayed = result ?? { symbol, params, var95Daily: series.var95_daily };
  const bins = summary ? histogramAround(summary.terminal, 30, -summary.var95) : [];

  return (
    <div className="analysis">
      <div className="analysis-rail">
        {stale && <p className="notice is-lead">設定已變更，下方仍是舊設定的結果。</p>}
        <section className="card stress-controls is-lead" aria-label="模擬設定">
          <label className="field">
            <span className="label">模擬天數</span>
            <select className="input" value={params.horizon} onChange={(e) => update({ horizon: Number(e.target.value) })}>
              {withValue(HORIZONS, params.horizon).map((h) => (
                <option key={h} value={h}>
                  {h} 個交易日
                </option>
              ))}
            </select>
          </label>
          <label className="field" htmlFor="stress-block">
            <span className="label">
              區塊長度 <output data-testid="block-value">{params.block}</output> 天
            </span>
            <input
              id="stress-block"
              type="range"
              min={STRESS_LIMITS.block[0]}
              max={STRESS_LIMITS.block[1]}
              value={params.block}
              onChange={(e) => update({ block: Number(e.target.value) })}
              aria-valuetext={`${params.block} 天`}
            />
          </label>
          <label className="field">
            <span className="label">路徑數</span>
            <select className="input" value={params.paths} onChange={(e) => update({ paths: Number(e.target.value) })}>
              {withValue(PATHS, params.paths).map((p) => (
                <option key={p} value={p}>
                  {p.toLocaleString("zh-TW")}
                </option>
              ))}
            </select>
          </label>
          <div className="stress-actions">
            {running ? (
              <button type="button" className="btn" onClick={cancel}>
                取消
              </button>
            ) : (
              <button type="button" className="btn btn-primary" onClick={() => setRequested(`${key}#${Date.now()}`)} disabled={!stale && result !== null}>
                {result === null ? "開始模擬" : stale ? "以新設定重新模擬" : "已是最新結果"}
              </button>
            )}
            <span className="muted small">種子 {params.seed}：同一組設定每次結果完全相同</span>
          </div>
          {running && (
            <div className="progress-row">
              <progress max={1} value={progress} aria-label="模擬進度" />
              <span className="small">{formatPercent(progress, 0)}</span>
            </div>
          )}
          {error && <p role="alert">模擬失敗：{error}</p>}
        </section>
        {summary && (
          <section className="card" aria-label="風險指標" data-testid="risk-kpis">
            <dl className="readout">
              <div>
                <dt>VaR 95%</dt>
                <dd>
                  <span className="stat-value" data-testid="var95">
                    {formatPercent(summary.var95, 1)}
                  </span>
                  <span className="muted small">{displayed.params.horizon} 天後，有 5% 的機會虧損超過這個幅度</span>
                </dd>
              </div>
              <div>
                <dt>CVaR 95%</dt>
                <dd>
                  <span className="stat-value" data-testid="cvar95">
                    {formatPercent(summary.cvar95, 1)}
                  </span>
                  <span className="muted small">最糟 5% 情境的平均虧損（永遠 ≥ VaR）</span>
                </dd>
              </div>
              <div>
                <dt>VaR／CVaR 99%</dt>
                <dd>
                  <span className="stat-value">
                    {formatPercent(summary.var99, 1)}／{formatPercent(summary.cvar99, 1)}
                  </span>
                  <span className="muted small">百分之一的極端情境</span>
                </dd>
              </div>
            </dl>
          </section>
        )}
      </div>
      <div className="analysis-main">
        {summary ? (
          <div className="stress-charts is-hero" data-testid="stress-charts">
            <section className="card">
              <ChartFrame
                title={`${displayed.symbol} 未來 ${displayed.params.horizon} 個交易日的報酬扇形圖`}
                summary={`中位數路徑最後為 ${formatSignedPercent(summary.fan["0.5"]!.at(-1) ?? null)}；90% 的路徑落在 ${formatSignedPercent(summary.fan["0.05"]!.at(-1) ?? null)} 到 ${formatSignedPercent(summary.fan["0.95"]!.at(-1) ?? null)} 之間。`}
                table={
                  <table data-testid="fan-table">
                    <thead>
                      <tr>
                        <th scope="col">第幾天</th>
                        <th scope="col">5%</th>
                        <th scope="col">25%</th>
                        <th scope="col">中位數</th>
                        <th scope="col">75%</th>
                        <th scope="col">95%</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.fan["0.5"]!.map((_, day) =>
                        day % 5 === 4 || day === displayed.params.horizon - 1 ? (
                          <tr key={day}>
                            <th scope="row">{day + 1}</th>
                            {["0.05", "0.25", "0.5", "0.75", "0.95"].map((q) => (
                              <td key={q} className="num">
                                {formatSignedPercent(summary.fan[q]![day] ?? null)}
                              </td>
                            ))}
                          </tr>
                        ) : null,
                      )}
                    </tbody>
                  </table>
                }
              >
                <FanChart fan={summary.fan} format={(v) => formatPercent(v, 0)} />
              </ChartFrame>
              <p className="muted small">深色帶是 25%–75%，淺色帶是 5%–95%，線是中位數。</p>
            </section>
            <section className="card">
              <ChartFrame
                title="期末報酬分布"
                summary={`${displayed.params.paths.toLocaleString("zh-TW")} 條路徑的期末報酬；紅色是超過 VaR 95% 的虧損尾端。`}
                table={
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">報酬區間</th>
                        <th scope="col">路徑數</th>
                      </tr>
                    </thead>
                    <tbody>
                      {bins.map((b) => (
                        <tr key={b.lo}>
                          <th scope="row">
                            {formatPercent(b.lo, 1)}～{formatPercent(b.hi, 1)}
                          </th>
                          <td className="num">{b.count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                }
              >
                <Histogram bins={bins} format={(v) => formatPercent(v, 0)} highlight={-summary.var95} />
              </ChartFrame>
              <p className="muted small">
                對照：歷史單日 VaR 95% 為 {formatPercent(displayed.var95Daily, 2)}。若報酬獨立，{displayed.params.horizon} 天的 VaR 約為它的 √{displayed.params.horizon} ≈{" "}
                {formatNumber(Math.sqrt(displayed.params.horizon), 1)} 倍；區塊越長，越能保留連續下跌的風險。
              </p>
            </section>
          </div>
        ) : (
          <p className="state state-empty is-hero" role="status">{running ? "模擬中…" : "尚無模擬結果，請開始或重新執行。"}</p>
        )}
      </div>
    </div>
  );
}

export default function StressPage({ route }: { route: StressRoute }) {
  useDocumentTitle("壓力測試");
  const overview = useDataset("overview.json");
  const stress = useDataset("stress.json");
  return (
    <div className="page">
      <PageHead eyebrow="瀏覽器端 Monte Carlo" title="壓力測試">
        把歷史日報酬切成連續的區塊，隨機抽取、接起來，模擬未來可能的路徑。用區塊而不是單日抽樣，是為了保留波動聚集——壞日子往往連著來。整個模擬在 Web Worker 裡執行，不會卡住頁面。
      </PageHead>
      <SymbolBar route={route} />
      <Gate<[Overview, Stress]> states={[overview, stress]}>{(o, s) => <StressView overview={o} stress={s} route={route} />}</Gate>
    </div>
  );
}
