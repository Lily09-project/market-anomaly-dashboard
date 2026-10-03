"""Real browser acceptance for the static release, including project-path hosting."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def report_hash(report: dict, page) -> str:
    canonical = page.evaluate("(report) => JSON.stringify(Object.fromEntries(Object.entries(report).filter(([key]) => key !== 'sha256')))", report)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def downloaded_json(page, selector: str) -> dict:
    with page.expect_download() as event:
        page.locator(selector).click()
    return json.loads(Path(event.value.path()).read_text(encoding="utf-8-sig"))


def layout_check(page):
    problems = page.evaluate("""() => {
      const issues = [];
      if (document.documentElement.scrollWidth > innerWidth + 1) issues.push("horizontal overflow");
      for (const node of document.querySelectorAll("input,select,button,nav a")) {
        if (!node.checkVisibility()) continue;
        const r = node.getBoundingClientRect();
        if (r.width < 24 || r.height < 24) issues.push("small target: " + node.id);
        if (r.left < -1 || r.right > innerWidth + 1) issues.push("control overflow: " + node.id);
      }
      return issues;
    }""")
    assert not problems, problems


def keyboard_check(page):
    page.locator("#search").focus()
    for _ in range(16):
        page.keyboard.press("Tab")
        result = page.evaluate("""() => {
          const node = document.activeElement;
          if (node === document.body) return null;
          const r = node.getBoundingClientRect(), style = getComputedStyle(node);
          const x = Math.max(1, Math.min(innerWidth-1, r.left+r.width/2));
          const y = Math.max(1, Math.min(innerHeight-1, r.top+r.height/2));
          const hit = document.elementFromPoint(x,y);
          return {tag:node.tagName, id:node.id, type:node.type, focusVisible:node.matches(":focus-visible"), visible:r.width>0 && r.height>0,
            outline:style.outlineStyle !== "none" && parseFloat(style.outlineWidth)>=2,
            occluded:!(hit && (node.contains(hit) || hit.contains(node)))};
        }""")
        if result:
            assert result["visible"] and result["outline"] and not result["occluded"], result


def contrast_check(page):
    pairs = page.evaluate("""() => {
      const style = getComputedStyle(document.documentElement);
      return [["--text","--surface"],["--muted","--surface"],["--accent","--bg"],["--on-accent","--accent"]]
        .map(pair=>pair.map(key=>style.getPropertyValue(key).trim()));
    }""")
    def luminance(color):
        assert color.startswith("#") and len(color) in (4, 7), color
        if len(color) == 4:
            color = "#" + "".join(char * 2 for char in color[1:])
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
        return sum(a * b for a, b in zip(linear, (.2126, .7152, .0722)))
    for foreground, background in pairs:
        a, b = sorted((luminance(foreground), luminance(background)))
        assert (b + .05) / (a + .05) >= 4.5, (foreground, background)


def functional_check(page, url, bundle):
    page.goto(url)
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    first = bundle["datasets"][0]
    group = str(first["rows"][0][first["group"]])
    page.locator("#group").select_option(group)
    report = downloaded_json(page, "#json")
    assert report["project"] == bundle["project"] and report["dataset"] == first["id"]
    assert report["rows"] and all(str(row[first["group"]]) == group for row in report["rows"])
    assert report["sha256"] == report_hash(report, page)
    with page.expect_download() as event:
        page.locator("#csv").click()
    rows = list(csv.DictReader(io.StringIO(Path(event.value.path()).read_text(encoding="utf-8-sig"))))
    assert len(rows) == len(report["rows"])
    assert all(row[first["group"]] == group for row in rows)
    if first["date"]:
        dates = sorted(row[first["date"]][:10] for row in report["rows"])
        page.locator("#start").fill(dates[0]); page.locator("#start").press("Tab")
        page.locator("#end").fill(dates[0]); page.locator("#end").press("Tab")
        bounded = downloaded_json(page, "#json")
        assert bounded["rows"] and all(row[first["date"]][:10] == dates[0] for row in bounded["rows"])
        page.locator("#start").fill(dates[-1]); page.locator("#start").press("Tab")
        page.locator("#end").fill("2000-01-01"); page.locator("#end").press("Tab")
        assert page.locator("#filter-error").is_visible()
        assert page.locator("#json").is_disabled()
    page.locator("#reset").click()
    page.locator("#search").fill("NO_MATCH_7f9f123456")
    assert page.locator("#json").is_disabled() and page.locator("#csv").is_disabled()
    page.locator("#reset").click()
    picks = page.locator('#table input[type="checkbox"]')
    picks.nth(0).check(); picks.nth(1).check(); picks.nth(2).check()
    assert picks.nth(3).is_disabled()
    selected = downloaded_json(page, "#selection-download")
    assert len(selected["rows"]) == 3 and selected["sha256"] == report_hash(selected, page)
    shared = page.url
    page.reload()
    assert page.url == shared
    page.locator("#selection-status").filter(has_text="3 / 3").wait_for()
    page.locator("#clear-selection").click()
    assert page.locator("#selection-download").is_disabled()
    assert page.locator('#table input[type="checkbox"]:checked').count() == 0
    page.locator("#table button").first.click()
    assert page.locator("#detail-panel").is_visible() and "detail=" in page.url
    page.reload(); page.locator("#detail-panel").wait_for()
    page.locator("#close-detail").click()
    assert not page.locator("#detail-panel").is_visible()
    if bundle["kind"] == "cpbl":
        page.locator('#views a[href="?view=batters"]').click()
        page.locator("#minimum").fill("100"); page.locator("#minimum").press("Tab")
        players = downloaded_json(page, "#json")
        assert all(row["pa"] >= 100 and len(row["player_id"]) == 10 for row in players["rows"])
    if bundle["kind"] == "market":
        page.locator('#views a[href="?view=overview"]').click()
        original = downloaded_json(page, "#json")
        good = page.evaluate("(report) => JSON.stringify(report)", original).encode("utf-8")
        payload = {"name": "snapshot.json", "mimeType": "application/json", "buffer": good}
        page.locator("#snapshot-a").set_input_files(payload)
        page.locator("#snapshot-b").set_input_files(payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        compared = downloaded_json(page, "#snapshot-download")
        assert compared["added"] == compared["removed"] == compared["changed"] == []
        tampered = {**original, "project": "tampered"}
        page.locator("#snapshot-b").set_input_files({"name": "tampered.json", "mimeType": "application/json",
                                                   "buffer": page.evaluate("(report) => JSON.stringify(report)", tampered).encode("utf-8")})
        page.locator("#snapshot-status").filter(has_text="不是此網站").wait_for()
        assert page.locator("#snapshot-download").is_disabled()
        broken_rows = json.loads(good)
        broken_rows["rows"][0]["close"] += 1
        page.locator("#snapshot-b").set_input_files({"name": "tampered.json", "mimeType": "application/json",
                                                   "buffer": page.evaluate("(report) => JSON.stringify(report)", broken_rows).encode("utf-8")})
        page.locator("#snapshot-status").filter(has_text="SHA-256 不一致").wait_for()
        assert page.locator("#snapshot-download").is_disabled()
        duplicate = good.decode("utf-8").replace('"project":', '"project":"duplicated","project":', 1)
        page.locator("#snapshot-b").set_input_files({"name": "duplicate.json", "mimeType": "application/json", "buffer": duplicate.encode("utf-8")})
        page.locator("#snapshot-status").filter(has_text="重複欄位").wait_for()
        assert page.locator("#snapshot-download").is_disabled()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    args = parser.parse_args()
    bundle = json.loads((ROOT / "pages-dist/data.json").read_text(encoding="utf-8"))
    evidence = ROOT / "reports/pages-qa"
    evidence.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as engine:
        browser = engine.chromium.launch()
        for theme in ("light", "dark"):
            for width in (320, 390, 768, 1024, 1440):
                for scale in (1, 2):
                    context = browser.new_context(viewport={"width": width, "height": 1000}, color_scheme=theme,
                                                  reduced_motion="reduce", accept_downloads=True)
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
                    page.goto(args.url)
                    page.locator("#status").filter(has_text="筆符合條件").wait_for()
                    assert page.locator("html").get_attribute("data-theme") == theme
                    page.evaluate("(scale) => document.documentElement.style.fontSize = (16*scale)+'px'", scale)
                    contrast_check(page)
                    for view in bundle["datasets"]:
                        page.locator('#views a[href="?view=' + view["id"] + '"]').click()
                        assert page.locator("#status").inner_text().startswith(view["label"])
                        layout_check(page); keyboard_check(page)
                        if width in (320, 1440):
                            page.screenshot(path=str(evidence / f"{theme}-{width}-{scale}-{view['id']}.png"), full_page=True)
                    assert not errors, errors
                    context.close()
            context = browser.new_context(viewport={"width": 390, "height": 1000}, color_scheme=theme, accept_downloads=True)
            page = context.new_page()
            functional_check(page, args.url, bundle)
            context.close()
        context = browser.new_context()
        page = context.new_page()
        page.route("**/data.json", lambda route: route.fulfill(body='{"schema_version":"tampered"}', content_type="application/json"))
        page.goto(args.url)
        page.locator("#fatal").wait_for()
        assert page.locator("#json").is_disabled() and page.locator("#table tbody tr").count() == 0
        context.close()
        browser.close()
    print("PASS: 2 themes x 5 viewports x 2 text scales x every page; keyboard, contrast, filters, real downloads, comparisons, deep links, integrity failure")


if __name__ == "__main__":
    main()
