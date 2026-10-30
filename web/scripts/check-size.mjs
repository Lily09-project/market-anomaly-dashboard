// Enforce the performance budget from docs/ACCEPTANCE.md (Q6):
//   initial JavaScript ≤ 200 KB gzip, first-screen data ≤ 800 KB.
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const dist = fileURLToPath(new URL("../dist/", import.meta.url));
const html = readFileSync(join(dist, "index.html"), "utf8");
const scripts = [...html.matchAll(/<script[^>]+src="\.\/([^"]+)"/g)].map((m) => m[1]);
const preloads = [...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="\.\/([^"]+)"/g)].map((m) => m[1]);
const initialJs = [...scripts, ...preloads];
const jsGzip = initialJs.reduce((sum, file) => sum + gzipSync(readFileSync(join(dist, file))).length, 0);

// The home page loads the manifest, overview, regimes, backtest, events, provenance and TWSE files.
const firstScreenData = ["manifest.json", "overview.json", "regimes.json", "backtest.json", "events.json", "provenance.json", "twse.json"];
const dataBytes = firstScreenData.reduce((sum, file) => sum + statSync(join(dist, "data", file)).size, 0);

const JS_BUDGET = 200 * 1024;
const DATA_BUDGET = 800 * 1024;
console.log(`initial JS (gzip): ${(jsGzip / 1024).toFixed(1)} KB / ${JS_BUDGET / 1024} KB  [${initialJs.join(", ")}]`);
console.log(`first-screen data: ${(dataBytes / 1024).toFixed(1)} KB / ${DATA_BUDGET / 1024} KB`);
if (initialJs.length === 0) throw new Error("no entry script found in dist/index.html");
if (jsGzip > JS_BUDGET || dataBytes > DATA_BUDGET) {
  console.error("Performance budget exceeded.");
  process.exit(1);
}
