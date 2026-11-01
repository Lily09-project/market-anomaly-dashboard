import { useDataset, useDocumentTitle, useRoute } from "../app/hooks";
import { ChartFrame, Legend, LineChart } from "../components/charts";
import { pickSymbol, StateChip, SymbolPicker } from "../components/Common";
import { Gate } from "../components/States";
import { TwsePanel } from "../components/Twse";
import { formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import { drawdowns, mostVolatileState, rollingVolatility, statesByDay } from "../lib/market";
import { PERIOD_DAYS, routeToHash, type Period, type Route } from "../lib/router";
import { logReturns } from "../lib/stress";
import type { Backtest, Events, Overview, Provenance, Regimes, Segment } from "../lib/types";
import "./Home.css";

type HomeRoute = Extract<Route, { name: "home" }>;
const PERIODS: { value: Period; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "3y", label: "近 3 年" },
  { value: "1y", label: "近 1 年" },
];

/** Clip regime segments (return indexes) to a window that starts at price index `from`. */
function clipSegments(segments: Segment[], from: number): Segment[] {
  return segments
    .map(([s, e, state]) => [s + 1 - from, e + 1 - from, state] as Segment)
    .filter(([, e]) => e >= 0)
    .map(([s, e, state]) => [Math.max(s, 0), e, state] as Segment);
}

const JOURNEY: { name: "regimes" | "events" | "backtest" | "stress"; label: string; question: string }[] = [
  { name: "regimes", label: "市場狀態", question: "現在處於哪一種狀態？" },
  { name: "events", label: "異常事件", question: "大漲大跌之後，報酬可以預測嗎？" },
  { name: "backtest", label: "誠實回測", question: "漂亮的回測，是實力還是運氣？" },
  { name: "stress", label: "壓力測試", question: "接下來 60 天，壞情況會虧多少？" },
];

/** Cross-symbol headline computed from the loaded results; the control series is excluded. */
function HeadlineFinding({ overview, regimes, backtest }: { overview: Overview; regimes: Regimes; backtest: Backtest }) {
  const symbols = overview.symbols.filter((s) => !s.is_control && backtest.symbols[s.symbol] && regimes.symbols[s.symbol]).map((s) => s.symbol);
  const n = symbols.length;
  if (n === 0) return null;
  const overfit = symbols.filter((s) => backtest.symbols[s]!.pbo >= 0.5).length;
  const losing = symbols.filter((s) => backtest.symbols[s]!.oos_sharpe_stitched < backtest.symbols[s]!.buy_hold_sharpe_oos).length;
  const stressed = symbols.filter((s) => {
    const r = regimes.symbols[s]!;
    return r.current.state === mostVolatileState(r.vol_annual);
  }).length;
  return (
    <aside className="card headline" aria-labelledby="headline-title" data-testid="headline-finding">
      <span className="stat-label">核心發現 · {n} 檔合計</span>
      <h2 id="headline-title">{overfit * 2 > n ? "多數「漂亮回測」經不起檢驗" : "回測經得起檢驗嗎？"}</h2>
      <dl className="headline-stats">
        <div>
          <dt>回測過度擬合機率（PBO）≥ 50%</dt>
          <dd>
            <strong>{overfit}</strong> / {n} 檔
          </dd>
        </div>
        <div>
          <dt>均線策略樣本外 Sharpe 不如買進持有</dt>
          <dd>
            <strong>{losing}</strong> / {n} 檔
          </dd>
        </div>
        <div>
          <dt>目前處於高波動狀態</dt>
          <dd>
            <strong>{stressed}</strong> / {n} 檔
          </dd>
        </div>
      </dl>
      <a className="headline-link" href={routeToHash({ name: "backtest" })}>
        看回測如何被檢驗 →
      </a>
    </aside>
  );
}

function Dashboard({ overview, regimes, backtest, events, provenance, route }: { overview: Overview; regimes: Regimes; backtest: Backtest; events: Events; provenance: Provenance; route: HomeRoute }) {
  const [, navigate] = useRoute();
  const symbol = pickSymbol(overview, route.symbol);
  const period = route.period ?? "all";
  const series = overview.symbols.find((s) => s.symbol === symbol)!;
  const regime = regimes.symbols[symbol]!;
  const bt = backtest.symbols[symbol]!;
  const days = PERIOD_DAYS[period];
  const from = days === null ? 0 : Math.max(overview.dates.length - days, 0);
  const dates = overview.dates.slice(from);
  const close = series.close.slice(from);
  const returns = logReturns(series.close);
  // Price-aligned: the first price has no return, so it has no volatility either.
  const vol = [null, ...rollingVolatility(returns)].slice(from);
  const dd = drawdowns(close);
  const stripes = clipSegments(regime.segments, from);
  const daysInState = statesByDay(regime.segments, returns.length);
  let streak = 0;
  for (let i = daysInState.length - 1; i >= 0 && daysInState[i] === regime.current.state; i -= 1) streak += 1;
  const negative = events.study.negative;
  const reboundIndex = negative.post_offsets.indexOf(3);
  const analysed = overview.symbols.filter((s) => !s.is_control);
  const split = provenance.price_basis?.splits.find((s) => s.symbol === symbol);

  return (
    <div className="stack">
      <header className="hero">
        <div className="hero-copy">
          <span className="eyebrow">市場狀態實驗室 · 研究用途，非投資建議</span>
          <h1>市場不是一條平滑的曲線，而是幾種「狀態」之間的切換。</h1>
          <p className="lede">
            用隱藏馬可夫模型找出平穩、震盪與高波動三種狀態；檢驗異常日之後是否真的有可預測的報酬；再用過度擬合檢定揭穿「漂亮回測」。每個方法都先在已知答案的合成資料上接受檢驗。
          </p>
          <p className="hero-meta" data-testid="hero-meta">
            {provenance.is_simulated ? "測試用合成資料" : provenance.provider === "finmind" ? "FinMind 臺股日行情" : "市場日資料"} · {analysed.length} 檔 · {provenance.range.start} 至{" "}
            <strong>{provenance.range.end}</strong>（{provenance.trading_days.toLocaleString("zh-TW")} 個交易日，非即時）·{" "}
            <a href={routeToHash({ name: "data" })}>資料來源與驗證</a>
          </p>
        </div>
        <HeadlineFinding overview={overview} regimes={regimes} backtest={backtest} />
      </header>

      <nav className="journey" aria-labelledby="journey-title">
        <h2 id="journey-title" className="journey-title">
          第一次來？照這個順序看
        </h2>
        <ol>
          {JOURNEY.map((step, i) => (
            <li key={step.name}>
              <a href={routeToHash({ name: step.name, symbol })}>
                <span className="journey-step" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="journey-text">
                  <strong>{step.label}</strong>
                  <span>{step.question}</span>
                </span>
              </a>
            </li>
          ))}
        </ol>
      </nav>

      <div className="controls">
        <SymbolPicker overview={overview} value={symbol} route={{ ...route, symbol }} />
        <fieldset className="segmented">
          <legend>期間</legend>
          {PERIODS.map((p) => (
            <label key={p.value}>
              <input type="radio" name="period" value={p.value} checked={period === p.value} onChange={() => navigate({ ...route, symbol, period: p.value }, { replace: true })} />
              <span>{p.label}</span>
            </label>
          ))}
        </fieldset>
      </div>

      {series.is_control && (
        <p className="notice" data-testid="control-notice">
          這是<strong>隨機漫步對照組</strong>：報酬是獨立的雜訊、平均為零。它在這裡是為了檢查方法——任何在這條曲線上「找到」的規律都是假象。
        </p>
      )}

      <section className="kpis" aria-label={`${symbol} 摘要`}>
        <div className="card kpi">
          <span className="stat-label">目前市場狀態</span>
          <StateChip state={regime.current.state} labels={regime.labels} />
          <span className="muted small" data-testid="current-state">
            機率 {formatPercent(regime.current.probability, 0)}，已持續 {streak} 個交易日
          </span>
        </div>
        <div className="card kpi">
          <span className="stat-label">期間價格報酬</span>
          <span className="stat-value" data-testid="total-return">
            {formatSignedPercent(close.at(-1)! / close[0]! - 1)}
          </span>
          <span className="muted small">
            {dates[0]} 起，年化波動 {formatPercent(series.vol_annual, 0)}（全期）
          </span>
        </div>
        <div className="card kpi">
          <span className="stat-label">最大回撤（此期間）</span>
          <span className="stat-value">{formatPercent(Math.min(...dd))}</span>
          <span className="muted small">單日 VaR 95% {formatPercent(series.var95_daily, 2)}、CVaR {formatPercent(series.cvar95_daily, 2)}（全期）</span>
        </div>
      </section>

      <section className="card">
        <ChartFrame
          title={`${symbol} ${series.name} 收盤價與市場狀態`}
          summary={`${dates[0]} 至 ${dates.at(-1)}，收盤價從 ${formatNumber(close[0], 2)} 到 ${formatNumber(close.at(-1), 2)}。背景色帶是 HMM 判定的狀態：${regime.labels.map((l, i) => `${l} 占 ${formatPercent(regime.share[i], 0)}`).join("、")}。`}
          table={
            <table data-testid="price-table">
              <thead>
                <tr>
                  <th scope="col">日期</th>
                  <th scope="col">收盤</th>
                  <th scope="col">狀態</th>
                </tr>
              </thead>
              <tbody>
                {dates
                  .map((d, i) => ({ d, i }))
                  .filter(({ i }) => i % 21 === 0 || i === dates.length - 1)
                  .map(({ d, i }) => {
                    const state = daysInState[from + i - 1];
                    return (
                      <tr key={d}>
                        <th scope="row">{d}</th>
                        <td className="num">{formatNumber(close[i], 2)}</td>
                        <td>{state !== undefined && state >= 0 ? regime.labels[state] : "—"}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          }
        >
          <LineChart series={[{ key: "close", label: "收盤價", values: close, tone: 1 }]} labels={dates} stripes={stripes} format={(v) => formatNumber(v, 0)} />
        </ChartFrame>
        <Legend items={[{ key: "close", label: "收盤價", tone: 1 }, ...regime.labels.map((label, state) => ({ key: label, label, state }))]} />
        <p className="chart-note">
          怎麼看：線是收盤價（元），背景顏色是模型每天判定的狀態，顏色換了就代表狀態切換。
          {split && <> 價格已依官方公告還原 {split.effective_date} 的 1 拆 {split.new_units_per_old} 分割。</>}
        </p>
      </section>

      <section className="split">
        <div className="card">
          <ChartFrame
            title="20 日滾動年化波動率"
            summary={`最新 ${formatPercent(vol.at(-1) ?? null, 0)}；高波動狀態期間明顯升高。`}
            table={
              <table>
                <thead>
                  <tr>
                    <th scope="col">日期</th>
                    <th scope="col">年化波動</th>
                  </tr>
                </thead>
                <tbody>
                  {dates
                    .map((d, i) => ({ d, i }))
                    .filter(({ i }) => i % 21 === 0)
                    .map(({ d, i }) => (
                      <tr key={d}>
                        <th scope="row">{d}</th>
                        <td className="num">{formatPercent(vol[i] ?? null, 1)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            }
          >
            <LineChart series={[{ key: "vol", label: "波動率", values: vol, tone: 2 }]} labels={dates} stripes={stripes} format={(v) => formatPercent(v, 0)} height={200} />
          </ChartFrame>
        </div>
        <div className="card guide">
          <h2>這個標的的研究結論</h2>
          <ul className="findings">
            <li>
              <a href={routeToHash({ name: "regimes", symbol })}>市場狀態</a>：
              {regime.accuracy !== null ? (
                <>與合成資料的真實狀態比對，準確率 <strong>{formatPercent(regime.accuracy, 0)}</strong>。</>
              ) : regime.bic_choice === 1 ? (
                <>BIC 選擇 <strong>1 個狀態</strong>——沒有證據顯示存在不同狀態。</>
              ) : (
                <>BIC 選擇 {regime.bic_choice} 個狀態。</>
              )}
            </li>
            <li>
              <a href={routeToHash({ name: "backtest", symbol })}>誠實回測</a>：均線策略的回測過度擬合機率 <strong>{formatPercent(bt.pbo, 0)}</strong>，walk-forward 樣本外 Sharpe{" "}
              <strong>{formatNumber(bt.oos_sharpe_stitched, 2)}</strong>（樣本內最佳 {formatNumber(bt.full_sharpe[bt.best_full], 2)}）。
            </li>
            <li>
              <a href={routeToHash({ name: "events", symbol })}>異常事件</a>：所有標的合計，負向衝擊後 3 日平均累積異常報酬{" "}
              <strong>{formatSignedPercent(negative.post_car[reboundIndex] ?? null)}</strong>（95% 區間 {formatSignedPercent(negative.post_low[reboundIndex] ?? null)}～
              {formatSignedPercent(negative.post_high[reboundIndex] ?? null)}）。
            </li>
            <li>
              <a href={routeToHash({ name: "stress", symbol })}>壓力測試</a>：在瀏覽器裡用區塊 bootstrap 模擬未來 60 個交易日的可能路徑。
            </li>
          </ul>
        </div>
      </section>

      <TwsePanel symbol={symbol} />
    </div>
  );
}

export default function Home({ route }: { route: HomeRoute }) {
  useDocumentTitle("");
  const overview = useDataset("overview.json");
  const regimes = useDataset("regimes.json");
  const backtest = useDataset("backtest.json");
  const events = useDataset("events.json");
  const provenance = useDataset("provenance.json");
  return (
    <div className="page">
      <Gate<[Overview, Regimes, Backtest, Events, Provenance]> states={[overview, regimes, backtest, events, provenance]}>
        {(o, r, b, e, p) => <Dashboard overview={o} regimes={r} backtest={b} events={e} provenance={p} route={route} />}
      </Gate>
    </div>
  );
}
