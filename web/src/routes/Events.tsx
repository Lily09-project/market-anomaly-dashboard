import { useDataset, useDocumentTitle } from "../app/hooks";
import { ChartFrame, Legend, LineChart, type Series } from "../components/charts";
import { pickSymbol, StateChip, SymbolPicker } from "../components/Common";
import { ScrollRegion } from "../components/ScrollRegion";
import { EmptyState, Gate } from "../components/States";
import { downloadText, toCsv } from "../lib/csv";
import { formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import { routeToHash, type Route } from "../lib/router";
import type { Events, Overview, Regimes, Study } from "../lib/types";

type EventsRoute = Extract<Route, { name: "events" }>;

function significant(study: Study, offset: number): "up" | "down" | "none" {
  const i = study.post_offsets.indexOf(offset);
  const lo = study.post_low[i];
  const hi = study.post_high[i];
  if (lo !== null && lo !== undefined && lo > 0) return "up";
  if (hi !== null && hi !== undefined && hi < 0) return "down";
  return "none";
}

function StudyChart({ study, title }: { study: Study; title: string }) {
  const series: Series[] = [{ key: "car", label: "平均累積異常報酬", values: study.post_car, low: study.post_low, high: study.post_high, tone: 1 }];
  const i3 = study.post_offsets.indexOf(3);
  return (
    <ChartFrame
      title={title}
      summary={`${study.n} 個事件；事件後第 3 天平均累積異常報酬 ${formatSignedPercent(study.post_car[i3] ?? null)}，95% 區間 ${formatSignedPercent(study.post_low[i3] ?? null)} 至 ${formatSignedPercent(study.post_high[i3] ?? null)}。`}
      table={
        <table>
          <thead>
            <tr>
              <th scope="col">事件後第幾天</th>
              <th scope="col">平均 CAR</th>
              <th scope="col">95% 下界</th>
              <th scope="col">95% 上界</th>
            </tr>
          </thead>
          <tbody>
            {study.post_offsets.map((o, i) => (
              <tr key={o}>
                <th scope="row">+{o}</th>
                <td className="num">{formatSignedPercent(study.post_car[i] ?? null, 2)}</td>
                <td className="num">{formatSignedPercent(study.post_low[i] ?? null, 2)}</td>
                <td className="num">{formatSignedPercent(study.post_high[i] ?? null, 2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      }
    >
      <LineChart series={series} labels={study.post_offsets.map((o) => `+${o} 日`)} reference={{ value: 0, label: "0" }} format={(v) => formatPercent(v, 1)} height={220} />
    </ChartFrame>
  );
}

function EventsView({ overview, events, regimes, route }: { overview: Overview; events: Events; regimes: Regimes; route: EventsRoute }) {
  const symbol = pickSymbol(overview, route.symbol);
  const list = events.symbols[symbol]?.events ?? [];
  const labels = regimes.labels;
  const selected = list.find((e) => e.date === route.date) ?? list[0];
  const v = events.validation;
  const negative = events.study.negative;
  const positive = events.study.positive;
  const negSig = significant(negative, 3);
  const posSig = significant(positive, 3);

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">事件研究</span>
        <h1>異常事件：之後會發生什麼？</h1>
        <p className="lede">
          「異常」是相對於當下市場狀態而言：高波動期間跌 3% 很平常，平穩期間跌 3% 就很罕見。先以最早 252 個交易日校準並固定 HMM，再以此前資料的過濾狀態逐日計算 z 分數（校準期不評分），|z| &gt; {events.threshold} 視為異常，再問一個誠實的問題：異常日之後，報酬可以預測嗎？
        </p>
      </header>

      {v && (
        <section className="kpis" aria-label="偵測器驗證">
          <div className="card kpi">
            <span className="stat-label">注入事件召回率</span>
            <span className="stat-value" data-testid="recall">
              {formatPercent(v.recall, 0)}
            </span>
            <span className="muted small">
              合成資料中注入 {v.injected} 個跳空，找到 {v.matched} 個
            </span>
          </div>
          <div className="card kpi">
            <span className="stat-label">精確率</span>
            <span className="stat-value">{formatPercent(v.precision, 0)}</span>
            <span className="muted small">偵測到 {v.detected} 個異常日，其中屬於注入跳空的比例</span>
          </div>
          <div className="card kpi">
            <span className="stat-label">對照組誤報</span>
            <span className="stat-value" data-testid="control-events">
              {events.control_events}
            </span>
            <span className="muted small">隨機漫步對照組上被判為異常的天數</span>
          </div>
        </section>
      )}

      <section className="split">
        <div className="card">
          <StudyChart study={negative} title={`負向衝擊之後（${negative.n} 個事件，所有個股合計）`} />
          <p className="callout" data-testid="negative-verdict">
            {negSig === "up"
              ? "結論：負向衝擊之後有顯著的反彈——第 3 天的 95% 區間完全在 0 以上。"
              : negSig === "down"
                ? "結論：負向衝擊之後顯著續跌。"
                : "結論：95% 區間涵蓋 0，沒有證據顯示事件後的報酬可以預測。"}
            {v && ` 合成資料的真實答案是：每次負向跳空後連續 ${v.truth_rebound.days} 天各多出 ${formatPercent(v.truth_rebound.per_day, 1)}（合計約 ${formatPercent(v.truth_rebound.days * v.truth_rebound.per_day, 1)}）。`}
          </p>
        </div>
        <div className="card">
          <StudyChart study={positive} title={`正向衝擊之後（${positive.n} 個事件）`} />
          <p className="callout" data-testid="positive-verdict">
            {posSig === "none"
              ? "結論：95% 區間涵蓋 0，正向衝擊之後沒有可預測的報酬。這也是合成資料的真實設定：正向跳空之後沒有任何延續或反轉。"
              : `結論：第 3 天的區間${posSig === "up" ? "高於" : "低於"} 0。`}
          </p>
        </div>
      </section>

      <SymbolPicker overview={overview} value={symbol} route={{ ...route, symbol, date: undefined }} />

      {list.length === 0 ? (
        <EmptyState title="這個標的沒有異常日">
          <p>{overview.symbols.find((s) => s.symbol === symbol)?.is_control ? "隨機漫步對照組沒有被誤判的異常日——偵測器沒有把雜訊當成事件。" : "門檻內沒有任何一天超過異常標準。"}</p>
        </EmptyState>
      ) : (
        <section className="split">
          <div className="card">
            <div className="row-between">
              <h2>{symbol} 的異常日（{list.length}）</h2>
              <button
                type="button"
                className="btn"
                onClick={() =>
                  downloadText(
                    `events-${symbol}.csv`,
                    toCsv(
                      ["date", "symbol", "return", "z", "state", "injected"],
                      list.map((e) => ({ date: e.date, symbol, return: e.return, z: e.z, state: labels[e.state], injected: e.injected === null ? "" : e.injected ? "yes" : "no" })),
                    ),
                    "text/csv;charset=utf-8",
                  )
                }
              >
                下載 CSV
              </button>
            </div>
            <ScrollRegion label="異常日列表">
              <table data-testid="events-table">
                <thead>
                  <tr>
                    <th scope="col">日期</th>
                    <th scope="col">報酬</th>
                    <th scope="col">z</th>
                    <th scope="col">當時狀態</th>
                    {v && <th scope="col">注入？</th>}
                  </tr>
                </thead>
                <tbody>
                  {list.map((e) => (
                    <tr key={e.date} aria-current={selected?.date === e.date ? "true" : undefined}>
                      <th scope="row">
                        <a href={routeToHash({ name: "events", symbol, date: e.date })}>{e.date}</a>
                      </th>
                      <td className="num">{formatSignedPercent(e.return, 2)}</td>
                      <td className="num">{formatNumber(e.z, 1)}</td>
                      <td>
                        <StateChip state={e.state} labels={labels} />
                      </td>
                      {v && <td>{e.injected ? "是" : "否"}</td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </ScrollRegion>
          </div>
          {selected && (
            <div className="card" data-testid="event-detail">
              <h2>
                {selected.date}：{formatSignedPercent(selected.return, 2)}
              </h2>
              <p className="muted">
                z = {formatNumber(selected.z, 1)}，當時處於 <StateChip state={selected.state} labels={labels} />。
              </p>
              {selected.car_post ? (
                <>
                  <ChartFrame
                    title="這一個事件之後的累積異常報酬"
                    summary={`第 10 天累積 ${formatSignedPercent(selected.car_post.at(-1) ?? null)}。單一事件的雜訊很大，只有平均多個事件才看得出規律。`}
                    table={
                      <table>
                        <thead>
                          <tr>
                            <th scope="col">事件後</th>
                            <th scope="col">CAR</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selected.car_post.map((c, i) => (
                            <tr key={i}>
                              <th scope="row">+{i + 1}</th>
                              <td className="num">{formatSignedPercent(c, 2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    }
                  >
                    <LineChart
                      series={[{ key: "one", label: "此事件", values: selected.car_post, tone: 2 }]}
                      labels={selected.car_post.map((_, i) => `+${i + 1} 日`)}
                      reference={{ value: 0, label: "0" }}
                      format={(x) => formatPercent(x, 1)}
                      height={200}
                    />
                  </ChartFrame>
                  <Legend items={[{ key: "one", label: "此事件的累積異常報酬", tone: 2 }]} />
                </>
              ) : (
                <p className="muted">這個事件太靠近資料開頭或結尾，沒有完整的估計窗或事件窗，所以不納入事件研究。</p>
              )}
            </div>
          )}
        </section>
      )}

      <section className="card method">
        <h2>方法</h2>
        <p>
          異常報酬採平均調整模型：事件日的報酬減去該股在事件前第 120 至第 11 天的平均報酬。事件窗為前 5 天到後 10 天。信賴區間以「重抽事件」的 bootstrap（2,000 次、固定種子）計算，因此反映的是事件之間的差異。
        </p>
      </section>
    </div>
  );
}

export default function EventsPage({ route }: { route: EventsRoute }) {
  useDocumentTitle("異常事件研究");
  const overview = useDataset("overview.json");
  const events = useDataset("events.json");
  const regimes = useDataset("regimes.json");
  return (
    <div className="page">
      <Gate<[Overview, Events, Regimes]> states={[overview, events, regimes]}>{(o, e, r) => <EventsView overview={o} events={e} regimes={r} route={route} />}</Gate>
    </div>
  );
}
