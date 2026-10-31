/** Hash routes keep every view shareable on a static host. */
export type Period = "all" | "3y" | "1y";
export const PERIOD_DAYS: Record<Period, number | null> = { all: null, "3y": 756, "1y": 252 };

export type Route =
  | { name: "home"; symbol?: string; period?: Period }
  | { name: "regimes"; symbol?: string }
  | { name: "events"; symbol?: string; date?: string }
  | { name: "backtest"; symbol?: string; cell?: number }
  | { name: "stress"; symbol?: string; horizon?: number; block?: number; paths?: number }
  | { name: "market"; q?: string; sort?: MarketSort; desc?: boolean; kind?: MarketKind }
  | { name: "snapshot" }
  | { name: "data" }
  | { name: "not-found"; path: string };

export const MARKET_SORTS = ["code", "change_pct", "value_twd", "pe", "dividend_yield_pct", "pb", "margin_change"] as const;
export type MarketSort = (typeof MARKET_SORTS)[number];
export type MarketKind = "stock" | "etf";

export const STRESS_LIMITS = {
  horizon: [5, 250],
  block: [1, 60],
  paths: [100, 20000],
} as const;

function intParam(params: URLSearchParams, key: string): number | undefined {
  const raw = params.get(key);
  if (raw === null || !/^\d+$/.test(raw)) return undefined;
  return Number(raw);
}

function bounded(value: number | undefined, [lo, hi]: readonly [number, number]): number | undefined {
  return value !== undefined && value >= lo && value <= hi ? value : undefined;
}

export function parseRoute(hash: string): Route {
  const raw = hash.replace(/^#/, "") || "/";
  const [path = "/", query = ""] = raw.split("?");
  const params = new URLSearchParams(query);
  const head = path.split("/").filter(Boolean)[0];
  const symbol = params.get("symbol") ?? undefined;
  switch (head) {
    case undefined: {
      const period = params.get("period");
      return { name: "home", symbol, period: period === "3y" || period === "1y" || period === "all" ? period : undefined };
    }
    case "regimes":
      return { name: "regimes", symbol };
    case "events": {
      const date = params.get("date");
      return { name: "events", symbol, date: date && /^\d{4}-\d{2}-\d{2}$/.test(date) ? date : undefined };
    }
    case "backtest":
      return { name: "backtest", symbol, cell: intParam(params, "cell") };
    case "stress":
      return {
        name: "stress",
        symbol,
        horizon: bounded(intParam(params, "horizon"), STRESS_LIMITS.horizon),
        block: bounded(intParam(params, "block"), STRESS_LIMITS.block),
        paths: bounded(intParam(params, "paths"), STRESS_LIMITS.paths),
      };
    case "market": {
      const sort = params.get("sort");
      const kind = params.get("kind");
      const q = params.get("q")?.trim().slice(0, 40);
      return {
        name: "market",
        q: q || undefined,
        sort: (MARKET_SORTS as readonly string[]).includes(sort ?? "") ? (sort as MarketSort) : undefined,
        desc: params.get("desc") === "1" ? true : undefined,
        kind: kind === "stock" || kind === "etf" ? kind : undefined,
      };
    }
    case "snapshot":
      return { name: "snapshot" };
    case "data":
      return { name: "data" };
    default:
      return { name: "not-found", path };
  }
}

export function routeToHash(route: Route): string {
  const query = (entries: Record<string, string | number | undefined>) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(entries)) if (value !== undefined && value !== "") params.set(key, String(value));
    const text = params.toString();
    return text ? `?${text}` : "";
  };
  switch (route.name) {
    case "home":
      return `#/${query({ symbol: route.symbol, period: route.period })}`;
    case "regimes":
      return `#/regimes${query({ symbol: route.symbol })}`;
    case "events":
      return `#/events${query({ symbol: route.symbol, date: route.date })}`;
    case "backtest":
      return `#/backtest${query({ symbol: route.symbol, cell: route.cell })}`;
    case "stress":
      return `#/stress${query({ symbol: route.symbol, horizon: route.horizon, block: route.block, paths: route.paths })}`;
    case "market":
      return `#/market${query({ q: route.q, sort: route.sort, desc: route.desc ? 1 : undefined, kind: route.kind })}`;
    case "snapshot":
      return "#/snapshot";
    case "data":
      return "#/data";
    case "not-found":
      return `#${route.path}`;
  }
}
