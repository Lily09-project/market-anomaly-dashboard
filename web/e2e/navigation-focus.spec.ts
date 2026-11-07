import { expect, openRoute, test } from "./fixtures";

test("keyboard focus reaches main while a lazy page is loading", async ({ page }) => {
  let releaseChunk!: () => void;
  const pendingChunk = new Promise<void>((resolve) => {
    releaseChunk = resolve;
  });

  await page.route(/\/assets\/DataTrust-[^/]+\.js(?:\?.*)?$/, async (route) => {
    await pendingChunk;
    await route.continue();
  });
  const main = page.getByRole("main");
  try {
    await openRoute(page, "/");
    await expect(main).not.toBeFocused();
    const link = page.getByRole("navigation", { name: "主要頁面" })
      .getByRole("link", { name: "資料可信度" });
    await link.focus();
    await link.press("Enter");
    await expect(main.getByText("頁面載入中…")).toBeVisible();
    await expect(main).toBeFocused();
  } finally {
    releaseChunk();
  }

  await expect(main.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(main).toBeFocused();
});
