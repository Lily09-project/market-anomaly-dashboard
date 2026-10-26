import { expect, openRoute, test } from "./fixtures";

for (const replacement of ["invalid-object", "oversized", "cleared"] as const) {
  test(`only the latest snapshot selection may publish a result: ${replacement}`, async ({ page }) => {
    await page.addInitScript(() => {
      const original = File.prototype.text;
      File.prototype.text = function () {
        if (this.name !== "slow.json") return original.call(this);
        return new Promise<string>((resolve) => {
          Object.defineProperty(window, "releaseSlowSnapshot", {
            configurable: true,
            value: () => resolve("{invalid json"),
          });
        });
      };
    });
    await openRoute(page, "/snapshot");
    const input = page.getByLabel("快照 A");
    const status = page.getByTestId("snapshot-a-status");
    await input.setInputFiles({ name: "slow.json", mimeType: "application/json", buffer: Buffer.from("{}") });
    await page.waitForFunction(() => typeof Reflect.get(window, "releaseSlowSnapshot") === "function");
    if (replacement === "invalid-object") {
      await input.setInputFiles({ name: "latest.json", mimeType: "application/json", buffer: Buffer.from("[]") });
      await expect(status).toContainText("內容不是 JSON 物件");
    } else if (replacement === "oversized") {
      await input.setInputFiles({ name: "latest.json", mimeType: "application/json", buffer: Buffer.alloc(64 * 1024 + 1, " ") });
      await expect(status).toContainText("KB 上限");
    } else {
      await input.setInputFiles([]);
      await expect(status).toBeEmpty();
    }
    // Release the older read after the newer selection was processed, then allow
    // its promise chain and React commit to run before checking the final state.
    await page.evaluate(async () => {
      Reflect.get(window, "releaseSlowSnapshot")();
      await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
    });
    if (replacement === "cleared") await expect(status).toBeEmpty();
    else await expect(status).toContainText(replacement === "oversized" ? "KB 上限" : "內容不是 JSON 物件");
    await expect(status).not.toContainText("不是有效的 JSON");
  });
}

test("a broken manifest shows the existing data error without an unhandled rejection", async ({ page }) => {
  await page.route("**/data/manifest.json", (route) => route.fulfill({
    status: 200, contentType: "application/json", body: "{invalid json",
  }));
  await openRoute(page, "/snapshot");
  await expect(page.getByRole("alert")).toContainText("無法顯示這個頁面");
  await expect(page.getByRole("button", { name: "建立並下載快照" })).toHaveCount(0);
  // The shared fixture requires zero page errors, console errors or failed HTTP requests.
});
