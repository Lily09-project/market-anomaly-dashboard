/** Positive closes on shared trading dates, normalized to the first shared close. */
export function compareCloses(dates: readonly string[], a: readonly number[], b: readonly number[], lastDays: number | null) {
  const shared = dates.flatMap((date, i) => {
    const left = a[i];
    const right = b[i];
    return left !== undefined && right !== undefined && Number.isFinite(left) && Number.isFinite(right) && left > 0 && right > 0
      ? [{ date, left, right }] : [];
  });
  const rows = lastDays === null ? shared : shared.slice(-lastDays);
  const first = rows[0];
  if (!first || rows.length < 2) return null;
  return rows.map(({ date, left, right }) => ({ date, a: 100 * left / first.left, b: 100 * right / first.right }));
}

export function comparisonMetrics(index: readonly number[]) {
  let peak = index[0]!;
  let drawdown = 0;
  const changes = index.slice(1).map((value, i) => value / index[i]! - 1);
  for (const value of index) {
    peak = Math.max(peak, value);
    drawdown = Math.min(drawdown, value / peak - 1);
  }
  const mean = changes.reduce((sum, value) => sum + value, 0) / changes.length;
  const variance = changes.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (changes.length - 1);
  return { total: index.at(-1)! / index[0]! - 1, drawdown, volatility: changes.length > 1 ? Math.sqrt(252 * variance) : null };
}
