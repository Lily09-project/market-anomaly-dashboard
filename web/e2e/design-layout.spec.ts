import { expect, openRoute, test } from "./fixtures";
const ROUTES = [
  "/",
  "/regimes",
  "/events",
  "/backtest",
  "/stress",
  "/snapshot",
  "/data",
];
test("redesigned pages reflow with 200 percent text and retain reachable navigation", async ({ page }, testInfo) => {
  for (const route of ROUTES) {
    await openRoute(page, route);
    await page.locator(".state-loading").waitFor({ state: "detached" });
    await page.addStyleTag({ content: "html{font-size:200% !important}" });
    const layout = await page.evaluate(() => {
      const main = document.querySelector("main")!.getBoundingClientRect();
      const nav = document.querySelector(".site-nav")!.getBoundingClientRect();
      return { overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        mainLeft: main.left, navRight: nav.right, navPosition: getComputedStyle(document.querySelector(".site-header")!).position };
    });
    expect(layout.overflow, route).toBeLessThanOrEqual(1);
    await expect(page.locator("main h1")).toBeVisible();
    await testInfo.attach(route === "/" ? "home-200-percent" : route.replaceAll("/", "-") + "-200-percent",
      { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
    await page.locator("style").last().evaluate(node => node.remove());
  }
});
