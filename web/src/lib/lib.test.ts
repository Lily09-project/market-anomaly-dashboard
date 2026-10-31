import { describe, expect, it, vi } from "vitest";
import { downloadText, escapeCell, toCsv } from "./csv";
import { createLoader, IntegrityError, sha256Hex } from "./data";
import stressFixture from "./fixtures/stress-parity.json";
import { formatNumber, formatPercent, formatSigned, formatSignedPercent } from "./format";
import { agreement, drawdowns, heatmap, rankCorrelation, rollingVolatility, sampledDates, statesByDay } from "./market";
import { mulberry32 } from "./rng";
import { selectMarketRows } from "./marketTable";
import { parseRoute, routeToHash, type Route } from "./router";
import type { MarketRow } from "./types";
import { canonicalJson, createSnapshot, diffSnapshots, MAX_SNAPSHOT_BYTES, validateSnapshot, type SnapshotBody } from "./snapshot";
import { quantile } from "./stats";
import { blockBootstrap, histogram, logReturns, summarise, varCvar } from "./stress";
import type { Segment, StressParity } from "./types";

describe("stress engine (mirrors src/analytics/risk.py)", () => {
  const fixture = stressFixture as { closes: Record<string, number[]>; parity: StressParity[] };

  it("mulberry32 matches the Python port", () => {
    const draw = mulberry32(20261024);
    expect([draw(), draw(), draw()]).toEqual([0.28407089272513986, 0.5368913877755404, 0.6360740626696497]);
  });

  it("reproduces every Python reference case", () => {
    expect(fixture.parity.length).toBeGreaterThanOrEqual(4);
    for (const c of fixture.parity) {
      const returns = logReturns(fixture.closes[c.symbol]!);
      const s = summarise(blockBootstrap(returns, c));
      expect(Math.abs(s.var95 - c.var95)).toBeLessThan(1e-9);
      expect(Math.abs(s.cvar95 - c.cvar95)).toBeLessThan(1e-9);
      expect(Math.abs(s.var99 - c.var99)).toBeLessThan(1e-9);
      expect(Math.abs(s.cvar99 - c.cvar99)).toBeLessThan(1e-9);
      expect(Math.abs(s.fan["0.5"]!.at(-1)! - c.median_last)).toBeLessThan(1e-9);
    }
  });

  it("is reproducible, reports progress and validates the block length", () => {
    const returns = Array.from({ length: 50 }, (_, i) => (i % 7) / 1000 - 0.003);
    const params = { horizon: 12, block: 4, paths: 500, seed: 3 };
    const progress = vi.fn();
    const a = blockBootstrap(returns, params, progress);
    expect(blockBootstrap(returns, params)).toEqual(a);
    expect(progress).toHaveBeenCalledWith(250);
    expect(a).toHaveLength(500);
    expect(a[0]).toHaveLength(12);
    expect(() => blockBootstrap(returns, { ...params, block: 51 })).toThrow();
    expect(() => blockBootstrap(returns, { ...params, block: 0 })).toThrow();
  });

  it("computes VaR and CVaR on a known distribution", () => {
    const losses = Array.from({ length: 100 }, (_, i) => (i + 1) / 100);
    const r = varCvar(losses, 0.95);
    expect(r.var).toBeCloseTo(quantile(losses, 0.95), 12);
    expect(r.cvar).toBeCloseTo(losses.filter((x) => x >= r.var).reduce((a, b) => a + b, 0) / losses.filter((x) => x >= r.var).length, 12);
    expect(r.cvar).toBeGreaterThanOrEqual(r.var);
    expect(() => varCvar([], 0.9)).toThrow();
    const s = summarise(blockBootstrap(logReturns(fixture.closes["0050"]!), { horizon: 20, block: 5, paths: 400, seed: 1 }));
    expect(s.cvar99).toBeGreaterThanOrEqual(s.var99);
    expect(s.var99).toBeGreaterThanOrEqual(s.var95);
    expect(s.terminal).toHaveLength(400);
    expect(s.fan["0.05"]![10]!).toBeLessThanOrEqual(s.fan["0.95"]![10]!);
  });

  it("bins terminal returns", () => {
    const bins = histogram([0, 0.1, 0.2, 0.3, 0.4], 2);
    expect(bins.map((b) => b.count)).toEqual([2, 3]);
    expect(histogram([], 3)).toEqual([]);
    expect(histogram([1, 1], 2)[0]!.count).toBe(2);
  });
});

describe("market helpers", () => {
  const segments: Segment[] = [
    [0, 2, 0],
    [3, 4, 2],
  ];

  it("expands segments and measures agreement", () => {
    expect(statesByDay(segments, 6)).toEqual([0, 0, 0, 2, 2, -1]);
    expect(agreement(segments, [[0, 4, 0]], 5)).toBeCloseTo(0.6);
    expect(agreement([], [], 0)).toBe(0);
  });

  it("computes rolling volatility and drawdowns", () => {
    const vol = rollingVolatility([0.01, -0.01, 0.01, -0.01], 2);
    expect(vol[0]).toBeNull();
    expect(vol[1]!).toBeCloseTo(Math.sqrt(0.0002 * 252), 10);
    expect(vol[3]!).toBeCloseTo(vol[1]!, 10);
    expect(drawdowns([100, 120, 90, 130])).toEqual([0, 0, -0.25, 0]);
  });

  it("lays out the parameter heatmap and ranks agreement", () => {
    const grid = heatmap({ fast: [5, 50], slow: [20, 50], grid: [[5, 20], [5, 50]] }, [1, 2]);
    expect(grid[0]!.map((c) => c?.value)).toEqual([1, 2]);
    expect(grid[1]).toEqual([null, null]);
    expect(rankCorrelation([1, 2, 3], [10, 20, 30])).toBeCloseTo(1);
    expect(rankCorrelation([1, 2, 3], [3, 2, 1])).toBeCloseTo(-1);
    expect(rankCorrelation([1, 1, 2], [5, 5, 9])).toBeCloseTo(1);
    expect(rankCorrelation([1, 1], [2, 3])).toBe(0);
  });

  it("maps a sampled equity curve back to dates", () => {
    const dates = ["d0", "d1", "d2", "d3", "d4"];
    expect(sampledDates(dates, "d1", 2, 3)).toEqual(["d1", "d3", "d4"]);
    expect(sampledDates(dates, "nope", 2, 3)).toEqual([]);
  });
});

const body = (overrides: Partial<SnapshotBody> = {}): Omit<SnapshotBody, "kind" | "version"> => ({
  label: "測試",
  data: { input_sha256: "a".repeat(64), schema_version: "2.0", range: { start: "2021-01-01", end: "2025-12-31" } },
  symbol: "0050",
  params: { horizon: 60, block: 10, paths: 2000, seed: 1 },
  results: {
    regime_state: "平穩",
    regime_probability: 0.9,
    regime_accuracy: 0.91,
    pbo: 0.45,
    dsr: 0.7,
    walk_forward_sharpe: -0.3,
    event_post_car_3d: 0.015,
    var95: 0.2,
    cvar95: 0.25,
    var99: null,
    cvar99: null,
  },
  ...overrides,
});

describe("research snapshots", () => {
  it("serialises canonically", () => {
    expect(canonicalJson({ b: 1, a: [true, null, { d: "x", c: 2 }] })).toBe('{"a":[true,null,{"c":2,"d":"x"}],"b":1}');
  });

  it("round-trips and keeps the same fingerprint", async () => {
    const snapshot = await createSnapshot(body());
    const text = JSON.stringify(snapshot, null, 2);
    const result = await validateSnapshot(text);
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.snapshot.fingerprint).toBe(snapshot.fingerprint);
    // Key order does not matter, only content.
    const reordered = JSON.stringify(Object.fromEntries(Object.entries(snapshot).reverse()));
    expect((await validateSnapshot(reordered)).ok).toBe(true);
    expect((await createSnapshot(body({ label: "x".repeat(500) }))).label).toHaveLength(120);
  });

  it("rejects tampered, malformed and oversized files with a reason", async () => {
    const snapshot = await createSnapshot(body());
    const tampered = { ...snapshot, results: { ...snapshot.results, pbo: 0.01 } };
    expect(await validateSnapshot(JSON.stringify(tampered))).toEqual({ ok: false, reason: "指紋不符：檔案在匯出後被修改過" });
    expect(await validateSnapshot("{not json")).toMatchObject({ ok: false, reason: expect.stringContaining("JSON") });
    expect(await validateSnapshot("[1,2]")).toMatchObject({ ok: false, reason: expect.stringContaining("物件") });
    expect(await validateSnapshot(JSON.stringify({ ...snapshot, kind: "other" }))).toMatchObject({ ok: false, reason: expect.stringContaining("kind") });
    expect(await validateSnapshot(JSON.stringify({ ...snapshot, symbol: "<script>" }))).toMatchObject({ ok: false, reason: expect.stringContaining("symbol") });
    expect(await validateSnapshot(JSON.stringify({ ...snapshot, results: { ...snapshot.results, var95: "1" } }))).toMatchObject({
      ok: false,
      reason: expect.stringContaining("results"),
    });
    expect(await validateSnapshot(" ".repeat(MAX_SNAPSHOT_BYTES + 1))).toMatchObject({ ok: false, reason: expect.stringContaining("KB") });
  });

  it("lists differences between two snapshots", async () => {
    const a = await createSnapshot(body());
    const b = await createSnapshot(body({ symbol: "2330", params: { horizon: 20, block: 10, paths: 2000, seed: 1 } }));
    const rows = diffSnapshots(a, b);
    expect(rows.find((r) => r.key === "symbol")).toMatchObject({ a: "0050", b: "2330", changed: true });
    expect(rows.find((r) => r.key === "params.horizon")?.changed).toBe(true);
    expect(rows.find((r) => r.key === "params.block")?.changed).toBe(false);
    expect(rows.filter((r) => r.key.startsWith("results."))).toHaveLength(11);
  });
});

describe("router", () => {
  it("round-trips every route and validates parameters", () => {
    const routes: Route[] = [
      { name: "home", symbol: "2330", period: "1y" },
      { name: "home", symbol: undefined, period: undefined },
      { name: "regimes", symbol: "0050" },
      { name: "events", symbol: "2317", date: "2023-05-02" },
      { name: "backtest", symbol: "RANDOM", cell: 4 },
      { name: "stress", symbol: "0050", horizon: 60, block: 10, paths: 2000 },
      { name: "market", q: "台積", sort: "change_pct", desc: true, kind: "stock" },
      { name: "market", q: undefined, sort: undefined, desc: undefined, kind: undefined },
      { name: "snapshot" },
      { name: "data" },
    ];
    for (const route of routes) expect(parseRoute(routeToHash(route))).toEqual(route);
    expect(parseRoute("")).toEqual({ name: "home", symbol: undefined, period: undefined });
    expect(parseRoute("#/?period=10y")).toMatchObject({ period: undefined });
    expect(parseRoute("#/stress?horizon=9999&block=0&paths=abc")).toEqual({ name: "stress", symbol: undefined, horizon: undefined, block: undefined, paths: undefined });
    expect(parseRoute("#/events?date=yesterday")).toMatchObject({ date: undefined });
    expect(parseRoute("#/market?sort=price&kind=bond&desc=yes")).toEqual({ name: "market", q: undefined, sort: undefined, desc: undefined, kind: undefined });
    expect(parseRoute("#/nope")).toEqual({ name: "not-found", path: "/nope" });
    expect(routeToHash({ name: "not-found", path: "/nope" })).toBe("#/nope");
  });
});

describe("format, csv and data loader", () => {
  it("formats numbers", () => {
    expect(formatNumber(1.234, 2)).toBe("1.23");
    expect(formatNumber(null)).toBe("—");
    expect(formatPercent(0.1234)).toBe("12.3%");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatSigned(0.5)).toBe("+0.50");
    expect(formatSigned(-0.001)).toBe("0.00");
    expect(formatSigned(-1)).toBe("-1.00");
    expect(formatSigned(null)).toBe("—");
    expect(formatSignedPercent(0.015)).toBe("+1.5%");
    expect(formatSignedPercent(null)).toBe("—");
  });

  it("neutralises spreadsheet formulas", () => {
    for (const attack of ["=1+1", "+1", "-1+1", "@SUM(1)", "\t=1"]) expect(escapeCell(attack).replace(/^"/, "")).toMatch(/^'/);
    expect(toCsv(["date", "z"], [{ date: "2024-01-02", z: -5.2 }]).startsWith("﻿date,z\r\n2024-01-02,-5.2")).toBe(true);
  });

  it("verifies files against the manifest", async () => {
    const encoder = new TextEncoder();
    const respond = (text: string, status = 200) => new Response(encoder.encode(text), { status });
    const body = '{"dates":[]}';
    const digest = await sha256Hex(encoder.encode(body).buffer as ArrayBuffer);
    const fetcher = vi.fn(async (url: string) =>
      url.endsWith("manifest.json") ? respond(JSON.stringify({ schema_version: "2.0", files: { "overview.json": digest } })) : url.endsWith("overview.json") ? respond(body) : respond("x", 404),
    );
    const loader = createLoader("./", fetcher);
    await expect(loader.load("overview.json")).resolves.toEqual({ dates: [] });
    await expect(loader.load("events.json")).rejects.toThrow("HTTP 404");
    const bad = createLoader("./", async (url: string) =>
      url.endsWith("manifest.json") ? respond(JSON.stringify({ schema_version: "2.0", files: { "events.json": "0".repeat(64) } })) : respond("{}"),
    );
    await expect(bad.load("events.json")).rejects.toBeInstanceOf(IntegrityError);
  });

  it("revalidates once after a redeploy and recovers from a failed manifest request", async () => {
    const encoder = new TextEncoder();
    const respond = (text: string, status = 200) => new Response(encoder.encode(text), { status });
    const oldBody = '{"dates":["a"]}';
    const newBody = '{"dates":["b"]}';
    const digest = async (text: string) => sha256Hex(encoder.encode(text).buffer as ArrayBuffer);
    const manifests = [await digest(oldBody), await digest(newBody)];
    let deployed = 0;
    const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.cache === "reload") deployed = 1;
      return url.endsWith("manifest.json")
        ? respond(JSON.stringify({ schema_version: "2.1", files: { "overview.json": manifests[deployed] } }))
        : respond(newBody);
    });
    await expect(createLoader("./", fetcher).load("overview.json")).resolves.toEqual({ dates: ["b"] });
    expect(fetcher.mock.calls.filter(([, init]) => init?.cache === "reload")).toHaveLength(2);

    let failManifest = true;
    const flaky = createLoader("./", async (url: string) => {
      if (url.endsWith("manifest.json")) {
        if (failManifest) {
          failManifest = false;
          return respond("down", 503);
        }
        return respond(JSON.stringify({ schema_version: "2.1", files: { "overview.json": manifests[1] } }));
      }
      return respond(newBody);
    });
    await expect(flaky.load("overview.json")).rejects.toThrow("HTTP 503");
    await expect(flaky.load("overview.json")).resolves.toEqual({ dates: ["b"] });
  });
});

describe("downloadText", () => {
  it("creates and revokes an object URL for the download", async () => {
    const create = vi.fn(() => "blob:test");
    const revoke = vi.fn();
    Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    downloadText("snapshot.json", "{}", "application/json");
    expect(create).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(document.querySelector("a[download]")).toBeNull();
    await new Promise((r) => setTimeout(r, 0));
    expect(revoke).toHaveBeenCalledWith("blob:test");
  });
});

describe("market table", () => {
  const row = (code: string, name: string, pct: number | null, pe: number | null): MarketRow => [code, name, 10, 1, pct, 1e8, pe, null, null, 0, 0];
  const rows = [row("2330", "台積電", 0.02, 27), row("0050", "元大台灣50", -0.01, null), row("2317", "鴻海", null, 16), row("1101", "台泥", 0.05, 12)];

  it("searches code or name and filters by kind", () => {
    expect(selectMarketRows(rows, { q: "台" }).map((r) => r[0])).toEqual(["0050", "1101", "2330"]);
    expect(selectMarketRows(rows, { q: "23" }).map((r) => r[0])).toEqual(["2317", "2330"]);
    expect(selectMarketRows(rows, { kind: "etf" }).map((r) => r[0])).toEqual(["0050"]);
    expect(selectMarketRows(rows, { kind: "stock" })).toHaveLength(3);
  });

  it("sorts both ways and keeps missing values last", () => {
    expect(selectMarketRows(rows, { sort: "change_pct" }).map((r) => r[0])).toEqual(["0050", "2330", "1101", "2317"]);
    expect(selectMarketRows(rows, { sort: "change_pct", desc: true }).map((r) => r[0])).toEqual(["1101", "2330", "0050", "2317"]);
    expect(selectMarketRows(rows, { sort: "pe", desc: true }).map((r) => r[0])).toEqual(["2330", "2317", "1101", "0050"]);
  });
});
