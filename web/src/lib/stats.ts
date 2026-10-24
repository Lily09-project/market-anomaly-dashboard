/** Linear-interpolated quantile, q in [0, 1] (same definition as numpy's default). */
export function quantile(values: readonly number[], q: number): number {
  if (values.length === 0) return Number.NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const position = (sorted.length - 1) * Math.min(Math.max(q, 0), 1);
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const lo = sorted[lower] as number;
  const hi = sorted[upper] as number;
  return lo + (hi - lo) * (position - lower);
}
