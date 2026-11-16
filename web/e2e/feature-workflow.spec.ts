import { expect, openRoute, test } from "./fixtures";

test("標的比較 keeps settings after reload", async ({ page }) => {
  await openRoute(page, "/compare");
  await expect(page.getByRole("heading", { name: "標的比較" })).toBeVisible();
  await page.getByLabel("標的 A", { exact: true }).selectOption("2330");
  await page.getByLabel("標的 B", { exact: true }).selectOption("2330");
  await expect(page).toHaveURL(/against=2330/);
  await page.reload();
  await expect(page.getByLabel("標的 B", { exact: true })).toHaveValue("2330");
  const tradingDay = page.getByRole("slider", { name: "查看交易日" });
  const values = page.getByTestId("compare-trading-day-values");
  const latest = await tradingDay.getAttribute("aria-valuetext");
  await tradingDay.press("Home");
  await expect(tradingDay).toHaveValue("0");
  await expect(values).toContainText("100.00");
  await expect(values).toContainText("0.00 個百分點");
  await expect(tradingDay).not.toHaveAttribute("aria-valuetext", latest!);
  await tradingDay.press("End");
  await expect(tradingDay).toHaveAttribute("aria-valuetext", latest!);
  const downloadReady = page.waitForEvent("download");
  await page.getByRole("button", { name: "下載比較 CSV" }).click();
  expect((await downloadReady).suggestedFilename()).toBe("market-2330-2330.csv");
});

test("comparison links restore the selected session and swapping keeps that date", async ({ page }) => {
  await openRoute(page, "/compare?symbol=0050&against=2330&period=1y");
  const tradingDay = page.getByRole("slider", { name: "查看交易日" });
  await tradingDay.press("Home");
  const date = await tradingDay.getAttribute("aria-valuetext");
  await page.getByRole("link", { name: "開啟這一天的分享連結" }).click();
  await expect(page).toHaveURL(/date=\d{4}-\d{2}-\d{2}/);
  await page.reload();
  await expect(tradingDay).toHaveAttribute("aria-valuetext", date!);
  await page.getByRole("button", { name: "交換標的 A／B" }).click();
  await expect(page.getByLabel("標的 A", { exact: true })).toHaveValue("2330");
  await expect(page.getByLabel("標的 B", { exact: true })).toHaveValue("0050");
  await expect(tradingDay).toHaveAttribute("aria-valuetext", date!);
});
