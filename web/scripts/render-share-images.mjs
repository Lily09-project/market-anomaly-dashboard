// Render the link-preview image (public/og-image.png, 1200×630) and the iOS home-screen
// icon (public/apple-touch-icon.png, 180×180) from the site's own design tokens and favicon.
//
// The preview image is deliberately title-only: it carries no prices, dates or results,
// so it never goes stale when the data snapshot is rebuilt.
//
//   cd web && node scripts/render-share-images.mjs
//
// Uses the Playwright Chromium that the e2e suite already installs. Text is set in the
// site's font stack, so render on a machine with a Traditional Chinese system font
// (Microsoft JhengHei, PingFang TC or Noto Sans TC).
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const root = new URL("../", import.meta.url);
const tokens = readFileSync(new URL("src/styles/tokens.css", root), "utf8");
const favicon = readFileSync(new URL("public/favicon.svg", root), "utf8");
// The home-screen icon must be opaque and square; iOS applies its own corner mask.
const touchIcon = favicon.replace(/ rx="[^"]*"/, "");

const shareHtml = `<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8"><style>
${tokens}
* { box-sizing: border-box; margin: 0; }
html, body { width: 1200px; height: 630px; overflow: hidden; }
body { background: var(--bg); color: var(--ink); font-family: var(--font-sans); position: relative; }
.frame { position: absolute; inset: 0; padding: 72px 80px; display: flex; flex-direction: column; }
.brand { display: flex; align-items: center; gap: 22px; }
.mark { width: 88px; height: 88px; }
.mark svg { width: 100%; height: 100%; display: block; }
.name { font-size: 34px; font-weight: 700; letter-spacing: 0.01em; color: var(--ink-soft); }
h1 { margin-top: 64px; font-size: 92px; line-height: 1.08; font-weight: 800; letter-spacing: -0.02em; }
h1 span { color: var(--accent); }
p { margin-top: 28px; font-size: 34px; line-height: 1.45; color: var(--ink-soft); max-width: 980px; }
.foot { margin-top: auto; display: flex; justify-content: space-between; align-items: flex-end; font-size: 24px; color: var(--muted); }
.states { position: absolute; left: 0; right: 0; bottom: 0; height: 12px; display: flex; }
.states i { flex: 1; }
</style></head><body>
<div class="frame">
  <div class="brand"><div class="mark">${favicon}</div><div class="name">Market Regime Lab</div></div>
  <h1>市場狀態<span>實驗室</span></h1>
  <p>臺股市場狀態、異常事件、誠實回測與壓力測試的互動研究網站</p>
  <div class="foot"><span>隱藏馬可夫模型 · 事件研究 · 過度擬合檢定 · 區塊 bootstrap</span><span>研究用途，非投資建議</span></div>
</div>
<div class="states" aria-hidden="true"><i style="background:var(--state-0)"></i><i style="background:var(--state-1)"></i><i style="background:var(--state-2)"></i></div>
</body></html>`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  await page.setContent(shareHtml, { waitUntil: "load" });
  await page.screenshot({ path: fileURLToPath(new URL("public/og-image.png", root)), type: "png" });

  await page.setViewportSize({ width: 180, height: 180 });
  await page.setContent(
    `<!doctype html><html><head><style>html,body{margin:0;width:180px;height:180px;overflow:hidden}svg{display:block;width:180px;height:180px}</style></head><body>${touchIcon}</body></html>`,
  );
  await page.screenshot({ path: fileURLToPath(new URL("public/apple-touch-icon.png", root)), type: "png" });
} finally {
  await browser.close();
}
console.log("wrote public/og-image.png and public/apple-touch-icon.png");
