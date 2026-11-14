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
      const offenders = Array.from(document.querySelectorAll("main *, .site-header *")).filter(el => {
        const rect = el.getBoundingClientRect();
        return rect.right > document.documentElement.clientWidth + 1 && !el.parentElement?.closest(".table-scroll, .site-nav, .symbol-rail");
      }).slice(0,8).map(el => ({ tag: el.tagName, cls: el.className, text: el.textContent?.slice(0,50) }));
      return { offenders, overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        mainLeft: main.left, navRight: nav.right, navPosition: getComputedStyle(document.querySelector(".site-header")!).position };
    });
    expect(layout.overflow, route + JSON.stringify(layout.offenders)).toBeLessThanOrEqual(1);
    await expect(page.locator("main h1")).toBeVisible();
    await testInfo.attach(route === "/" ? "home-200-percent" : route.replaceAll("/", "-") + "-200-percent",
      { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
    await page.locator("style").last().evaluate(node => node.remove());
  }
});

test("the selected symbol chip is scrolled into view inside the toolbar rail", async ({ page }) => {
  // 1024px is the narrowest sticky toolbar, where the rail scrolls; phones use the same rail.
  for (const width of [1024, 1180, 390]) {
    await page.setViewportSize({ width, height: 800 });
    const symbols = await (await page.request.get("./data/overview.json")).json() as { symbols: { symbol: string }[] };
    for (const { symbol } of [symbols.symbols[0]!, symbols.symbols.at(-1)!]) for (const path of ["/", "/regimes"]) {
      await openRoute(page, `${path}?symbol=${symbol}`);
      await page.locator(".analysis").waitFor();
      const chip = page.locator(".symbol-rail input:checked + span");
      await expect(chip).toContainText(symbol);
      const inside = await page.evaluate(() => {
        const rail = document.querySelector(".symbol-rail")!.getBoundingClientRect();
        const chip = document.querySelector(".symbol-rail input:checked")!.parentElement!.getBoundingClientRect();
        return chip.left >= rail.left - 1 && chip.right <= rail.right + 1;
      });
      expect(inside, `${symbol} on ${path} at ${width}px`).toBe(true);
    }
  }
});

test("the not-found page has its own heading and title", async ({ page }) => {
  await page.goto("./#/nowhere");
  await expect(page.getByRole("heading", { level: 1, name: "找不到這個頁面" })).toBeVisible();
  await expect(page).toHaveTitle(/找不到這個頁面/);
});

test("a shared stress link with an unlisted value shows that value in its control", async ({ page }) => {
  await openRoute(page, "/stress?horizon=33&paths=777");
  await expect(page.getByTestId("var95")).toBeVisible();
  await expect(page.getByLabel("模擬天數")).toHaveValue("33");
  await expect(page.getByLabel("路徑數")).toHaveValue("777");
  await expect(page.getByTestId("stress-charts").locator("figcaption").first()).toContainText("33 個交易日");
});

test("picking an event date on a phone brings the detail into view", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openRoute(page, "/events");
  const links = page.getByTestId("events-table").locator("tbody a");
  test.skip((await links.count()) < 2, "needs two events");
  const date = (await links.nth(1).textContent())!;
  await links.nth(1).click();
  await expect(page.locator(".event-detail-title")).toContainText(date);
  const top = await page.getByTestId("event-detail").evaluate((el) => el.getBoundingClientRect().top);
  expect(top).toBeGreaterThanOrEqual(-1);
});

test("a figure that rounds to zero carries no minus sign", async ({ page }) => {
  await openRoute(page, "/backtest");
  await expect(page.getByTestId("heat-is")).toBeVisible();
  await expect(page.locator("main")).not.toContainText(/-0\.0+(?!\d)/);
});
