import { expect, openRoute, test } from "./fixtures";

// The header's nine tabs, brand and data badge share one row on laptops. The
// badge is given the longest production label so sample data cannot hide an
// overflow that only shows with "FinMind 日資料".
const WIDTHS = [1024, 1100, 1199, 1200, 1280, 1359, 1360, 1440];

test("the header navigation never scrolls sideways on laptop widths", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-dark", "viewport is set by the test; one project is enough");
  await openRoute(page, "/");
  await page.locator("[data-testid=data-badge]").evaluate((badge) => {
    badge.textContent = "FinMind 日資料";
  });
  for (const width of WIDTHS) {
    await page.setViewportSize({ width, height: 800 });
    const fit = await page.evaluate(() => {
      const nav = document.querySelector<HTMLElement>(".site-nav")!;
      const header = document.querySelector<HTMLElement>(".site-header")!;
      return { overflow: nav.scrollWidth - nav.clientWidth, height: header.getBoundingClientRect().height };
    });
    expect(fit.overflow, `nav overflow at ${width}px`).toBeLessThanOrEqual(0);
    expect(fit.height, `header height at ${width}px`).toBeLessThan(72);
  }
});
