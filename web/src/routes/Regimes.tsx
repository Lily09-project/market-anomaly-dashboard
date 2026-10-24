import type { CSSProperties } from "react";
import { useDataset, useDocumentTitle } from "../app/hooks";
import { ChartFrame, Legend, LineChart, StateTimeline } from "../components/charts";
import { pickSymbol, StateChip, SymbolPicker } from "../components/Common";
import { ScrollRegion } from "../components/ScrollRegion";
import { Gate } from "../components/States";
import { formatNumber, formatPercent, formatSignedPercent } from "../lib/format";
import type { Route } from "../lib/router";
import type { Overview, Regimes } from "../lib/types";
import "./Regimes.css";

type RegimesRoute = Extract<Route, { name: "regimes" }>;

function RegimeView({ overview, regimes, route }: { overview: Overview; regimes: Regimes; route: RegimesRoute }) {
  const symbol = pickSymbol(overview, route.symbol);
  const regime = regimes.symbols[symbol]!;
  const labels = regime.labels;
  const length = overview.dates.length - 1;
  const ll = regime.log_likelihood;
  const noRegimes = regime.bic_choice === 1;

  return (
    <div className="stack">
      <header>
        <span className="eyebrow">隱藏馬可夫模型</span>
        <h1>市場狀態偵測</h1>
        <p className="lede">
          我們看不到市場「處於什麼狀態」，只看得到每天的報酬。高斯隱藏馬可夫模型假設背後有幾個會持續一段時間的狀態，各有自己的平均報酬與波動，再用 Baum-Welch 估計參數、Viterbi 解出最可能的狀態序列。
        </p>
      </header>

      <SymbolPicker overview={overview} value={symbol} route={{ ...route, symbol }} />

      {noRegimes && (
        <p className="notice" data-testid="no-regime-notice">
          BIC 在 1、2、3 個狀態中選擇了 <strong>1 個</strong>：這條序列沒有證據顯示存在不同狀態。下面仍顯示 3 狀態模型的結果，但三個狀態的波動幾乎相同，只是在切分雜訊。
        </p>
      )}

      <section className="grid grid-3" aria-label="各狀態特徵">
        {labels.map((label, state) => (
          <div className="card kpi state-card" data-state={state} key={label} data-testid="state-card">
            <StateChip state={state} labels={labels} />
            <dl className="mini-dl">
              <dt>年化平均報酬</dt>
              <dd>{formatSignedPercent(regime.means_annual[state])}</dd>
              <dt>年化波動</dt>
              <dd>{formatPercent(regime.vol_annual[state])}</dd>
              <dt>預期持續</dt>
              <dd>{formatNumber(regime.expected_days[state], 0)} 個交易日</dd>
              <dt>時間占比</dt>
              <dd>{formatPercent(regime.share[state], 0)}</dd>
            </dl>
          </div>
        ))}
      </section>

      <section className="card">
        <ChartFrame
          title={regime.truth_segments ? "模型判定 vs. 合成資料的真實狀態" : "模型判定的狀態序列"}
          summary={
            regime.accuracy !== null
              ? `標籤對齊後，模型與真實狀態一致的交易日比例為 ${formatPercent(regime.accuracy, 1)}。`
              : `共 ${regime.segments.length} 段狀態；目前為 ${labels[regime.current.state]}。`
          }
          table={
            <table data-testid="segments-table">
              <thead>
                <tr>
                  <th scope="col">起</th>
                  <th scope="col">迄</th>
                  <th scope="col">狀態</th>
                  <th scope="col">天數</th>
                </tr>
              </thead>
              <tbody>
                {regime.segments.map(([start, end, state]) => (
                  <tr key={start}>
                    <th scope="row">{overview.dates[start + 1]}</th>
                    <td>{overview.dates[end + 1]}</td>
                    <td>{labels[state]}</td>
                    <td className="num">{end - start + 1}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <StateTimeline
            length={length}
            labels={labels}
            rows={[
              { key: "hmm", label: "HMM", segments: regime.segments },
              ...(regime.truth_segments ? [{ key: "truth", label: "真實狀態", segments: regime.truth_segments }] : []),
            ]}
          />
        </ChartFrame>
        <Legend items={labels.map((label, state) => ({ key: label, label, state }))} />
        {regime.accuracy !== null && (
          <p className="callout">
            還原準確率 <strong data-testid="accuracy">{formatPercent(regime.accuracy, 1)}</strong>（驗收門檻 80%）。估計前先排除了 {regime.excluded_jump_days} 個跳空日：跳空另外在「異常事件」研究，否則模型會把它們當成第四種狀態。
          </p>
        )}
      </section>

      <section className="split">
        <div className="card">
          <h2>轉移矩陣</h2>
          <p className="muted small">每一列是「今天的狀態」，每一欄是「明天的狀態」；對角線越接近 100%，狀態越持久。每列加總為 100%。</p>
          <ScrollRegion label="狀態轉移機率">
            <table className="matrix" data-testid="transition-table">
              <thead>
                <tr>
                  <th scope="col">今天 \ 明天</th>
                  {labels.map((l) => (
                    <th scope="col" key={l}>
                      {l}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {regime.transition.map((row, i) => (
                  <tr key={labels[i]}>
                    <th scope="row">{labels[i]}</th>
                    {row.map((p, j) => (
                      <td key={j} className="num" style={{ "--p": p } as CSSProperties} data-diagonal={i === j}>
                        {formatPercent(p, 1)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
          {regime.confusion && (
            <>
              <h3>混淆矩陣（天數）</h3>
              <ScrollRegion label="真實狀態與模型判定的混淆矩陣">
                <table className="matrix" data-testid="confusion-table">
                  <thead>
                    <tr>
                      <th scope="col">真實 \ 模型</th>
                      {labels.map((l) => (
                        <th scope="col" key={l}>
                          {l}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {regime.confusion.map((row, i) => (
                      <tr key={labels[i]}>
                        <th scope="row">{labels[i]}</th>
                        {row.map((n, j) => (
                          <td key={j} className="num" data-diagonal={i === j}>
                            {n}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollRegion>
            </>
          )}
        </div>
        <div className="card">
          <ChartFrame
            title="EM 疊代的對數概似"
            summary={`從 ${formatNumber(ll[0], 1)} 單調上升到 ${formatNumber(ll.at(-1), 1)}，共 ${ll.length - 1} 次疊代。`}
            table={
              <table>
                <thead>
                  <tr>
                    <th scope="col">疊代</th>
                    <th scope="col">對數概似</th>
                  </tr>
                </thead>
                <tbody>
                  {ll.map((v, i) => (
                    <tr key={i}>
                      <th scope="row">{i}</th>
                      <td className="num">{formatNumber(v, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          >
            <LineChart series={[{ key: "ll", label: "對數概似", values: ll, tone: 1 }]} labels={ll.map((_, i) => `第 ${i} 次`)} format={(v) => formatNumber(v, 0)} height={200} />
          </ChartFrame>
          <h3>要用幾個狀態？</h3>
          <ScrollRegion label="BIC 模型選擇">
            <table data-testid="bic-table">
              <thead>
                <tr>
                  <th scope="col">狀態數</th>
                  <th scope="col">BIC（越低越好）</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(regime.bic).map(([k, v]) => (
                  <tr key={k} aria-current={Number(k) === regime.bic_choice ? "true" : undefined}>
                    <th scope="row">
                      {k} {Number(k) === regime.bic_choice && <span className="tag" data-tone="info">BIC 選擇</span>}
                    </th>
                    <td className="num">{formatNumber(v, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollRegion>
          <p className="muted small">
            {noRegimes
              ? "對照組正確地選了 1 個狀態。"
              : regime.bic_choice === 2
                ? "BIC 偏好 2 個狀態：平穩與震盪的波動只差約一倍，懲罰參數後不一定值得分開。真實資料是 3 個狀態，所以我們仍展示 3 狀態模型，並用真實答案檢驗它。"
                : `BIC 選擇 ${regime.bic_choice} 個狀態。`}
          </p>
        </div>
      </section>
    </div>
  );
}

export default function RegimesPage({ route }: { route: RegimesRoute }) {
  useDocumentTitle("市場狀態偵測");
  const overview = useDataset("overview.json");
  const regimes = useDataset("regimes.json");
  return (
    <div className="page">
      <Gate<[Overview, Regimes]> states={[overview, regimes]}>{(o, r) => <RegimeView overview={o} regimes={r} route={route} />}</Gate>
    </div>
  );
}
