import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";
import type { Segment } from "../lib/types";
import "./charts.css";
import { ScrollRegion } from "./ScrollRegion";

/** Fallback width before the container has been measured (and in tests). */
const W = 520;

/**
 * Measure the chart's container so the viewBox matches real pixels: text stays
 * 13px on a wide desktop card and on a phone instead of scaling with the card.
 */
function useChartWidth(): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(W);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const next = Math.round(entry?.contentRect.width ?? 0);
      if (next > 0) setWidth(Math.min(Math.max(next, 280), 1200));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** Every chart pairs its SVG with an equivalent table for screen readers. */
export function ChartFrame({ title, summary, table, children }: { title: string; summary: string; table: ReactNode; children: ReactNode }) {
  const id = useId();
  return (
    <figure className="chart-frame" aria-labelledby={`${id}-title`}>
      <figcaption id={`${id}-title`} className="chart-title">
        {title}
      </figcaption>
      <div role="img" aria-label={`${title}：${summary}`}>
        {children}
      </div>
      <details className="data-table">
        <summary>以表格檢視資料</summary>
        <ScrollRegion label={`${title}（資料表）`}>{table}</ScrollRegion>
      </details>
    </figure>
  );
}

export interface Series {
  key: string;
  label: string;
  values: (number | null)[];
  /** 1–4 picks the colour and dash pattern, so series never rely on colour alone. */
  tone: 1 | 2 | 3 | 4;
  /** Optional uncertainty band drawn behind the line. */
  low?: (number | null)[];
  high?: (number | null)[];
}

const defined = (v: number | null | undefined): v is number => v !== null && v !== undefined && Number.isFinite(v);

/**
 * Line chart over an index axis with optional bands, background state
 * stripes, a zero/reference line and a vertical marker.
 */
export function LineChart({
  series,
  labels,
  format = (v) => String(v),
  height = 240,
  reference,
  marker,
  stripes,
  stripeOffset = 0,
  ticks = 4,
}: {
  series: Series[];
  labels: string[];
  format?: (v: number) => string;
  height?: number;
  reference?: { value: number; label: string };
  marker?: number;
  /** Regime segments drawn as background stripes; indexes are shifted by stripeOffset. */
  stripes?: Segment[];
  stripeOffset?: number;
  ticks?: number;
}) {
  const [box, width] = useChartWidth();
  const left = 52;
  const right = width - 12;
  const values = series.flatMap((s) => [...s.values, ...(s.low ?? []), ...(s.high ?? [])].filter(defined));
  if (reference) values.push(reference.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.1 || 1;
  const x = scaleLinear().domain([0, Math.max(labels.length - 1, 1)]).range([left, right]);
  const y = scaleLinear().domain([lo - pad, hi + pad]).range([height - 26, 10]).nice();
  const tickIndexes = Array.from({ length: Math.min(ticks, labels.length) }, (_, i) => Math.round((i * (labels.length - 1)) / Math.max(ticks - 1, 1)));
  return (
    <div ref={box} className="chart-box">
      <svg className="chart line-chart" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {stripes?.map(([start, end, state]) => (
          <rect
            key={`${start}-${state}`}
            className="stripe"
            data-state={state}
            x={x(start + stripeOffset)}
            width={Math.max(x(end + stripeOffset + 1) - x(start + stripeOffset), 1)}
            y={10}
            height={height - 36}
          />
        ))}
        {y.ticks(4).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={left} x2={right} y1={y(t)} y2={y(t)} />
            <text x={left - 6} y={y(t) + 4} textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        {reference && (
          <g>
            <line className="reference-line" x1={left} x2={right} y1={y(reference.value)} y2={y(reference.value)} />
            <text x={right} y={y(reference.value) - 5} textAnchor="end" className="reference-label">
              {reference.label}
            </text>
          </g>
        )}
        {series.map((s) =>
          s.low && s.high ? (
            <path
              key={`${s.key}-band`}
              className={`band band-${s.tone}`}
              d={
                area<number>()
                  .defined((i) => defined(s.low?.[i]) && defined(s.high?.[i]))
                  .x((i) => x(i))
                  .y0((i) => y(s.low?.[i] ?? 0))
                  .y1((i) => y(s.high?.[i] ?? 0))(s.values.map((_, i) => i)) ?? ""
              }
            />
          ) : null,
        )}
        {series.map((s) => (
          <path
            key={s.key}
            className={`series series-${s.tone}`}
            d={
              line<number | null>()
                .defined(defined)
                .x((_, i) => x(i))
                .y((v) => y(v ?? 0))(s.values) ?? ""
            }
          />
        ))}
        {marker !== undefined && <line className="marker-line" x1={x(marker)} x2={x(marker)} y1={6} y2={height - 26} />}
        {tickIndexes.map((i, k) => (
          <text key={i} x={x(i)} y={height - 8} textAnchor={k === 0 ? "start" : k === tickIndexes.length - 1 ? "end" : "middle"}>
            {labels[i]}
          </text>
        ))}
      </svg>
    </div>
  );
}

export function Legend({ items }: { items: { key: string; label: string; tone?: 1 | 2 | 3 | 4; state?: number }[] }) {
  return (
    <ul className="legend">
      {items.map((item) => (
        <li key={item.key}>
          {item.state !== undefined ? (
            <span className="legend-swatch" data-state={item.state} aria-hidden="true" />
          ) : (
            <svg width="28" height="10" aria-hidden="true">
              <line x1="1" x2="27" y1="5" y2="5" className={`series series-${item.tone ?? 1}`} />
            </svg>
          )}
          {item.label}
        </li>
      ))}
    </ul>
  );
}

/** Percentile fan: 5–95% and 25–75% bands with the median line. */
export function FanChart({ fan, format, height = 260 }: { fan: Record<string, number[]>; format: (v: number) => string; height?: number }) {
  const [box, width] = useChartWidth();
  const p5 = fan["0.05"] ?? [];
  const p25 = fan["0.25"] ?? [];
  const p50 = fan["0.5"] ?? [];
  const p75 = fan["0.75"] ?? [];
  const p95 = fan["0.95"] ?? [];
  const left = 56;
  const right = width - 12;
  const all = [...p5, ...p95, 0];
  const x = scaleLinear().domain([0, Math.max(p50.length, 1)]).range([left, right]);
  const y = scaleLinear().domain([Math.min(...all), Math.max(...all)]).range([height - 26, 10]).nice();
  const band = (lo: number[], hi: number[]) =>
    area<number>()
      .x((i) => x(i + 1))
      .y0((i) => y(lo[i] ?? 0))
      .y1((i) => y(hi[i] ?? 0))(lo.map((_, i) => i)) ?? "";
  return (
    <div ref={box} className="chart-box">
      <svg className="chart fan-chart" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {y.ticks(5).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={left} x2={right} y1={y(t)} y2={y(t)} />
            <text x={left - 6} y={y(t) + 4} textAnchor="end">
              {format(t)}
            </text>
          </g>
        ))}
        <line className="reference-line" x1={left} x2={right} y1={y(0)} y2={y(0)} />
        <path className="fan-outer" d={band(p5, p95)} />
        <path className="fan-inner" d={band(p25, p75)} />
        <path className="series series-1" d={line<number>().x((_, i) => x(i + 1)).y((v) => y(v))(p50) ?? ""} />
        <text x={left} y={height - 8}>
          第 1 天
        </text>
        <text x={right} y={height - 8} textAnchor="end">
          第 {p50.length} 天
        </text>
      </svg>
    </div>
  );
}

export function Histogram({
  bins,
  format,
  highlight,
  height = 200,
}: {
  bins: { lo: number; hi: number; count: number }[];
  format: (v: number) => string;
  /** Bins whose upper edge is at or below this value are highlighted (the loss tail). */
  highlight?: number;
  height?: number;
}) {
  const [box, width] = useChartWidth();
  const left = 40;
  const right = width - 12;
  const lo = bins[0]?.lo ?? 0;
  const hi = bins.at(-1)?.hi ?? 1;
  const x = scaleLinear().domain([lo, hi]).range([left, right]);
  const y = scaleLinear().domain([0, Math.max(...bins.map((b) => b.count), 1)]).range([height - 26, 10]).nice();
  return (
    <div ref={box} className="chart-box">
      <svg className="chart histogram" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {y.ticks(4).map((t) => (
          <g key={t}>
            <line className="grid-line" x1={left} x2={right} y1={y(t)} y2={y(t)} />
            <text x={left - 6} y={y(t) + 4} textAnchor="end">
              {t}
            </text>
          </g>
        ))}
        {bins.map((b) => (
          <rect
            key={b.lo}
            className={highlight !== undefined && b.hi <= highlight ? "bar bar-tail" : "bar"}
            x={x(b.lo) + 0.5}
            width={Math.max(x(b.hi) - x(b.lo) - 1, 1)}
            y={y(b.count)}
            height={Math.max(height - 26 - y(b.count), 0)}
          />
        ))}
        {highlight !== undefined && <line className="reference-line" x1={x(highlight)} x2={x(highlight)} y1={10} y2={height - 26} />}
        {x.ticks(5).map((t) => (
          <text key={t} x={x(t)} y={height - 8} textAnchor="middle">
            {format(t)}
          </text>
        ))}
      </svg>
    </div>
  );
}

/** Horizontal bars around zero (used for the logit distribution and per-fold Sharpe). */
export function DivergingBars({ rows, format, height = 28 }: { rows: { key: string; label: string; value: number }[]; format: (v: number) => string; height?: number }) {
  const [box, width] = useChartWidth();
  const labelWidth = 120;
  const extent = Math.max(...rows.map((r) => Math.abs(r.value)), 0.1);
  const x = scaleLinear().domain([-extent, extent]).range([labelWidth + 44, width - 52]);
  const total = rows.length * height + 8;
  return (
    <div ref={box} className="chart-box">
      <svg className="chart diverging" viewBox={`0 0 ${width} ${total}`} aria-hidden="true">
        <line className="zero" x1={x(0)} x2={x(0)} y1={0} y2={total} />
        {rows.map((r, i) => {
          const y = i * height + 4;
          return (
            <g key={r.key}>
              <text x={0} y={y + height / 2} className="row-label">
                {r.label}
              </text>
              <rect className={r.value >= 0 ? "pos" : "neg"} x={Math.min(x(0), x(r.value))} y={y + 4} width={Math.abs(x(r.value) - x(0))} height={height - 12} rx={3} />
              <text x={r.value >= 0 ? x(r.value) + 6 : x(r.value) - 6} y={y + height / 2} textAnchor={r.value >= 0 ? "start" : "end"} className="value-label">
                {format(r.value)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/** One row of state stripes per path (e.g. the HMM next to the ground truth). */
export function StateTimeline({ rows, length, labels }: { rows: { key: string; label: string; segments: Segment[] }[]; length: number; labels: string[] }) {
  const [box, width] = useChartWidth();
  const left = 92;
  const right = width - 12;
  const rowHeight = 30;
  const x = scaleLinear().domain([0, Math.max(length, 1)]).range([left, right]);
  const height = rows.length * (rowHeight + 10) + 20;
  return (
    <div ref={box} className="chart-box">
      <svg className="chart timeline" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        {rows.map((row, r) => {
          const y = r * (rowHeight + 10) + 4;
          return (
            <g key={row.key}>
              <text x={left - 8} y={y + rowHeight / 2 + 4} textAnchor="end" className="row-label">
                {row.label}
              </text>
              {row.segments.map(([start, end, state]) => (
                <rect key={start} className="timeline-cell" data-state={state} x={x(start)} width={Math.max(x(end + 1) - x(start), 0.5)} y={y} height={rowHeight}>
                  <title>{labels[state]}</title>
                </rect>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
