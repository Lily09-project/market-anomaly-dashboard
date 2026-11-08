import { scaleLinear as d3ScaleLinear } from "d3-scale";
import { describe, expect, it } from "vitest";
import { scaleLinear } from "./scale";

const DOMAINS: [number, number][] = [
  [0, 1],
  [0, 249],
  [-0.0731, 0.0912],
  [0.93, 1.87],
  [1.87, 0.93],
  [-12.5, 3.25],
  [100, 100],
  [0, 0],
  [523.4, 1189.7],
  [-1e-4, 3e-4],
  [0, 17],
];
const RANGES: [number, number][] = [
  [52, 708],
  [298, 10],
  [0, 1],
];

describe("scaleLinear parity with d3-scale", () => {
  for (const domain of DOMAINS) {
    for (const range of RANGES) {
      it(`matches d3 for domain ${domain.join("..")} → ${range.join("..")}`, () => {
        for (const count of [undefined, 4, 5]) {
          const ours = scaleLinear().domain(domain).range(range).nice(count);
          const theirs = d3ScaleLinear().domain(domain).range(range).nice(count);
          expect(ours.domain()).toEqual(theirs.domain());
          expect(ours.ticks(count)).toEqual(theirs.ticks(count));
          const probes = [domain[0], domain[1], (domain[0] + domain[1]) / 2, ...theirs.ticks(count), -3, 1e6];
          for (const p of probes) expect(ours(p)).toBe(theirs(p));
        }
        const plain = scaleLinear().domain(domain).range(range);
        const plainD3 = d3ScaleLinear().domain(domain).range(range);
        expect(plain.domain()).toEqual(plainD3.domain());
        expect(plain.range()).toEqual(plainD3.range());
        expect(plain.ticks()).toEqual(plainD3.ticks());
        expect(plain(domain[0] * 0.3 + domain[1] * 0.7)).toBe(plainD3(domain[0] * 0.3 + domain[1] * 0.7));
      });
    }
  }

  it("returns undefined for missing values like d3", () => {
    const ours = scaleLinear().domain([0, 1]).range([0, 10]);
    expect(ours(Number.NaN)).toBeUndefined();
    expect(d3ScaleLinear().domain([0, 1]).range([0, 10])(Number.NaN)).toBeUndefined();
  });
});
