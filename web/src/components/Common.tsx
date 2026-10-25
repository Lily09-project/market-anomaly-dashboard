import { useRoute } from "../app/hooks";
import type { Route } from "../lib/router";
import type { Overview } from "../lib/types";

export const DEFAULT_SYMBOL = "0050";

/** Resolve the route's symbol against the data, falling back to the default. */
export function pickSymbol(overview: Overview, symbol: string | undefined): string {
  return overview.symbols.some((s) => s.symbol === symbol) ? (symbol as string) : (overview.symbols.find((s) => s.symbol === DEFAULT_SYMBOL)?.symbol ?? overview.symbols[0]?.symbol ?? DEFAULT_SYMBOL);
}

/** Radio group that switches the symbol in the URL while keeping the current page. */
export function SymbolPicker({ overview, value, route }: { overview: Overview; value: string; route: Extract<Route, { symbol?: string }> }) {
  const [, navigate] = useRoute();
  return (
    <fieldset className="segmented symbol-segmented">
      <legend>標的</legend>
      {overview.symbols.map((s) => (
        <label key={s.symbol}>
          <input type="radio" name="symbol" value={s.symbol} checked={value === s.symbol} onChange={() => navigate({ ...route, symbol: s.symbol } as Route, { replace: true })} />
          <span>
            {s.symbol} {s.name}
          </span>
        </label>
      ))}
    </fieldset>
  );
}

export function StateChip({ state, labels }: { state: number; labels: string[] }) {
  return (
    <span className="state-chip" data-state={state}>
      {labels[state] ?? `狀態 ${state}`}
    </span>
  );
}
