import { useEffect, useState } from "react";
import { useDataset, useDocumentTitle, useRoute } from "../app/hooks";
import { ChartFrame, FanChart, Histogram } from "../components/charts";
import { pickSymbol, SymbolPicker } from "../components/Common";
import { Gate } from "../components/States";
import { formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import { STRESS_LIMITS, type Route } from "../lib/router";
import { histogram, logReturns, type StressSummary } from "../lib/stress";
import type { Overview, Stress } from "../lib/types";
import { useStressWorker } from "../workers/useStressWorker";
import "./Stress.css";

type StressRoute = Extract<Route, { name: "stress" }>;
const HORIZONS = [20, 60, 120, 250];
const PATHS = [500, 2000, 5000, 10000, 20000];

interface Result {
  key: string;
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

  // Run once for every new parameter set (including the first visit).
  useEffect(() => {
    let alive = true;
    run(logReturns(series.close), params).then(
      (summary) => alive && setResult({ key, summary }),
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
  const bins = summary ? histogram(summary.terminal, 30) : [];

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">瀏覽器端 Monte Carlo</span>
        <h1>壓力測試</h1>
        <p className="lede">
          把歷史日報酬切成連續的區塊，隨機抽取、接起來，模擬未來可能的路徑。用區塊而不是單日抽樣，是為了保留波動聚集——壞日子往往連著來。整個模擬在 Web Worker 裡執行，不會卡住頁面。
        </p>
      </header>

      <SymbolPicker overview={overview} value={symbol} route={{ ...route, symbol }} />

      <section className="card stress-controls" aria-label="模擬設定">
        <label className="field">
          <span className="label">模擬天數</span>
          <select className="input" value={params.horizon} onChange={(e) => update({ horizon: Number(e.target.value) })}>
            {HORIZONS.map((h) => (
              <option key={h} value={h}>
                {h} 個交易日
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="label">
            區塊長度 <output data-testid="block-value">{params.block}</output> 天
          </span>
          <input
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
            {PATHS.map((p) => (
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

      {stale && <p className="notice">設定已變更，下方仍是舊設定的結果。</p>}

      {summary ? (
        <>
          <section className="kpis" aria-label="風險指標" data-testid="risk-kpis">
            <div className="card kpi">
              <span className="stat-label">VaR 95%</span>
              <span className="stat-value" data-testid="var95">
                {formatPercent(summary.var95, 1)}
              </span>
              <span className="muted small">{params.horizon} 天後，有 5% 的機會虧損超過這個幅度</span>
            </div>
            <div className="card kpi">
              <span className="stat-label">CVaR 95%</span>
              <span className="stat-value" data-testid="cvar95">
                {formatPercent(summary.cvar95, 1)}
              </span>
              <span className="muted small">最糟 5% 情境的平均虧損（永遠 ≥ VaR）</span>
            </div>
            <div className="card kpi">
              <span className="stat-label">VaR／CVaR 99%</span>
              <span className="stat-value">
                {formatPercent(summary.var99, 1)}／{formatPercent(summary.cvar99, 1)}
              </span>
              <span className="muted small">百分之一的極端情境</span>
            </div>
          </section>

          <section className="split">
            <div className="card">
              <ChartFrame
                title={`${symbol} 未來 ${params.horizon} 個交易日的報酬扇形圖`}
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
                        day % 5 === 4 || day === params.horizon - 1 ? (
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
            </div>
            <div className="card">
              <ChartFrame
                title="期末報酬分布"
                summary={`${params.paths.toLocaleString("zh-TW")} 條路徑的期末報酬；紅色是超過 VaR 95% 的虧損尾端。`}
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
                對照：歷史單日 VaR 95% 為 {formatPercent(series.var95_daily, 2)}。若報酬獨立，{params.horizon} 天的 VaR 約為它的 √{params.horizon} ≈{" "}
                {formatNumber(Math.sqrt(params.horizon), 1)} 倍；區塊越長，越能保留連續下跌的風險。
              </p>
            </div>
          </section>
        </>
      ) : (
        <p className="muted">模擬中…</p>
      )}
    </div>
  );
}

export default function StressPage({ route }: { route: StressRoute }) {
  useDocumentTitle("壓力測試");
  const overview = useDataset("overview.json");
  const stress = useDataset("stress.json");
  return (
    <div className="page">
      <Gate<[Overview, Stress]> states={[overview, stress]}>{(o, s) => <StressView overview={o} stress={s} route={route} />}</Gate>
    </div>
  );
}
