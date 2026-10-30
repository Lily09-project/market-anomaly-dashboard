import { mkdtemp, readFile, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, expectAccessible, fetchJson, openRoute, test } from "./fixtures";

interface Overview {
  dates: string[];
  symbols: { symbol: string; close: number[] }[];
}

test.describe("F1 標的總覽", () => {
  test("switching symbol and period updates the summary and the URL", async ({ page }) => {
    await openRoute(page, "/");
    const total = page.getByTestId("total-return");
    const before = await total.innerText();
    await page.getByRole("radio", { name: /2330/ }).check();
    await expect(page).toHaveURL(/symbol=2330/);
    await expect(total).not.toHaveText(before);
    await expect(page.getByRole("figure").first()).toContainText("2330");
    await page.getByRole("radio", { name: "近 1 年" }).check();
    await expect(page).toHaveURL(/period=1y/);
    await page.reload();
    await expect(page.getByRole("radio", { name: "近 1 年" })).toBeChecked();
    await expect(page.getByRole("radio", { name: /2330/ })).toBeChecked();
    await page.getByRole("radio", { name: /RANDOM/ }).check();
    await expect(page.getByTestId("control-notice")).toBeVisible();
    await expectAccessible(page);
  });

  test("the exchange snapshot panel is labelled as a preview and skips the control", async ({ page }) => {
    await openRoute(page, "/?symbol=2330");
    const panel = page.getByTestId("twse-panel");
    await expect(panel.getByTestId("twse-sample")).toBeVisible();
    await expect(panel.getByTestId("twse-cross-check")).toHaveText("與 FinMind 收盤一致");
    await expect(panel.getByRole("figure")).toContainText("加權指數");
    await page.getByRole("radio", { name: /RANDOM/ }).check();
    await expect(panel).toContainText("隨機漫步對照組");
    await expectAccessible(page);
  });
});

test.describe("F2 市場狀態", () => {
  test("shows three states, a valid transition matrix and the accuracy against the truth", async ({ page }) => {
    await openRoute(page, "/regimes?symbol=0050");
    await expect(page.getByTestId("state-card")).toHaveCount(3);
    const accuracy = Number((await page.getByTestId("accuracy").innerText()).replace("%", ""));
    expect(accuracy).toBeGreaterThanOrEqual(80);
    const rows = page.getByTestId("transition-table").locator("tbody tr");
    await expect(rows).toHaveCount(3);
    for (let i = 0; i < 3; i += 1) {
      const cells = (await rows.nth(i).locator("td").allInnerTexts()).map((t) => Number(t.replace("%", "")));
      expect(Math.abs(cells.reduce((a, b) => a + b, 0) - 100)).toBeLessThan(0.3);
    }
    await page.getByRole("radio", { name: /RANDOM/ }).check();
    await expect(page.getByTestId("no-regime-notice")).toBeVisible();
    await expectAccessible(page);
  });
});

test.describe("F3 異常事件研究", () => {
  test("pooled study is honest about significance and each event can be inspected", async ({ page }) => {
    await openRoute(page, "/events");
    await expect(page.getByTestId("negative-verdict")).toContainText("顯著的反彈");
    await expect(page.getByTestId("positive-verdict")).toContainText("涵蓋 0");
    await expect(page.getByTestId("control-events")).toHaveText("0");
    const links = page.getByTestId("events-table").locator("tbody a");
    expect(await links.count()).toBeGreaterThan(3);
    const second = await links.nth(1).innerText();
    await links.nth(1).click();
    await expect(page).toHaveURL(new RegExp(`date=${second}`));
    await expect(page.getByTestId("event-detail")).toContainText(second);
    await page.getByRole("radio", { name: /RANDOM/ }).check();
    await expect(page.getByText("這個標的沒有異常日")).toBeVisible();
  });
});

test.describe("F4 誠實回測", () => {
  test("heatmaps compare in- and out-of-sample results and report PBO and DSR", async ({ page }) => {
    await openRoute(page, "/backtest?symbol=0050");
    const pbo = Number((await page.getByTestId("pbo").innerText()).replace("%", ""));
    expect(pbo).toBeGreaterThanOrEqual(0);
    expect(pbo).toBeLessThanOrEqual(100);
    await expect(page.getByTestId("dsr")).toContainText("%");
    await expect(page.getByTestId("causal-check")).toContainText("通過");
    await expect(page.getByTestId("folds-table").locator("tbody tr")).not.toHaveCount(0);
    const cell = page.getByTestId("heat-is").getByRole("button", { name: /短均線 5、長均線 20：/ });
    await cell.click();
    await expect(page).toHaveURL(/cell=0/);
    await expect(cell).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("heat-oos").getByRole("button", { name: /短均線 5、長均線 20：/ })).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByTestId("selected-cell")).toContainText("5／20");
    await page.getByRole("radio", { name: /RANDOM/ }).check();
    await expect(page.getByTestId("pbo")).toBeVisible();
    await expectAccessible(page);
  });
});

test.describe("F5 壓力測試", () => {
  test("simulation is reproducible, parameters live in the URL and a run can be cancelled", async ({ page }) => {
    await openRoute(page, "/stress?symbol=0050");
    const var95 = page.getByTestId("var95");
    await expect(var95).toBeVisible();
    const first = await var95.innerText();
    const cvar = Number((await page.getByTestId("cvar95").innerText()).replace("%", ""));
    expect(cvar).toBeGreaterThanOrEqual(Number(first.replace("%", "")));

    await page.reload();
    await expect(var95).toHaveText(first); // same seed, same answer

    await page.getByLabel("模擬天數").selectOption("20");
    await expect(page).toHaveURL(/horizon=20/);
    await page.getByRole("button", { name: "以新設定重新模擬" }).click();
    await expect(page.getByRole("button", { name: "已是最新結果" })).toBeVisible();
    expect(await var95.innerText()).not.toBe(first);

    await page.getByLabel("模擬天數").selectOption("250");
    await page.getByLabel("路徑數").selectOption("20000");
    await page.getByRole("button", { name: "以新設定重新模擬" }).click();
    const cancel = page.getByRole("button", { name: "取消" });
    await expect(cancel).toBeVisible();
    await expect(page.getByRole("progressbar", { name: "模擬進度" })).toBeVisible();
    await cancel.click();
    await expect(page.getByRole("progressbar")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "以新設定重新模擬" })).toBeVisible();
  });
});

test.describe("F6 研究快照", () => {
  test("a downloaded snapshot re-imports with the same fingerprint and a tampered one is rejected", async ({ page }) => {
    await openRoute(page, "/snapshot");
    await page.getByLabel("標的").selectOption("0050");
    await page.getByLabel(/備註/).fill("E2E 測試");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "建立並下載快照" }).click();
    const file = await download;
    const path = (await file.path())!;
    const text = await readFile(path, "utf8");
    const snapshot = JSON.parse(text);
    await expect(page.getByTestId("created-snapshot")).toContainText(snapshot.fingerprint);

    await page.getByLabel("快照 A").setInputFiles(path);
    await expect(page.getByTestId("snapshot-a-status")).toContainText("指紋驗證通過");

    // An ASCII-only temp path: Chromium cannot read uploads from some non-ASCII paths.
    const tamperedPath = join(await mkdtemp(join(tmpdir(), "snapshot-")), "tampered.json");
    await writeFile(tamperedPath, JSON.stringify({ ...snapshot, results: { ...snapshot.results, pbo: 0.01 } }));
    await page.getByLabel("快照 B").setInputFiles(tamperedPath);
    await expect(page.getByTestId("snapshot-b-status")).toContainText("指紋不符");

    await page.getByLabel("快照 B").setInputFiles(path);
    await expect(page.getByTestId("diff-table")).toBeVisible();
    await expect(page.getByTestId("diff-table")).not.toContainText("不同");
    await expectAccessible(page);
  });
});

test.describe("F7 資料可信度", () => {
  test("every file passes in-browser SHA-256 verification against the manifest", async ({ page }) => {
    await openRoute(page, "/data");
    await expect(page.getByTestId("integrity-summary")).toHaveText("7/7");
    const manifest = await fetchJson<{ files: Record<string, string> }>(page, "manifest.json");
    const rows = page.getByTestId("integrity-table").locator("tbody tr");
    for (const [name, hash] of Object.entries(manifest.files)) {
      await expect(rows.filter({ hasText: name })).toContainText(hash);
      await expect(rows.filter({ hasText: name })).toContainText("相符");
    }
    const overview = await fetchJson<Overview>(page, "overview.json");
    expect(overview.symbols).toHaveLength(4);
    await expect(page.getByTestId("data-source")).toHaveText("合成資料");
  });
});

test("old stress results keep their own symbol, horizon, paths and baseline", async ({ page }) => {
  // Isolate the result/label contract from the maximum-size numerical benchmark.
  // Existing F5 and Python/TS parity tests still exercise the real worker.
  await page.addInitScript(() => {
    class DelayedWorker extends EventTarget {
      postMessage(request: { id: number; params: { horizon: number; paths: number } }) {
        const { id, params } = request;
        setTimeout(() => {
          const fan = Object.fromEntries(["0.05", "0.25", "0.5", "0.75", "0.95"].map(
            (q) => [q, Array.from({ length: params.horizon }, (_, i) => Number(q) * (i + 1) / 100)],
          ));
          this.dispatchEvent(new MessageEvent("message", { data: {
            id, type: "done", summary: {
              fan, terminal: Array.from({ length: params.paths }, (_, i) => i / params.paths / 10),
              var95: 0.1, cvar95: 0.12, var99: 0.15, cvar99: 0.17,
            },
          } }));
        }, 200);
      }
      terminate() { /* deliberately retain already queued messages */ }
    }
    Object.defineProperty(window, "Worker", { value: DelayedWorker });
  });
  await openRoute(page, "/stress?symbol=0050&horizon=20&paths=500");
  await expect(page.getByRole("button", { name: "已是最新結果" })).toBeVisible();
  const originalRisk = await page.getByTestId("risk-kpis").innerText();
  const originalResult = await page.locator(".split").innerText();
  await page.getByRole("radio", { name: /2330/ }).check();
  await page.getByLabel("模擬天數").selectOption("250");
  await page.getByLabel("路徑數").selectOption("20000");
  await page.getByRole("slider", { name: /區塊長度/ }).press("ArrowRight");
  await expect(page.getByText("設定已變更，下方仍是舊設定的結果。")).toBeVisible();
  await expect(page.getByTestId("risk-kpis")).toHaveText(originalRisk, { useInnerText: true });
  await expect(page.locator(".split")).toHaveText(originalResult, { useInnerText: true });
  await page.getByRole("button", { name: "以新設定重新模擬" }).click();
  await expect(page.getByRole("button", { name: "已是最新結果" })).toBeVisible();
  await expect(page.getByRole("figure", { name: "2330 未來 250 個交易日的報酬扇形圖" })).toBeVisible();
  await expect(page.getByTestId("fan-table").locator("tbody tr").last()).toContainText("250");
  await expect(page.getByRole("img", { name: /^期末報酬分布：20,000 條路徑/ })).toBeVisible();
});
