import { useDataset } from "../app/hooks";
import { formatNumber, formatSigned } from "../lib/format";
import { isEtf } from "../lib/marketTable";
import type { Twse, TwseSymbol } from "../lib/types";
import { ChartFrame, LineChart } from "./charts";
import { Gate } from "./States";
import "./Twse.css";

const lots = (value: number | null) => (value === null ? "—" : `${value.toLocaleString("zh-TW")} 張`);
const hundredMillion = (value: number | null) => (value === null ? "—" : `${formatNumber(value / 1e8, 1)} 億元`);

function CrossCheck({ row, date }: { row: TwseSymbol; date: string }) {
  if (row.cross_check === null) {
    return (
      <span className="tag" data-tone="info" data-testid="twse-cross-check">
        FinMind 尚無 {date} 資料
      </span>
    );
  }
  return row.cross_check.match ? (
    <span className="tag" data-tone="good" data-testid="twse-cross-check">
      與 FinMind 收盤一致
    </span>
  ) : (
    <span className="tag" data-tone="bad" data-testid="twse-cross-check">
      與 FinMind 不一致（{formatNumber(row.cross_check.finmind_close, 2)}）
    </span>
  );
}

function Metric({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="twse-metric">
      <dt className="stat-label">{label}</dt>
      <dd>
        <span className="twse-value">{value}</span>
        {note && <span className="muted small">{note}</span>}
      </dd>
    </div>
  );
}

function TwseView({ twse, symbol }: { twse: Twse; symbol: string }) {
  if (twse.status === "unavailable" || twse.trade_date === null) {
    return (
      <p className="notice" data-testid="twse-unavailable">
        這次更新沒有取得證交所盤後資料，價格分析不受影響；下次排程會再試。
      </p>
    );
  }
  const date = twse.trade_date;
  const row = twse.symbols[symbol];
  const market = twse.market;
  return (
    <div className="twse-grid">
      <div className="twse-symbol">
        {row ? (
          <>
            <dl className="twse-metrics">
              <Metric label="收盤價" value={formatNumber(row.close, 2)} note={`漲跌 ${formatSigned(row.change, 2)}`} />
              <Metric label="成交值" value={hundredMillion(row.value_twd)} />
              {isEtf(symbol) ? (
                <>
                  <Metric label="本益比" value="不適用" note="ETF 沒有個股估值" />
                  <Metric label="殖利率" value="不適用" />
                </>
              ) : (
                <>
                  <Metric label="本益比" value={row.pe === null ? "—" : `${formatNumber(row.pe, 2)} 倍`} note={`淨值比 ${formatNumber(row.pb, 2)}`} />
                  <Metric label="殖利率" value={row.dividend_yield_pct === null ? "—" : `${formatNumber(row.dividend_yield_pct, 2)}%`} />
                </>
              )}
              <Metric label="融資餘額" value={lots(row.margin_balance)} note={`較前日 ${formatSigned(row.margin_change, 0)} 張`} />
              <Metric label="融券餘額" value={lots(row.short_balance)} note={`較前日 ${formatSigned(row.short_change, 0)} 張`} />
            </dl>
            <CrossCheck row={row} date={date} />
          </>
        ) : (
          <p className="muted">這個標的沒有交易所資料（隨機漫步對照組）。</p>
        )}
      </div>
      {market.length > 1 && (
        <ChartFrame
          title="加權指數（本月）"
          summary={`${market[0]!.date} 至 ${market.at(-1)!.date}，加權指數從 ${formatNumber(market[0]!.taiex, 0)} 到 ${formatNumber(market.at(-1)!.taiex, 0)}。`}
          table={
            <table data-testid="twse-market-table">
              <thead>
                <tr>
                  <th scope="col">日期</th>
                  <th scope="col">加權指數</th>
                  <th scope="col">漲跌點數</th>
                  <th scope="col">成交值</th>
                </tr>
              </thead>
              <tbody>
                {market.map((m) => (
                  <tr key={m.date}>
                    <th scope="row">{m.date}</th>
                    <td className="num">{formatNumber(m.taiex, 2)}</td>
                    <td className="num">{formatSigned(m.change, 2)}</td>
                    <td className="num">{hundredMillion(m.value_twd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <LineChart series={[{ key: "taiex", label: "加權指數", values: market.map((m) => m.taiex), tone: 3 }]} labels={market.map((m) => m.date)} format={(v) => formatNumber(v, 0)} height={180} ticks={3} />
        </ChartFrame>
      )}
    </div>
  );
}

/** Latest TWSE after-hours snapshot; loads on its own so a failure never blocks the dashboard. */
export function TwsePanel({ symbol }: { symbol: string }) {
  const twse = useDataset("twse.json");
  const ready = twse.status === "ready" ? twse.data : null;
  return (
    <section className="card twse" aria-labelledby="twse-title" data-testid="twse-panel">
      <div className="row-between">
        <h2 id="twse-title">證交所盤後快照</h2>
        {ready?.trade_date && <span className="badge">{ready.trade_date} 收盤</span>}
      </div>
      {ready?.status === "sample" && (
        <p className="notice" data-testid="twse-sample">
          預覽用合成數值，正式網站會換成證交所 OpenAPI 的資料。
        </p>
      )}
      <Gate<[Twse]> states={[twse]}>{(t) => <TwseView twse={t} symbol={symbol} />}</Gate>
      <p className="muted small">
        來源：<a href="https://openapi.twse.com.tw/">證交所 OpenAPI</a>，依<a href="https://data.gov.tw/license">政府資料開放授權條款</a>使用。只提供最新一個交易日，不是即時報價；融資券資料集未標日期，視為同一批盤後公告。
      </p>
    </section>
  );
}
