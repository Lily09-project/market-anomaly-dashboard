import { expect, expectAccessible, fetchJson, openRoute, test } from "./fixtures";

interface Provenance {
  provider: string;
  data_source: string;
  is_simulated: boolean;
  trading_days: number;
  price_basis: { kind: string; cash_dividends_reinvested: boolean };
  symbols: string[];
  source_quality: { source_row_count: number; usable_price_rows: number; excluded_no_trade_rows: number } | null;
}

const SYMBOLS = ["0050", "1301", "2308", "2317", "2330", "2382", "2412", "2454", "2881", "2882"];

interface Twse {
  status: string;
  trade_date: string | null;
  symbols: Record<string, { close: number; cross_check: { match: boolean } | null }>;
}

interface Overview {
  dates: string[];
  symbols: { symbol: string; close: number[] }[];
}

test.describe("正式公開行情資料", () => {
  test("the public site renders verified FinMind data and its provenance", async ({ page }) => {
    const provenance = await fetchJson<Provenance>(page, "provenance.json");
    const overview = await fetchJson<Overview>(page, "overview.json");

    expect(provenance.provider).toBe("finmind");
    expect(provenance.data_source).toBe("FinMind public historical daily prices");
    expect(provenance.is_simulated).toBe(false);
    expect(provenance.price_basis.kind).toBe("known_split_adjusted");
    expect(provenance.price_basis.cash_dividends_reinvested).toBe(false);
    expect(provenance.trading_days).toBeGreaterThanOrEqual(400);
    expect(provenance.symbols.slice().sort()).toEqual(SYMBOLS);
    expect(provenance.source_quality).not.toBeNull();
    expect(provenance.source_quality!.source_row_count).toBe(
      provenance.source_quality!.usable_price_rows + provenance.source_quality!.excluded_no_trade_rows,
    );
    expect(overview.dates.length).toBe(provenance.trading_days);
    expect(overview.symbols.map((item) => item.symbol).sort()).toEqual(SYMBOLS);
    for (const item of overview.symbols) {
      expect(item.close).toHaveLength(overview.dates.length);
      expect(item.close.every((value) => Number.isFinite(value) && value > 0)).toBe(true);
    }

    const beforeSplit = overview.dates.indexOf("2025-06-10");
    const afterSplit = overview.dates.indexOf("2025-06-18");
    expect(beforeSplit).toBeGreaterThanOrEqual(0);
    expect(afterSplit).toBeGreaterThan(beforeSplit);
    const etf = overview.symbols.find((item) => item.symbol === "0050")!;
    // Official reference: 188.65 / 4 = 47.1625, not a 75% market loss.
    expect(etf.close[beforeSplit]).toBeCloseTo(47.1625, 3);
    expect(etf.close[afterSplit] / etf.close[beforeSplit]).toBeGreaterThan(0.8);
    expect(etf.close[afterSplit] / etf.close[beforeSplit]).toBeLessThan(1.2);
    // The TWSE snapshot is supplementary: it may be unavailable, but never simulated or mismatched.
    const twse = await fetchJson<Twse>(page, "twse.json");
    expect(["ok", "unavailable"]).toContain(twse.status);
    if (twse.status === "ok") {
      expect(Object.keys(twse.symbols).sort()).toEqual(SYMBOLS);
      for (const row of Object.values(twse.symbols)) {
        expect(row.close).toBeGreaterThan(0);
        if (row.cross_check) expect(row.cross_check.match).toBe(true);
      }
    }

    await openRoute(page, "/");
    await expect(page.getByTestId("total-return")).toBeVisible();
    await expect(page.getByTestId(twse.status === "ok" ? "twse-cross-check" : "twse-unavailable")).toBeVisible();
    await page.getByRole("radio", { name: /2330/ }).check();
    await expect(page).toHaveURL(/symbol=2330/);
    await expectAccessible(page);

    const market = await fetchJson<{ status: string; trade_date: string | null; rows: [string, string, number | null][] }>(page, "twse_market.json");
    expect(["ok", "unavailable"]).toContain(market.status);
    if (market.status === "ok") {
      expect(market.trade_date).toBe(twse.trade_date);
      expect(market.rows.length).toBeGreaterThan(900);
      const tsmc = market.rows.find((row) => row[0] === "2330");
      expect(tsmc?.[2]).toBe(twse.symbols["2330"]?.close);
      await openRoute(page, "/market?q=2330");
      await expect(page.getByTestId("market-table").locator("tbody tr")).toHaveCount(1);
      await expectAccessible(page);
    }

    await openRoute(page, "/data");
    await expect(page.getByTestId("data-source")).toHaveText("FinMind public historical daily prices");
    await expect(page.getByTestId("integrity-summary")).toHaveText("8/8");
    await expect(page.getByRole("heading", { name: "價格還原基準" })).toBeVisible();
    await expectAccessible(page);
  });
});
