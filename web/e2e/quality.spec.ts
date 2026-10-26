import { expect, expectAccessible, openRoute, test } from "./fixtures";

const ROUTES = [
  "/",
  "/regimes",
  "/events",
  "/backtest",
  "/stress",
  "/snapshot",
  "/data",
];
const FIXED_BACKGROUND = "#f4f4f7";
const LEGACY_THEME_KEY = "market-regime-lab-theme";

test.describe("Q4/Q5 navigation, keyboard and accessibility", () => {
  test("skip link, navigation and focus management work by keyboard", async ({ page }) => {
    await openRoute(page, "/");
    await page.keyboard.press("Tab");
    await expect(page.getByText("跳到主要內容")).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.locator("main")).toBeFocused();
    await expect(page.locator("main")).toHaveCSS("outline-style", "solid");
    await expect(page.locator("main")).toHaveCSS("outline-width", "3px");
    const nav = page.getByRole("navigation", { name: "主要頁面" });
    await nav.getByRole("link", { name: "誠實回測" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.locator("h1")).toHaveText("誠實回測實驗室");
    await expect(nav.getByRole("link", { name: "誠實回測" })).toHaveAttribute("aria-current", "page");
    await expect(page.locator("main")).toBeFocused();
    await expect(page).toHaveTitle(/誠實回測實驗室/);
  });

  test("navigation keeps the selected symbol", async ({ page }) => {
    await openRoute(page, "/?symbol=2330");
    await page.getByRole("navigation", { name: "主要頁面" }).getByRole("link", { name: "市場狀態" }).click();
    await expect(page).toHaveURL(/#\/regimes\?symbol=2330/);
    await expect(page.getByRole("radio", { name: /2330/ })).toBeChecked();
  });

  test("every page keeps one palette under both system color preferences", async ({ page }) => {
    await page.addInitScript((key) => {
      try {
        window.localStorage.setItem(key, "dark");
      } catch {
        // Storage restrictions must not change the fixed site palette.
      }
    }, LEGACY_THEME_KEY);

    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme });
      for (const route of ROUTES) {
        await openRoute(page, route);
        await page.locator(".state-loading").waitFor({ state: "detached" });
        await expect(page.getByLabel("介面主題")).toHaveCount(0);
        const appearance = await page.locator("html").evaluate((root) => ({
          dataTheme: root.getAttribute("data-theme"),
          colorScheme: getComputedStyle(root).colorScheme,
          background: getComputedStyle(root).getPropertyValue("--bg").trim(),
        }));
        expect(appearance).toEqual({
          dataTheme: null,
          colorScheme: "light",
          background: FIXED_BACKGROUND,
        });
        await expectAccessible(page);
      }
    }
  });



  test("unknown routes render a helpful page", async ({ page }) => {
    await page.goto("./#/nowhere");
    await expect(page.getByText("找不到這個頁面")).toBeVisible();
    await expectAccessible(page);
  });

  test("every chart offers an equivalent data table", async ({ page }) => {
    for (const route of ["/", "/regimes", "/events", "/backtest", "/stress"]) {
      await openRoute(page, route);
      if (route === "/stress") await expect(page.getByTestId("var95")).toBeVisible();
      const count = await page.locator("figure.chart-frame").count();
      expect(count, `charts on ${route}`).toBeGreaterThan(0);
      await expect(page.locator("figure.chart-frame details table")).toHaveCount(count);
    }
  });

  test("layout never scrolls horizontally", async ({ page }) => {
    for (const route of ROUTES) {
      await openRoute(page, route);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow, `horizontal overflow on ${route}`).toBeLessThanOrEqual(0);
    }
  });
});

test.describe("Q6 performance and Q8 security", () => {
  test("main content appears within 1.5 s and no third-party request is made", async ({ page }) => {
    const hosts = new Set<string>();
    page.on("request", (r) => hosts.add(new URL(r.url()).host));
    const start = Date.now();
    await page.goto("./");
    await expect(page.locator("main h1")).toBeVisible();
    expect(Date.now() - start).toBeLessThan(1500);
    await page.waitForLoadState("networkidle");
    expect([...hosts]).toEqual([new URL(page.url()).host]);
  });

  test("a strict Content-Security-Policy is declared and no inline script exists", async ({ page }) => {
    await page.goto("./");
    const csp = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute("content");
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).not.toContain("unsafe-eval");
    expect(await page.locator("script:not([src])").count()).toBe(0);
  });
});
