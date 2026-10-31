import { useDeferredValue, useEffect, useState } from "react";
import { useDataset, useDocumentTitle, useRoute } from "../app/hooks";
import { ScrollRegion } from "../components/ScrollRegion";
import { Gate } from "../components/States";
import { formatNumber, formatSigned, formatSignedPercent } from "../lib/format";
import { isEtf, selectMarketRows } from "../lib/marketTable";
import { routeToHash, type MarketKind, type MarketSort, type Route } from "../lib/router";
import type { Overview, TwseMarket } from "../lib/types";
import "./Market.css";

type MarketRoute = Extract<Route, { name: "market" }>;
const PAGE = 100;

const SORTS: { value: MarketSort; label: string }[] = [
  { value: "code", label: "代號" },
  { value: "change_pct", label: "漲跌幅" },
  { value: "value_twd", label: "成交值" },
  { value: "pe", label: "本益比" },
  { value: "dividend_yield_pct", label: "殖利率" },
  { value: "pb", label: "淨值比" },
  { value: "margin_change", label: "融資增減" },
];

const KINDS: { value: MarketKind | undefined; label: string }[] = [
  { value: undefined, label: "全部" },
  { value: "stock", label: "股票" },
  { value: "etf", label: "ETF" },
];

const hundredMillion = (value: number | null) => (value === null ? "—" : formatNumber(value / 1e8, 2));

function MarketView({ market, overview, route }: { market: TwseMarket; overview: Overview; route: MarketRoute }) {
  const [, navigate] = useRoute();
  const [query, setQuery] = useState(route.q ?? "");
  const deferred = useDeferredValue(query);
  const sort = route.sort ?? "code";
  const desc = route.desc ?? false;
  // Paging resets whenever the search, sort or filter changes.
  const filterKey = `${deferred}|${sort}|${desc}|${route.kind ?? ""}`;
  const [paging, setPaging] = useState({ key: filterKey, limit: PAGE });
  const limit = paging.key === filterKey ? paging.limit : PAGE;
  const analysed = new Set(overview.symbols.filter((s) => !s.is_control).map((s) => s.symbol));

  // Keep the search in the URL without adding a history entry per keystroke.
  useEffect(() => {
    const q = deferred.trim() || undefined;
    if (q !== route.q) navigate({ ...route, q }, { replace: true });
  }, [deferred, navigate, route]);

  if (market.status === "unavailable" || market.trade_date === null) {
    return (
      <p className="notice" data-testid="market-unavailable">
        這次更新沒有取得證交所全市場資料，下次排程會再試。
      </p>
    );
  }
  const rows = selectMarketRows(market.rows, { q: deferred, sort, desc, kind: route.kind });
  const shown = rows.slice(0, limit);

  return (
    <div className="stack">
      {market.status === "sample" && (
        <p className="notice" data-testid="market-sample">
          預覽用合成數值，正式網站會換成證交所 OpenAPI 的全部上市證券。
        </p>
      )}
      <div className="controls market-controls">
        <label className="field market-search">
          <span>搜尋代號或名稱</span>
          <input className="input" type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="例如 2330 或 台積" maxLength={40} />
        </label>
        <label className="field">
          <span>排序</span>
          <select className="input" value={sort} onChange={(e) => navigate({ ...route, q: query.trim() || undefined, sort: e.target.value as MarketSort }, { replace: true })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="segmented">
          <legend>方向</legend>
          {[false, true].map((d) => (
            <label key={String(d)}>
              <input type="radio" name="direction" checked={desc === d} onChange={() => navigate({ ...route, q: query.trim() || undefined, desc: d || undefined }, { replace: true })} />
              <span>{d ? "由大到小" : "由小到大"}</span>
            </label>
          ))}
        </fieldset>
        <fieldset className="segmented">
          <legend>類型</legend>
          {KINDS.map((k) => (
            <label key={k.label}>
              <input type="radio" name="kind" checked={route.kind === k.value} onChange={() => navigate({ ...route, q: query.trim() || undefined, kind: k.value }, { replace: true })} />
              <span>{k.label}</span>
            </label>
          ))}
        </fieldset>
      </div>

      <p className="muted" role="status" data-testid="market-count">
        {market.trade_date} 收盤，共 {rows.length.toLocaleString("zh-TW")} 檔{rows.length > shown.length ? `，顯示前 ${shown.length} 檔` : ""}。
      </p>

      <section className="card">
        <ScrollRegion label="全市場盤後資料表">
          <table className="market-table" data-testid="market-table">
            <thead>
              <tr>
                <th scope="col">代號</th>
                <th scope="col">名稱</th>
                <th scope="col" className="num">收盤</th>
                <th scope="col" className="num">漲跌幅</th>
                <th scope="col" className="num">成交值（億）</th>
                <th scope="col" className="num">本益比</th>
                <th scope="col" className="num">殖利率</th>
                <th scope="col" className="num">淨值比</th>
                <th scope="col" className="num">融資增減（張）</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r[0]}>
                  <th scope="row" className="mono">
                    {r[0]}
                  </th>
                  <td>
                    {analysed.has(r[0]) ? (
                      <a href={routeToHash({ name: "home", symbol: r[0] })} title="查看深度分析">
                        {r[1]}
                      </a>
                    ) : (
                      r[1]
                    )}
                    {isEtf(r[0]) && <span className="tag market-etf">ETF</span>}
                  </td>
                  <td className="num">{formatNumber(r[2], 2)}</td>
                  <td className="num" data-sign={r[4] === null ? undefined : Math.sign(r[4])}>
                    {formatSignedPercent(r[4], 2)}
                  </td>
                  <td className="num">{hundredMillion(r[5])}</td>
                  <td className="num">{formatNumber(r[6], 2)}</td>
                  <td className="num">{r[7] === null ? "—" : `${formatNumber(r[7], 2)}%`}</td>
                  <td className="num">{formatNumber(r[8], 2)}</td>
                  <td className="num">{formatSigned(r[10], 0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollRegion>
        {rows.length === 0 && <p className="muted">找不到符合「{deferred}」的證券。</p>}
        {rows.length > shown.length && (
          <button type="button" className="btn market-more" onClick={() => setPaging({ key: filterKey, limit: limit + PAGE })}>
            再顯示 {Math.min(PAGE, rows.length - shown.length)} 檔
          </button>
        )}
      </section>
    </div>
  );
}

export default function Market({ route }: { route: MarketRoute }) {
  useDocumentTitle("全市場");
  const market = useDataset("twse_market.json");
  const overview = useDataset("overview.json");
  return (
    <div className="page">
      <header className="stack">
        <span className="eyebrow">證交所 OpenAPI · 最新一個交易日</span>
        <h1>全市場盤後一覽</h1>
        <p className="lede">
          所有上市股票與 ETF 的收盤、漲跌、成交值、估值與融資變化。名稱有連結的是有完整市場狀態、異常事件與回測分析的標的。這裡只有最新一天，不是即時報價，也不構成投資建議。
        </p>
      </header>
      <Gate<[TwseMarket, Overview]> states={[market, overview]}>{(m, o) => <MarketView market={m} overview={o} route={route} />}</Gate>
      <p className="muted small">
        來源：<a href="https://openapi.twse.com.tw/">證交所 OpenAPI</a>（STOCK_DAY_ALL、BWIBBU_ALL、MI_MARGN），依<a href="https://data.gov.tw/license">政府資料開放授權條款</a>使用。沒有成交的證券收盤顯示「—」；ETF 沒有本益比、殖利率與淨值比。
      </p>
    </div>
  );
}
