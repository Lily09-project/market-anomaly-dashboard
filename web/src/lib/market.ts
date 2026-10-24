/** Pure helpers that turn the exported analysis into chart-ready series. */
import type { BacktestResult, Segment } from "./types";

/** State of every return day from run-length segments. */
export function statesByDay(segments: readonly Segment[], length: number): number[] {
  const out = new Array<number>(length).fill(-1);
  for (const [start, end, state] of segments) for (let i = start; i <= Math.min(end, length - 1); i += 1) out[i] = state;
  return out;
}

/** Share of days on which two state paths agree. */
export function agreement(a: readonly Segment[], b: readonly Segment[], length: number): number {
  const x = statesByDay(a, length);
  const y = statesByDay(b, length);
  let same = 0;
  for (let i = 0; i < length; i += 1) if (x[i] === y[i]) same += 1;
  return length ? same / length : 0;
}

/** Annualised rolling volatility of log returns (window days, trailing). */
export function rollingVolatility(returns: readonly number[], window = 20): (number | null)[] {
  const out: (number | null)[] = [];
  let sum = 0;
  let sumSq = 0;
  for (let i = 0; i < returns.length; i += 1) {
    const r = returns[i]!;
    sum += r;
    sumSq += r * r;
    if (i >= window) {
      const old = returns[i - window]!;
      sum -= old;
      sumSq -= old * old;
    }
    if (i + 1 < window) out.push(null);
    else {
      const mean = sum / window;
      const variance = Math.max((sumSq - window * mean * mean) / (window - 1), 0);
      out.push(Math.sqrt(variance * 252));
    }
  }
  return out;
}

/** Drawdown from the running peak of a price series (≤ 0). */
export function drawdowns(close: readonly number[]): number[] {
  let peak = -Infinity;
  return close.map((c) => {
    peak = Math.max(peak, c);
    return c / peak - 1;
  });
}

export interface HeatCell {
  index: number;
  fast: number;
  slow: number;
  value: number;
}

/** Rows by fast window, columns by slow window; null where fast ≥ slow. */
export function heatmap(result: Pick<BacktestResult, "fast" | "slow" | "grid">, values: readonly number[]): (HeatCell | null)[][] {
  const lookup = new Map(result.grid.map(([f, s], index) => [`${f}-${s}`, index]));
  return result.fast.map((f) =>
    result.slow.map((s) => {
      const index = lookup.get(`${f}-${s}`);
      return index === undefined ? null : { index, fast: f, slow: s, value: values[index] ?? 0 };
    }),
  );
}

/** Spearman rank correlation between in-sample and out-of-sample results. */
export function rankCorrelation(a: readonly number[], b: readonly number[]): number {
  const rank = (v: readonly number[]) => {
    const order = v.map((x, i) => [x, i] as const).sort((p, q) => p[0] - q[0]);
    const r = new Array<number>(v.length);
    let i = 0;
    while (i < order.length) {
      let j = i;
      while (j + 1 < order.length && order[j + 1]![0] === order[i]![0]) j += 1;
      for (let k = i; k <= j; k += 1) r[order[k]![1]] = (i + j) / 2 + 1;
      i = j + 1;
    }
    return r;
  };
  const ra = rank(a);
  const rb = rank(b);
  const n = a.length;
  const mean = (n + 1) / 2;
  let num = 0;
  let da = 0;
  let db = 0;
  for (let i = 0; i < n; i += 1) {
    num += (ra[i]! - mean) * (rb[i]! - mean);
    da += (ra[i]! - mean) ** 2;
    db += (rb[i]! - mean) ** 2;
  }
  return da && db ? num / Math.sqrt(da * db) : 0;
}

/** Dates for an equity curve that was sampled every `step` days from `start`. */
export function sampledDates(dates: readonly string[], start: string, step: number, count: number): string[] {
  const first = dates.indexOf(start);
  if (first < 0) return [];
  return Array.from({ length: count }, (_, i) => dates[Math.min(first + i * step, dates.length - 1)]!);
}
