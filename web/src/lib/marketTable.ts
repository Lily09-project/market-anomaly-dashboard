import type { MarketKind, MarketSort } from "./router";
import type { MarketRow } from "./types";

export const COLUMN_INDEX: Record<MarketSort, number> = {
  code: 0,
  change_pct: 4,
  value_twd: 5,
  pe: 6,
  dividend_yield_pct: 7,
  pb: 8,
  margin_change: 10,
};

/** Taiwan ETF codes start with 00; every other listed code is treated as a stock. */
export const isEtf = (code: string) => code.startsWith("00");

/** Search code or name, filter by kind and sort; missing values always sink to the end. */
export function selectMarketRows(rows: MarketRow[], { q, sort = "code", desc = false, kind }: { q?: string; sort?: MarketSort; desc?: boolean; kind?: MarketKind }): MarketRow[] {
  const needle = q?.trim().toLowerCase() ?? "";
  const index = COLUMN_INDEX[sort];
  const direction = desc ? -1 : 1;
  return rows
    .filter((r) => (kind === undefined ? true : kind === "etf" ? isEtf(r[0]) : !isEtf(r[0])))
    .filter((r) => !needle || r[0].toLowerCase().includes(needle) || r[1].toLowerCase().includes(needle))
    .slice()
    .sort((a, b) => {
      const x = a[index];
      const y = b[index];
      if (x === null || x === undefined) return y === null || y === undefined ? a[0].localeCompare(b[0]) : 1;
      if (y === null || y === undefined) return -1;
      const order = typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number);
      return order === 0 ? a[0].localeCompare(b[0]) : order * direction;
    });
}
