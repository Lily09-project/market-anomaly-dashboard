/**
 * Block bootstrap stress test. Mirrors src/analytics/risk.py draw for draw
 * (same mulberry32 stream and loop order), so the exported parity cases pin
 * the browser engine to the Python reference.
 */
import { mulberry32 } from "./rng";
import { quantile } from "./stats";
import type { StressParams } from "./types";

export const FAN_QUANTILES = [0.05, 0.25, 0.5, 0.75, 0.95] as const;

export function logReturns(close: readonly number[]): number[] {
  const out: number[] = [];
  for (let i = 1; i < close.length; i += 1) out.push(Math.log(close[i]!) - Math.log(close[i - 1]!));
  return out;
}

/** Cumulative log returns, one Float64Array of length `horizon` per path. */
export function blockBootstrap(
  returns: readonly number[],
  { horizon, block, paths, seed }: StressParams,
  onProgress?: (done: number) => void,
): Float64Array[] {
  const n = returns.length;
  if (block < 1 || block > n) throw new Error("block length must be between 1 and the number of returns");
  const rng = mulberry32(seed);
  const out: Float64Array[] = [];
  for (let p = 0; p < paths; p += 1) {
    const path = new Float64Array(horizon);
    let total = 0;
    let filled = 0;
    while (filled < horizon) {
      const start = Math.floor(rng() * (n - block + 1));
      const take = Math.min(block, horizon - filled);
      for (let offset = 0; offset < take; offset += 1) {
        total += returns[start + offset]!;
        path[filled] = total;
        filled += 1;
      }
    }
    out.push(path);
    if (onProgress && (p + 1) % 250 === 0) onProgress(p + 1);
  }
  return out;
}

/** Historical VaR (loss quantile) and CVaR (mean loss at or beyond it). Losses are positive. */
export function varCvar(losses: readonly number[], level: number): { var: number; cvar: number } {
  if (losses.length === 0) throw new Error("no losses");
  const v = quantile(losses, level);
  const tail = losses.filter((x) => x >= v);
  return { var: v, cvar: tail.reduce((a, b) => a + b, 0) / tail.length };
}

export interface StressSummary {
  fan: Record<string, number[]>;
  var95: number;
  cvar95: number;
  var99: number;
  cvar99: number;
  terminal: number[];
}

export function summarise(paths: Float64Array[]): StressSummary {
  const horizon = paths[0]?.length ?? 0;
  const fan: Record<string, number[]> = {};
  for (const q of FAN_QUANTILES) fan[String(q)] = [];
  for (let day = 0; day < horizon; day += 1) {
    const values = paths.map((p) => Math.exp(p[day]!) - 1);
    for (const q of FAN_QUANTILES) fan[String(q)]!.push(quantile(values, q));
  }
  const terminal = paths.map((p) => Math.exp(p[horizon - 1]!) - 1);
  const losses = terminal.map((r) => -r);
  const v95 = varCvar(losses, 0.95);
  const v99 = varCvar(losses, 0.99);
  return { fan, var95: v95.var, cvar95: v95.cvar, var99: v99.var, cvar99: v99.cvar, terminal };
}

/** Histogram of terminal returns for the distribution chart. */
export function histogram(values: readonly number[], bins: number): { lo: number; hi: number; count: number }[] {
  if (values.length === 0 || bins < 1) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = (max - min) / bins || 1;
  const counts = new Array<number>(bins).fill(0);
  for (const v of values) counts[Math.min(Math.floor((v - min) / width), bins - 1)]! += 1;
  return counts.map((count, i) => ({ lo: min + i * width, hi: min + (i + 1) * width, count }));
}
