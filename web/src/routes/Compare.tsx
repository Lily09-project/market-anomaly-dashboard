import { useDataset, useDocumentTitle, useRoute } from "../app/hooks";
import { ChartFrame, Legend, LineChart } from "../components/charts";
import { PageHead } from "../components/PageHead";
import { EmptyState, Gate } from "../components/States";
import { downloadText, toCsv } from "../lib/csv";
import { formatNumber, formatPercent } from "../lib/format";
import { PERIOD_DAYS, type Period, type Route } from "../lib/router";
import { compareCloses, comparisonMetrics } from "../lib/symbolComparison";
import type { Overview } from "../lib/types";

type CompareRoute = Extract<Route, { name: "compare" }>;

function Comparison({ data, route }: { data: Overview; route: CompareRoute }) {
  const [, navigate] = useRoute();
  const symbols = data.symbols.filter((item) => !item.is_control);
  const a = symbols.find((item) => item.symbol === route.symbol) ?? symbols[0];
  const b = symbols.find((item) => item.symbol === route.against) ?? symbols.find((item) => item.symbol !== a?.symbol) ?? a;
  if (!a || !b) return <EmptyState title="目前沒有可比較的歷史行情" />;
  const period = route.period ?? "1y";
  const rows = compareCloses(data.dates, a.close, b.close, PERIOD_DAYS[period]);
  const names = [a, b].map((item) => `${item.symbol} ${item.name}`);
  const update = (patch: Partial<CompareRoute>) => navigate({ name: "compare", symbol: a.symbol, against: b.symbol, period, ...patch });
  const options = symbols.map((item) => <option key={item.symbol} value={item.symbol}>{item.symbol} {item.name}</option>);
  return (
    <div className="stack">
      <section className="card controls-row" aria-label="比較設定">
        <label className="field">標的 A<select className="input" value={a.symbol} onChange={(event) => update({ symbol: event.target.value })}>{options}</select></label>
        <label className="field">標的 B<select className="input" value={b.symbol} onChange={(event) => update({ against: event.target.value })}>{options}</select></label>
        <label className="field">共同交易期間<select className="input" value={period} onChange={(event) => update({ period: event.target.value as Period })}>
          <option value="1y">近 252 個交易日</option><option value="3y">近 756 個交易日</option><option value="all">全部</option>
        </select></label>
      </section>
      {rows ? <section className="card">
        <p>{rows[0]!.date} 至 {rows.at(-1)!.date} · {rows.length} 個共同交易日</p>
        <p className="muted">以同一口徑的收盤價比較，第一個共同交易日為 100。報酬未計交易成本。</p>
        <div className="scroll-x"><table>
          <thead><tr><th scope="col">標的</th><th scope="col">累積報酬</th><th scope="col">最大回撤</th><th scope="col">年化波動</th></tr></thead>
          <tbody>{(["a", "b"] as const).map((key, i) => {
            const metrics = comparisonMetrics(rows.map((row) => row[key]));
            return <tr key={key}><th scope="row">{names[i]}</th><td>{formatPercent(metrics.total)}</td><td>{formatPercent(metrics.drawdown)}</td><td>{formatPercent(metrics.volatility)}</td></tr>;
          })}</tbody>
        </table></div>
        <ChartFrame title="收盤價走勢（起點 100）" summary={`${names.join("、")}，${rows.length} 個共同交易日`} table={<table>
          <thead><tr><th scope="col">日期</th><th scope="col">{names[0]}</th><th scope="col">{names[1]}</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.date}><th scope="row">{row.date}</th><td>{formatNumber(row.a, 2)}</td><td>{formatNumber(row.b, 2)}</td></tr>)}</tbody>
        </table>}>
          <LineChart labels={rows.map((row) => row.date)} series={[
            { key: "a", label: names[0]!, values: rows.map((row) => row.a), tone: 1 },
            { key: "b", label: names[1]!, values: rows.map((row) => row.b), tone: 2 },
          ]} reference={{ value: 100, label: "起點" }} />
          <Legend items={[{ key: "a", label: names[0]!, tone: 1 }, { key: "b", label: names[1]!, tone: 2 }]} />
        </ChartFrame>
        <button className="btn" type="button" onClick={() => downloadText(
          `market-${a.symbol}-${b.symbol}.csv`,
          toCsv(["date", "symbol_a", "index_a", "symbol_b", "index_b"], rows.map((row) => ({
            date: row.date, symbol_a: a.symbol, index_a: row.a, symbol_b: b.symbol, index_b: row.b,
          }))), "text/csv;charset=utf-8")}>下載比較 CSV</button>
      </section> : <EmptyState title="共同交易日不足"><p>請選擇其他標的。</p></EmptyState>}
    </div>
  );
}

export default function Compare({ route }: { route: CompareRoute }) {
  useDocumentTitle("標的比較");
  const data = useDataset("overview.json");
  return <div className="page stack"><PageHead eyebrow="研究工具" title="標的比較" /><Gate<[Overview]> states={[data]}>{(overview) => <Comparison data={overview} route={route} />}</Gate></div>;
}
