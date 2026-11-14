import { useEffect, useId, useRef } from "react";
import { useDataset, useRoute } from "../app/hooks";
import { formatNumber, formatSignedPercent } from "../lib/format";
import type { Period, Route } from "../lib/router";
import { pickSymbol } from "./Common";
import "./SymbolBar.css";

type AnalysisRoute = Extract<Route, { name: "home" | "regimes" | "events" | "backtest" | "stress" }>;

const PERIODS: { value: Period; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "3y", label: "近 3 年" },
  { value: "1y", label: "近 1 年" },
];

/** Switching symbol keeps the page and its settings, but drops selections that belong to the old symbol. */
function withSymbol(route: AnalysisRoute, symbol: string): Route {
  if (route.name === "events") return { ...route, symbol, date: undefined };
  if (route.name === "backtest") return { ...route, symbol, cell: undefined };
  return { ...route, symbol };
}

/**
 * The analysis pages' shared terminal toolbar: a quote read-out for the selected
 * symbol, every symbol as one radio group, and (on the overview) the period.
 * It loads the overview on its own, so it is usable before the page's charts are.
 */
export function SymbolBar({ route }: { route: AnalysisRoute }) {
  const [, navigate] = useRoute();
  const overview = useDataset("overview.json");
  const rail = useRef<HTMLDivElement>(null);
  const id = useId();
  const data = overview.status === "ready" ? overview.data : null;
  const symbol = data ? pickSymbol(data, route.symbol) : route.symbol;
  const series = data?.symbols.find((s) => s.symbol === symbol);
  const last = series?.close.at(-1);
  const prev = series?.close.at(-2);
  const change = last !== undefined && prev !== undefined && prev !== 0 ? last / prev - 1 : null;
  const sign = change === null ? undefined : Math.sign(Number(change.toFixed(4)));

  // Keep the selected chip in view inside the rail without scrolling the page.
  useEffect(() => {
    const box = rail.current;
    const chip = box?.querySelector<HTMLElement>("input:checked")?.parentElement;
    if (!box || !chip) return;
    // Measure against the rail itself: offsetLeft is relative to the nearest positioned
    // ancestor, which is the whole (sticky) toolbar on desktop and overshoots the rail.
    const offset = chip.getBoundingClientRect().left - box.getBoundingClientRect().left + box.scrollLeft;
    box.scrollLeft = Math.max(offset - (box.clientWidth - chip.offsetWidth) / 2, 0);
  }, [symbol, data]);

  return (
    <section className="symbol-bar" aria-label="分析標的" data-testid="symbol-bar">
      <div className="symbol-quote">
        {series ? (
          <>
            <span className="symbol-quote-id">
              <strong className="symbol-quote-code">{series.symbol}</strong>
              <span className="symbol-quote-name">{series.name}</span>
            </span>
            <span className="symbol-quote-price">
              <span className="visually-hidden">最新收盤 </span>
              {formatNumber(last, 2)}
              <span className="symbol-quote-change" data-sign={sign}>
                <span className="visually-hidden">，單日漲跌 </span>
                {formatSignedPercent(change, 2)}
              </span>
            </span>
            <span className="symbol-quote-date">{data?.dates.at(-1)} 收盤</span>
          </>
        ) : (
          <span className="symbol-quote-loading">{overview.status === "error" ? "標的資料無法載入" : "標的載入中…"}</span>
        )}
      </div>

      <div className="symbol-picker">
        <span className="symbol-picker-label" id={`${id}-symbols`}>
          標的
        </span>
        <div className="symbol-rail" ref={rail} role="radiogroup" aria-labelledby={`${id}-symbols`}>
          {data?.symbols.map((s) => (
            <label key={s.symbol} className="symbol-chip" data-control={s.is_control || undefined}>
              <input type="radio" name="symbol" value={s.symbol} checked={symbol === s.symbol} onChange={() => navigate(withSymbol(route, s.symbol), { replace: true })} />
              <span>
                <span className="symbol-chip-code">{s.symbol}</span> <span className="symbol-chip-name">{s.name}</span>
              </span>
            </label>
          ))}
        </div>
      </div>

      {route.name === "home" && (
        <div className="symbol-period">
          <span className="symbol-picker-label" id={`${id}-period`}>
            期間
          </span>
          <div className="segmented segmented-compact" role="radiogroup" aria-labelledby={`${id}-period`}>
            {PERIODS.map((p) => (
              <label key={p.value}>
                <input
                  type="radio"
                  name="period"
                  value={p.value}
                  checked={(route.period ?? "all") === p.value}
                  onChange={() => navigate({ ...route, symbol, period: p.value }, { replace: true })}
                />
                <span>{p.label}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
