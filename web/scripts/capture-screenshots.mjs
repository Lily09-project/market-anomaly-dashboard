// Retake the README screenshots from the live GitHub Pages site.
//
// Usage (from web/):  npm run screenshots [-- <site-url>]
// The shot list and default site URL live in ../docs/screenshots/shots.json.
// Images are written next to that file, so the README always shows what is
// actually deployed. Run it after a visual change has been merged and deployed.
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "..", "..", "docs", "screenshots");
const config = JSON.parse(readFileSync(path.join(outDir, "shots.json"), "utf8"));
const base = process.argv[2] ?? config.site;

const browser = await chromium.launch();
try {
  for (const shot of config.shots) {
    const context = await browser.newContext({
      viewport: shot.viewport ?? { width: 1440, height: 1000 },
      deviceScaleFactor: 1,
      isMobile: shot.mobile ?? false,
      hasTouch: shot.mobile ?? false,
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    let route = shot.route;
    if (shot.firstLinkFrom) {
      await page.goto(`${base}#${shot.firstLinkFrom.route}`);
      await page.locator(".state-loading").waitFor({ state: "detached" });
      const href = await page.locator(shot.firstLinkFrom.selector).first().getAttribute("href");
      route = href.replace(/^#/, "");
    }
    await page.goto(`${base}#${route}`);
    await page.locator("main h1").first().waitFor();
    await page.locator(".state-loading").waitFor({ state: "detached" });
    for (const click of shot.clicks ?? []) {
      await page.locator(click).first().click();
    }
    if (shot.waitFor) await page.locator(shot.waitFor).first().waitFor({ timeout: 60000 });
    // Park the pointer and drop focus so no hover or focus ring ends up in the image.
    await page.mouse.move(0, 0);
    await page.evaluate(() => document.activeElement instanceof HTMLElement && document.activeElement.blur());
    await page.waitForTimeout(600);
    const out = path.join(outDir, shot.file);
    if (shot.element) {
      await page.locator(shot.element).first().screenshot({ path: out });
    } else {
      await page.screenshot({ path: out, fullPage: shot.fullPage ?? false });
    }
    console.log(`${shot.file} <- ${route}`);
    await context.close();
  }
} finally {
  await browser.close();
}
