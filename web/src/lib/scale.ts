/**
 * Minimal linear scale with the same output as d3-scale's `scaleLinear` for
 * the subset the charts use (two-point domain/range, `nice()`, `ticks()`).
 *
 * d3-scale also bundles d3-format, d3-interpolate and d3-color for features the
 * site never calls; this keeps the initial JavaScript smaller. The parity test
 * compares every method against d3-scale itself.
 */
import { tickIncrement, ticks as arrayTicks } from "d3-array";

export interface LinearScale {
  (value: number): number;
  domain(): [number, number];
  domain(domain: readonly [number, number]): LinearScale;
  range(): [number, number];
  range(range: readonly [number, number]): LinearScale;
  nice(count?: number): LinearScale;
  ticks(count?: number): number[];
}

export function scaleLinear(): LinearScale {
  let d: [number, number] = [0, 1];
  let r: [number, number] = [0, 1];

  const scale = ((value: number) => {
    if (value == null || Number.isNaN((value = +value))) return undefined as unknown as number;
    // Same arithmetic as d3: normalize the domain to t, then interpolateNumber on the range.
    let [d0, d1] = d;
    let [r0, r1] = r;
    if (d1 < d0) [d0, d1, r0, r1] = [d1, d0, r1, r0];
    const span = d1 - d0;
    const t = span ? (value - d0) / span : Number.isNaN(span) ? NaN : 0.5;
    return r0 * (1 - t) + r1 * t;
  }) as LinearScale;

  scale.domain = ((next?: readonly [number, number]) => {
    if (next === undefined) return [d[0], d[1]];
    d = [+next[0], +next[1]];
    return scale;
  }) as LinearScale["domain"];

  scale.range = ((next?: readonly [number, number]) => {
    if (next === undefined) return [r[0], r[1]];
    r = [+next[0], +next[1]];
    return scale;
  }) as LinearScale["range"];

  scale.ticks = (count = 10) => arrayTicks(d[0], d[1], count);

  // Port of d3-scale's linearish().nice().
  scale.nice = (count = 10) => {
    const reversed = d[1] < d[0];
    let start = reversed ? d[1] : d[0];
    let stop = reversed ? d[0] : d[1];
    let prestep: number | undefined;
    let step: number;
    let maxIter = 10;
    while (maxIter-- > 0) {
      step = tickIncrement(start, stop, count);
      if (step === prestep) {
        d = reversed ? [stop, start] : [start, stop];
        return scale;
      } else if (step > 0) {
        start = Math.floor(start / step) * step;
        stop = Math.ceil(stop / step) * step;
      } else if (step < 0) {
        start = Math.ceil(start * step) / step;
        stop = Math.floor(stop * step) / step;
      } else {
        break;
      }
      prestep = step;
    }
    return scale;
  };

  return scale;
}
