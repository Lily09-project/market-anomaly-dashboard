import { expect, it } from "vitest";
import { compareCloses, comparisonMetrics } from "./symbolComparison";

it("aligns valid closes, then normalizes the shared period", () => {
  const rows = compareCloses(["a", "b", "c", "d"], [100, 110, 120, 90], [200, NaN, 240, 240], 2);
  expect(rows).toEqual([{ date: "c", a: 100, b: 100 }, { date: "d", a: 75, b: 100 }]);
  expect(comparisonMetrics(rows!.map((row) => row.a))).toEqual({ total: -0.25, drawdown: -0.25, volatility: null });
  expect(compareCloses(["a", "b"], [100, 0], [100, 100], null)).toBeNull();
  expect(comparisonMetrics([100, 100, 100])).toEqual({ total: 0, drawdown: 0, volatility: 0 });
});
