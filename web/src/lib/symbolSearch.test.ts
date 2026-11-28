import { afterEach, describe, expect, it } from "vitest";
import { normalizeQuery, pushRecent, rankSymbols, readRecent, RECENT_LIMIT, withRecentFirst } from "./symbolSearch";

const options = [
  { symbol: "0050", name: "元大台灣50" },
  { symbol: "2330", name: "台積電" },
  { symbol: "2303", name: "聯電" },
  { symbol: "3105", name: "穩懋" },
  { symbol: "2317", name: "鴻海" },
  { symbol: "6230", name: "尼得科超眾" },
];

describe("normalizeQuery", () => {
  it("folds full-width digits, letters and spaces from a CJK IME", () => {
    expect(normalizeQuery("２３３０")).toBe("2330");
    expect(normalizeQuery("　ＥＴＦ ")).toBe("etf");
  });
});

describe("rankSymbols", () => {
  it("returns every option in data order for an empty query", () => {
    expect(rankSymbols(options, "  ").map((o) => o.symbol)).toEqual(options.map((o) => o.symbol));
  });

  it("puts an exact code first, then code prefixes, then other matches", () => {
    expect(rankSymbols(options, "2330").map((o) => o.symbol)).toEqual(["2330"]);
    expect(rankSymbols(options, "23").map((o) => o.symbol)).toEqual(["2330", "2303", "2317", "6230"]);
  });

  it("matches names, and every space-separated term must match", () => {
    expect(rankSymbols(options, "台積").map((o) => o.symbol)).toEqual(["2330"]);
    expect(rankSymbols(options, "2 鴻").map((o) => o.symbol)).toEqual(["2317"]);
    expect(rankSymbols(options, "xyz")).toEqual([]);
  });

  it("accepts a full-width code", () => {
    expect(rankSymbols(options, "２３３０").map((o) => o.symbol)).toEqual(["2330"]);
  });
});

describe("recent symbols", () => {
  afterEach(() => window.localStorage.clear());

  it("keeps the newest first, without duplicates, up to the limit", () => {
    for (const s of ["0050", "2330", "2317", "0050", "2303", "3105", "6230"]) pushRecent(s);
    expect(readRecent()).toEqual(["6230", "3105", "2303", "0050", "2317"]);
    expect(readRecent()).toHaveLength(RECENT_LIMIT);
  });

  it("treats corrupt storage as empty", () => {
    window.localStorage.setItem("mrl:recent-symbols", "{not json");
    expect(readRecent()).toEqual([]);
    window.localStorage.setItem("mrl:recent-symbols", JSON.stringify([1, "2330", null]));
    expect(readRecent()).toEqual(["2330"]);
  });

  it("lists recent symbols first and skips ones no longer in the data", () => {
    const rows = withRecentFirst(options, ["2317", "9999", "0050"]);
    expect(rows.map((r) => [r.option.symbol, r.recent])).toEqual([
      ["2317", true],
      ["0050", true],
      ["2330", false],
      ["2303", false],
      ["3105", false],
      ["6230", false],
    ]);
  });
});
