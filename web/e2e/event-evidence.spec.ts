import { createHash } from "node:crypto";
import { expect, fetchJson, openRoute, test } from "./fixtures";
import type { Events, Manifest, Regimes } from "../src/lib/types";

for (const noEvents of [false, true]) {
  test(`event verdicts distinguish real data and missing evidence (empty=${noEvents})`, async ({ page }) => {
    const events = await fetchJson<Events>(page, "events.json");
    const manifest = await fetchJson<Manifest>(page, "manifest.json");
    events.validation = null;
    // A valid real-data response can have no significant positive effect.
    events.study.positive.post_low = events.study.positive.post_offsets.map(() => -0.01);
    events.study.positive.post_high = events.study.positive.post_offsets.map(() => 0.01);
    if (noEvents) {
      for (const study of [events.study.positive, events.study.negative]) {
        study.n = 0;
        for (const field of ["car", "low", "high", "post_car", "post_low", "post_high"] as const) {
          study[field] = study[field].map(() => null);
        }
      }
    }
    const body = JSON.stringify(events);
    manifest.files["events.json"] = createHash("sha256").update(body).digest("hex");
    await page.route("**/data/events.json", route => route.fulfill({ contentType: "application/json", body }));
    await page.route("**/data/manifest.json", route => route.fulfill({ json: manifest }));
    await openRoute(page, "/events");
    const verdicts = page.getByTestId("positive-verdict").or(page.getByTestId("negative-verdict"));
    await expect(verdicts).toHaveCount(2);
    for (const verdict of await verdicts.all()) await expect(verdict).not.toContainText("合成資料");
    if (noEvents) {
      for (const verdict of await verdicts.all()) {
        await expect(verdict).toContainText("沒有足夠事件");
        await expect(verdict).not.toContainText("區間涵蓋 0");
      }
    } else {
      await expect(page.getByTestId("positive-verdict")).toContainText("95% 區間涵蓋 0");
    }
  });
}

for (const states of [1, 2]) {
  test(`real-data BIC interpretation does not invent a known truth (states=${states})`, async ({ page }) => {
    const regimes = await fetchJson<Regimes>(page, "regimes.json");
    const manifest = await fetchJson<Manifest>(page, "manifest.json");
    const regime = regimes.symbols["0050"]!;
    regime.bic_choice = states;
    regime.accuracy = null;
    regime.truth_segments = null;
    regime.confusion = null;
    const body = JSON.stringify(regimes);
    manifest.files["regimes.json"] = createHash("sha256").update(body).digest("hex");
    await page.route("**/data/regimes.json", route => route.fulfill({ contentType: "application/json", body }));
    await page.route("**/data/manifest.json", route => route.fulfill({ json: manifest }));
    await openRoute(page, "/regimes?symbol=0050");
    await expect(page.locator("main")).not.toContainText("對照組正確地選了");
    await expect(page.locator("main")).not.toContainText("真實資料是 3 個狀態");
    await expect(page.locator("main")).toContainText("回顧性");
  });
}
