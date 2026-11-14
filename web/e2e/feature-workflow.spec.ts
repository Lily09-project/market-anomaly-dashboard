import { expect, openRoute, test } from "./fixtures";

test("標的比較 keeps settings after reload", async ({ page }) => {
  await openRoute(page, "/compare");
  await expect(page.getByRole("heading", { name: "標的比較" })).toBeVisible();
  await page.getByLabel("標的 A", { exact: true }).selectOption("2330");
  await page.getByLabel("標的 B", { exact: true }).selectOption("2330");
  await expect(page).toHaveURL(/against=2330/);
  await page.reload();
  await expect(page.getByLabel("標的 B", { exact: true })).toHaveValue("2330");
  await expect(page.getByRole("button", { name: "下載比較 CSV" })).toBeEnabled();
});
