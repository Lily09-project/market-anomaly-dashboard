import type { Overview } from "../lib/types";

export const DEFAULT_SYMBOL = "0050";

/** Resolve the route's symbol against the data, falling back to the default. */
export function pickSymbol(overview: Overview, symbol: string | undefined): string {
  return overview.symbols.some((s) => s.symbol === symbol) ? (symbol as string) : (overview.symbols.find((s) => s.symbol === DEFAULT_SYMBOL)?.symbol ?? overview.symbols[0]?.symbol ?? DEFAULT_SYMBOL);
}

export function StateChip({ state, labels }: { state: number; labels: string[] }) {
  return (
    <span className="state-chip" data-state={state}>
      {labels[state] ?? `狀態 ${state}`}
    </span>
  );
}
