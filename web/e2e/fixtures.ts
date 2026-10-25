import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type Page } from "@playwright/test";

/**
 * Every test fails if the page logs a console error, throws, or a request
 * fails — the acceptance criteria require zero of each.
 */
export const test = base.extend<{ watch: { errors: string[] } }>({
  watch: [
    async ({ page }, use) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
      page.on("console", (m) => {
        if (m.type() === "error") errors.push(`console: ${m.text()}`);
      });
      page.on("requestfailed", (r) => {
        // Downloads are delivered as blob: URLs and report as "aborted" by design.
        if (!r.url().startsWith("blob:")) errors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`);
      });
      page.on("response", (r) => {
        if (r.status() >= 400) errors.push(`http ${r.status()}: ${r.url()}`);
      });
      await use({ errors });
      expect(errors, "console errors, page errors or failed requests").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

export async function openRoute(page: Page, hash: string) {
  await page.goto(`./#${hash}`);
  await expect(page.locator("main h1").first()).toBeVisible();
}

export async function expectAccessible(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
  expect(
    serious.map((v) => `${v.id}: ${v.help} → ${v.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(" | ")}`),
    "axe serious/critical violations",
  ).toEqual([]);
}

export async function fetchJson<T>(page: Page, name: string): Promise<T> {
  const response = await page.request.get(`./data/${name}`);
  expect(response.ok()).toBe(true);
  return (await response.json()) as T;
}
