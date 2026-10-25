import { expect, expectAccessible, fetchJson, openRoute, test } from "./fixtures";

interface Provenance {
  provider: string;
  data_source: string;
  is_simulated: boolean;
  trading_days: number;
  symbols: string[];
  source_quality: { source_row_count: number; usable_price_rows: number; excluded_no_trade_rows: number } | null;
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
    expect(provenance.trading_days).toBeGreaterThanOrEqual(400);
    expect(provenance.symbols.slice().sort()).toEqual(["0050", "2317", "2330"]);
    expect(provenance.source_quality).not.toBeNull();
    expect(provenance.source_quality!.source_row_count).toBe(
      provenance.source_quality!.usable_price_rows + provenance.source_quality!.excluded_no_trade_rows,
    );
    expect(overview.dates.length).toBe(provenance.trading_days);
    expect(overview.symbols.map((item) => item.symbol).sort()).toEqual(["0050", "2317", "2330"]);
    for (const item of overview.symbols) {
      expect(item.close).toHaveLength(overview.dates.length);
      expect(item.close.every((value) => Number.isFinite(value) && value > 0)).toBe(true);
    }

    await openRoute(page, "/");
    await expect(page.getByTestId("total-return")).toBeVisible();
    await page.getByRole("radio", { name: /2330/ }).check();
    await expect(page).toHaveURL(/symbol=2330/);
    await expectAccessible(page);

    await openRoute(page, "/data");
    await expect(page.getByTestId("data-source")).toHaveText("FinMind public historical daily prices");
    await expect(page.getByTestId("integrity-summary")).toHaveText("6/6");
    await expectAccessible(page);
  });
});
