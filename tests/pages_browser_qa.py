"""Real browser acceptance for the static release, including project-path hosting."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

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
        if (r.width < 24 || r.height < 24) issues.push("small target: " + node.tagName + " " + node.id + " " + r.width + "x" + r.height);
        if (r.left < -1 || r.right > innerWidth + 1) issues.push("control overflow: " + node.tagName + " " + node.id + " " + r.left + ".." + r.right);
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
      return [["--text","--surface"],["--muted","--surface"],["--accent","--bg"],["--on-accent","--accent"],["--error","--surface"],["--text","--tint"],["--muted","--raised"]]
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
        page.locator("#advanced-filters").evaluate("(node) => node.open = true")
        dates = sorted(row[first["date"]][:10] for row in report["rows"])
        page.locator("#start").fill(dates[0]); page.locator("#start").press("Tab")
        page.locator("#end").fill(dates[0]); page.locator("#end").press("Tab")
        bounded = downloaded_json(page, "#json")
        assert bounded["rows"] and all(row[first["date"]][:10] == dates[0] for row in bounded["rows"])
        page.locator("#start").fill(dates[-1]); page.locator("#start").press("Tab")
        page.locator("#end").fill("2000-01-01"); page.locator("#end").press("Tab")
        assert page.locator("#filter-error").is_visible()
        assert page.locator("#theme").is_enabled()
        page.locator("#theme").click()
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
        page.locator("#advanced-filters").evaluate("(node) => node.open = true")
        page.locator("#minimum").fill("100"); page.locator("#minimum").press("Tab")
        players = downloaded_json(page, "#json")
        assert all(row["pa"] >= 100 and len(row["player_id"]) == 10 for row in players["rows"])
        for row in (item for data in bundle["datasets"] for item in data["rows"] if "player_id" in item):
            if not row["player_id"].isdigit():
                page.locator('#views a[href="?view=roster"]').click()
                page.locator("#search").fill(row["player_id"])
                page.locator("#table button").first.click()
                assert page.locator('#detail a[href*="acnt="]').count() == 0
                break
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



def ux_regression_check(page, url, bundle):
    """Behavioral regressions which geometry-only checks cannot catch."""
    page.goto(url)
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    first = bundle["datasets"][0]
    # Table sorting must not silently change the chart's selected series or colors.
    def chart_signature():
        return page.locator("#legend span").evaluate_all(
            "(nodes) => nodes.map(node => [node.textContent, node.className, getComputedStyle(node, '::before').borderTopColor])")
    signature = chart_signature()
    for field in first["fields"]:
        page.locator("#sort").select_option(field["key"])
        assert chart_signature() == signature, field
        page.locator("#direction").click()
        assert chart_signature() == signature, field
        assert page.locator("th[aria-sort]").count() == 1
    page.locator("#reset").click()
    # Keyboard route changes must focus a persistent, visible content target.
    if len(bundle["datasets"]) > 1:
        target = bundle["datasets"][1]
        page.locator('#views a[href="?view=' + target["id"] + '"]').focus()
        page.keyboard.press("Enter")
        assert page.locator("#main").evaluate("(node) => node === document.activeElement")
    page.locator('#views a[href="?view=' + first["id"] + '"]').click()
    page.locator('#table input[type="checkbox"]').first.check()
    page.locator("#comparison button").first.click()
    assert page.locator("#compare-title").evaluate("(node) => node === document.activeElement")
    assert page.locator("#clear-selection").is_disabled()
    # Preserve complete data in details while compact cards omit secondary fields.
    page.locator("#table button").first.click()
    assert page.locator("#detail dt").count() == len(first["fields"])
    page.locator("#close-detail").click()
    assert page.locator("#table button").first.evaluate("(node) => node === document.activeElement")
    # Resize after desktop pagination, without another filter/change event.
    paginated = next(view for view in bundle["datasets"] if len(view["rows"]) > 20)
    page.set_viewport_size({"width": 1440, "height": 900})
    page.locator('#views a[href="?view=' + paginated["id"] + '"]').click()
    page.locator("#table tbody tr").nth(19).wait_for()
    page.locator("#next").click()
    assert page.locator("#table-title").evaluate("(node) => node === document.activeElement")
    anchor = page.locator("#table tbody tr").first.get_attribute("data-row-id")
    page.locator('#table input[type="checkbox"]').first.check()
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("#table tbody tr")).to_have_count(8)
    assert anchor in page.locator("#table tbody tr").evaluate_all("(nodes) => nodes.map(node => node.getAttribute('data-row-id'))")
    assert page.locator("#selection-status").inner_text().startswith("已選取 1")
    page.locator("#next").click()
    assert page.locator("#table-title").evaluate("(node) => node === document.activeElement")
    assert 0 <= page.locator("#table-title").bounding_box()["y"] < 844
    shared = page.url
    page.reload()
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    assert page.url == shared
    assert not page.locator("#page-count").inner_text().startswith("1 /")
    assert page.locator("#selection-status").inner_text().startswith("已選取 1")
    page.locator("#clear-selection").click()
    assert page.locator("#compare-title").evaluate("(node) => node === document.activeElement")
    # A real calendar boundary must survive the viewer's timezone.
    if bundle["kind"] == "aqi":
        page.locator('#views a[href="?view=overview"]').click()
        day = min(row[first["date"]][:10] for row in first["rows"])
        page.locator("#advanced-filters").evaluate("(node) => node.open = true")
        for control in ("start", "end"):
            page.locator("#" + control).fill(day)
            page.locator("#" + control).press("Tab")
        assert page.locator("#chart .axis span").first.inner_text() == day
        assert page.locator("#chart .axis span").last.inner_text() == day
        page.locator("#advanced-summary").filter(has_text="已套用").wait_for()
    elif bundle["kind"] == "market":
        page.locator('#views a[href="?view=overview"]').click()
        assert "%" in page.locator('td[data-field="daily_return"]').first.inner_text()
    else:
        page.locator('#views a[href="?view=teams"]').click()
        assert "," not in page.locator('td[data-field="season"]').first.inner_text()
    page.set_viewport_size({"width": 844, "height": 390})
    layout_check(page)


def visual_polish_check(page, url, bundle):
    page.goto(url)
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    page.set_viewport_size({"width": 390, "height": 844})
    for view in bundle["datasets"]:
        page.locator('#views a[href="?view=' + view["id"] + '"]').click()
        assert page.locator("#main").evaluate("(node) => node === document.activeElement")
        assert page.locator("#views").bounding_box()["y"] >= -1
        layout_check(page)
        contrast_check(page)
        fields = {field["key"] for field in view["fields"]}
        required = ({"pa", "innings_pitched", "player_type", "season", "is_anomaly", "model_anomaly", "actual_next_hour_aqi"} & fields)
        if page.locator("#table tbody tr").count():
            for key in required:
                assert page.locator('td[data-field="' + key + '"]').first.is_visible(), (view["id"], key)
            check = page.locator('#table input[type="checkbox"]').first
            check.check()
            assert check.evaluate("(node) => node === document.activeElement")
            page.locator("#compare-jump").click()
            assert page.locator("#compare-title").evaluate("(node) => node === document.activeElement")
            assert 0 <= page.locator("#compare-title").bounding_box()["y"] < 844
            page.locator("#clear-selection").click()
        if view["date"]:
            assert page.locator("#chart .y-scale span").count() == 3
            assert "NaN" not in page.locator("#chart svg").evaluate("(node) => node.outerHTML")
        if view["date"] or view.get("minimum"):
            page.locator("#advanced-filters").evaluate("(node) => node.open = true")
            if view["date"]:
                day = min(row[view["date"]][:10] for row in view["rows"])
                page.locator("#start").fill(day)
                page.locator("#start").press("Tab")
            else:
                page.locator("#minimum").fill(str(view["minimum"]["value"] + 1))
                page.locator("#minimum").press("Tab")
            page.locator("#advanced-filters").evaluate("(node) => node.open = false")
            page.locator("#direction").click()
            assert not page.locator("#advanced-filters").evaluate("(node) => node.open")
            page.locator("#reset").click()
        if "is_anomaly" in fields or "model_anomaly" in fields:
            page.locator("#only-anomaly").check()
            report = downloaded_json(page, "#json")
            key = "is_anomaly" if "is_anomaly" in fields else "model_anomaly"
            assert report["rows"] and all(row[key] == 1 for row in report["rows"])
            assert report["filters"]["only_anomaly"] is True
            assert report["sha256"] == report_hash(report, page)
            page.reload()
            page.locator("#status").filter(has_text="筆符合條件").wait_for()
            assert page.locator("#only-anomaly").is_checked()
            page.locator("#reset").click()
        if bundle["kind"] == "market" and view["id"] == "anomaly":
            assert page.locator("#chart polyline").count() == 0
            assert page.locator("#chart circle").count() > 0
        if bundle["kind"] == "aqi" and view["id"] == "anomaly":
            assert page.locator("#chart .anomaly-point").count() > 0
            assert "三角形" in page.locator("#legend").inner_text()


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
                        assert page.locator("#main").evaluate("(node) => node === document.activeElement")
                        try:
                            layout_check(page); keyboard_check(page)
                            if width == 320 and scale == 2:
                                assert page.locator("#metrics").evaluate("(node) => getComputedStyle(node).gridTemplateColumns.split(' ').length") == 1
                                if page.locator("#table tbody td").count():
                                    assert page.locator("#table tbody td").first.evaluate("(node) => getComputedStyle(node).display") == "flex"
                            if width == 1440 and scale == 1 and bundle["kind"] == "market" and view["id"] != "metrics":
                                for key in ("date", "volume"):
                                    cell = page.locator('td[data-field="' + key + '"]').first
                                    assert cell.evaluate("(node) => { const range = document.createRange(); range.selectNodeContents(node); return range.getClientRects().length === 1; }"), key
                        except AssertionError:
                            page.screenshot(path=str(evidence / f"failure-{theme}-{width}-{scale}-{view['id']}.png"), full_page=True)
                            raise
                        if width in (320, 1440):
                            page.screenshot(path=str(evidence / f"{theme}-{width}-{scale}-{view['id']}.png"), full_page=True)
                    assert not errors, errors
                    context.close()
            context = browser.new_context(viewport={"width": 390, "height": 1000}, color_scheme=theme, accept_downloads=True)
            page = context.new_page()
            functional_check(page, args.url, bundle)
            ux_regression_check(page, args.url, bundle)
            visual_polish_check(page, args.url, bundle)
            context.close()
        for zone in ("UTC", "Asia/Taipei", "America/Los_Angeles"):
            context = browser.new_context(viewport={"width": 390, "height": 844}, timezone_id=zone, reduced_motion="reduce")
            page = context.new_page()
            ux_regression_check(page, args.url, bundle)
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
