// Enforce the performance budget from docs/ACCEPTANCE.md (Q6):
//   initial JavaScript ≤ 200 KB gzip, first-screen data ≤ 800 KB gzip.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const html = readFileSync(join(dist, "index.html"), "utf8");
const scripts = [...html.matchAll(/<script[^>]+src="\.\/([^"]+)"/g)].map((m) => m[1]);
const preloads = [...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="\.\/([^"]+)"/g)].map((m) => m[1]);
const initialJs = [...scripts, ...preloads];
const jsGzip = initialJs.reduce((sum, file) => sum + gzipSync(readFileSync(join(dist, file))).length, 0);

// New exports include the compact backtest summary in the overview. Legacy
// exports still require the full backtest file on the homepage.
const firstScreenData = ["manifest.json", "overview.json", "regimes.json", "events.json", "provenance.json", "twse.json"];
const overview = JSON.parse(readFileSync(join(dist, "data", "overview.json"), "utf8"));
if (!overview.backtest_summary) firstScreenData.push("backtest.json");
const dataBytes = firstScreenData.reduce((sum, file) => sum + gzipSync(readFileSync(join(dist, "data", file))).length, 0);

const JS_BUDGET = 200 * 1024;
const DATA_BUDGET = 800 * 1024;
console.log(`initial JS (gzip): ${(jsGzip / 1024).toFixed(1)} KB / ${JS_BUDGET / 1024} KB  [${initialJs.join(", ")}]`);
console.log(`first-screen data (gzip): ${(dataBytes / 1024).toFixed(1)} KB / ${DATA_BUDGET / 1024} KB`);
if (initialJs.length === 0) throw new Error("no entry script found in dist/index.html");
if (jsGzip > JS_BUDGET || dataBytes > DATA_BUDGET) {
  console.error("Performance budget exceeded.");
  process.exit(1);
}
