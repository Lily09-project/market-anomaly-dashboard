"""Real browser acceptance for the static release, including project-path hosting."""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
from datetime import date, timedelta
from urllib.parse import quote
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
    page.locator("a.skip").focus()
    visited = []
    reached_boundary = False
    for _ in range(80):
        page.keyboard.press("Tab")
        result = page.evaluate("""() => {
          const node = document.activeElement;
          if (node === document.body) return null;
          const r = node.getBoundingClientRect(), style = getComputedStyle(node);
          const x = Math.max(1, Math.min(innerWidth-1, r.left+r.width/2));
          const y = Math.max(1, Math.min(innerHeight-1, r.top+r.height/2));
          const hit = document.elementFromPoint(x,y);
          return {tag:node.tagName, id:node.id, type:node.type, isSkip:node.matches("a.skip"),
            visible:r.width>0 && r.height>0, outline:style.outlineStyle !== "none" && parseFloat(style.outlineWidth)>=2,
            occluded:!(hit && (node.contains(hit) || hit.contains(node)))};
        }""")
        # Walk real sequential focus order from the skip link, validating every target.
        if result is None:
            reached_boundary = True
            break
        assert result["visible"] and result["outline"] and not result["occluded"], result
        visited.append(result["id"])
        if result["isSkip"]:
            reached_boundary = True
            break
    assert reached_boundary, "Keyboard traversal did not reach the end of the focus sequence."
    assert len(visited) >= 20, (len(visited), visited)
    assert {"theme", "search", "group", "reset"}.issubset(set(visited)), visited


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
        for control in ("start", "end"):
            field = page.locator("#" + control)
            assert field.get_attribute("aria-describedby") == "filter-error"
            assert field.get_attribute("aria-invalid") == "true"
        assert page.locator("#theme").is_enabled()
        page.locator("#theme").click()
        assert page.locator("#json").is_disabled()
    page.locator("#reset").click()
    for control in ("start", "end"):
        assert page.locator("#" + control).get_attribute("aria-invalid") is None
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
        view = next(item for item in bundle["datasets"] if item["id"] == original["dataset"])
        original_rows = copy.deepcopy(original["rows"])
        assert len(original_rows) >= 2, "Market overview needs at least two rows for a meaningful snapshot diff."
        diff_report = copy.deepcopy(original)
        rows = copy.deepcopy(original_rows[:-1])
        numeric_field = next((field for field in view["fields"] if field["key"] not in view["identity"] and
                              any(isinstance(row.get(field["key"]), (int, float)) and not isinstance(row.get(field["key"]), bool) for row in rows)), None)
        assert numeric_field, "Market snapshot fixture needs a non-identity numeric field."
        changed_index = next(index for index, row in enumerate(rows)
                             if isinstance(row.get(numeric_field["key"]), (int, float)) and not isinstance(row.get(numeric_field["key"]), bool))
        changed_before = copy.deepcopy(rows[changed_index])
        rows[changed_index][numeric_field["key"]] += 1
        changed_after = copy.deepcopy(rows[changed_index])
        added = copy.deepcopy(original_rows[-1])
        identity_key = next((key for key in view["identity"] if next(field for field in view["fields"] if field["key"] == key)["kind"] != "date"), view["identity"][0])
        identity_value = added[identity_key]
        added[identity_key] = identity_value + 1000000000 if isinstance(identity_value, (int, float)) and not isinstance(identity_value, bool) else f"__qa_added__{identity_value}"
        rows.append(added)
        diff_report["rows"] = rows
        diff_report["sha256"] = report_hash(diff_report, page)
        diff_payload = {"name": "changed-snapshot.json", "mimeType": "application/json",
                        "buffer": page.evaluate("(report) => JSON.stringify(report)", diff_report).encode("utf-8")}
        page.locator("#snapshot-a").set_input_files(payload)
        page.locator("#snapshot-b").set_input_files(diff_payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        changed = downloaded_json(page, "#snapshot-download")
        def identity_tuple(row):
            return tuple(row[key] for key in view["identity"])
        expected_added = identity_tuple(added)
        expected_removed = identity_tuple(original_rows[-1])
        expected_changed = identity_tuple(changed_before)
        assert [identity_tuple(row) for row in changed["added"]] == [expected_added]
        assert [identity_tuple(row) for row in changed["removed"]] == [expected_removed]
        assert len(changed["changed"]) == 1
        changed_item = changed["changed"][0]
        assert json.loads(changed_item["identity"]) == list(expected_changed)
        assert changed_item["before"] == changed_before
        assert changed_item["after"] == changed_after

        # Reversing the inputs must reverse only the added/removed direction and changed values.
        page.locator("#snapshot-a").set_input_files(diff_payload)
        page.locator("#snapshot-b").set_input_files(payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        reversed_report = downloaded_json(page, "#snapshot-download")
        assert [identity_tuple(row) for row in reversed_report["added"]] == [expected_removed]
        assert [identity_tuple(row) for row in reversed_report["removed"]] == [expected_added]
        reversed_change = reversed_report["changed"][0]
        assert json.loads(reversed_change["identity"]) == list(expected_changed)
        assert reversed_change["before"] == changed_after
        assert reversed_change["after"] == changed_before
        assert reversed_report["first_sha256"] == diff_report["sha256"]
        assert reversed_report["second_sha256"] == original["sha256"]

        # Reset to a known valid pair before the asynchronous race cases.
        page.locator("#snapshot-a").set_input_files(payload)
        page.locator("#snapshot-b").set_input_files(payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()

        # Hold one older parse, finish a newer upload first, and prove the stale result cannot replace it.
        page.locator("#snapshot-b").set_input_files(payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        page.evaluate("""() => {
          const nativeText = File.prototype.text;
          window.__qaNativeFileText = nativeText;
          window.__qaSlowReleased = false;
          window.__qaReleaseSlowSnapshot = null;
          File.prototype.text = function() {
            if (!this.name.startsWith("slow-")) return nativeText.call(this);
            const file = this;
            return new Promise((resolve, reject) => {
              window.__qaReleaseSlowSnapshot = () => {
                if (file.name.startsWith("slow-fail-")) {
                  window.__qaSlowReleased = true;
                  reject(new Error("delayed snapshot parse failure"));
                  return;
                }
                nativeText.call(file).then(value => {
                  window.__qaSlowReleased = true;
                  resolve(value);
                }, reject);
              };
            });
          };
        }""")
        page.locator("#snapshot-a").set_input_files({"name": "slow-A.json", "mimeType": "application/json", "buffer": good})
        page.wait_for_function("typeof window.__qaReleaseSlowSnapshot === 'function'")
        page.locator("#snapshot-a").set_input_files(diff_payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        latest = downloaded_json(page, "#snapshot-download")
        assert len(latest["added"]) == len(latest["removed"]) == len(latest["changed"]) == 1
        page.evaluate("window.__qaReleaseSlowSnapshot()")
        page.wait_for_function("window.__qaSlowReleased === true")
        page.wait_for_timeout(50)
        assert downloaded_json(page, "#snapshot-download") == latest
        # A stale rejection must not replace a newer successful comparison.
        page.evaluate("() => { window.__qaSlowReleased = false; window.__qaReleaseSlowSnapshot = null; }")
        page.locator("#snapshot-a").set_input_files({"name": "slow-fail-A.json", "mimeType": "application/json", "buffer": good})
        page.wait_for_function("typeof window.__qaReleaseSlowSnapshot === 'function'")
        page.locator("#snapshot-a").set_input_files(payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        latest_after_failure = downloaded_json(page, "#snapshot-download")
        page.evaluate("window.__qaReleaseSlowSnapshot()")
        page.wait_for_function("window.__qaSlowReleased === true")
        page.wait_for_timeout(50)
        assert downloaded_json(page, "#snapshot-download") == latest_after_failure

        # Clearing one side invalidates an older in-flight parse and keeps download disabled.
        page.evaluate("() => { window.__qaSlowReleased = false; window.__qaReleaseSlowSnapshot = null; }")
        page.locator("#snapshot-a").set_input_files({"name": "slow-clear-A.json", "mimeType": "application/json", "buffer": good})
        page.wait_for_function("typeof window.__qaReleaseSlowSnapshot === 'function'")
        page.locator("#snapshot-a").set_input_files([])
        page.locator("#snapshot-status").filter(has_text="請選擇兩份快照").wait_for()
        assert page.locator("#snapshot-download").is_disabled()
        page.evaluate("window.__qaReleaseSlowSnapshot()")
        page.wait_for_function("window.__qaSlowReleased === true")
        page.wait_for_timeout(50)
        assert page.locator("#snapshot-download").is_disabled()
        assert "請選擇兩份快照" in page.locator("#snapshot-status").inner_text()
        # Restore a valid pair so the following invalid-file tests actually parse B.
        page.locator("#snapshot-a").set_input_files(payload)
        page.locator("#snapshot-b").set_input_files(payload)
        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
        page.evaluate("() => { File.prototype.text = window.__qaNativeFileText; }")
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
        page.locator("#snapshot-b").set_input_files({"name": "oversized.json", "mimeType": "application/json",
                                                    "buffer": b" " * (2 * 1024 * 1024 + 1)})
        page.locator("#snapshot-status").filter(has_text="2 MiB").wait_for()
        assert page.locator("#snapshot-download").is_disabled()
        nested = b"[" * 65 + b"0" + b"]" * 65
        page.locator("#snapshot-b").set_input_files({"name": "deep.json", "mimeType": "application/json", "buffer": nested})
        page.locator("#snapshot-status").filter(has_text="巢狀過深").wait_for()
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
    # Back restores the prior view's query, group and scroll position; Forward returns to the new view.
    if len(bundle["datasets"]) > 1:
        page.locator('#views a[href="?view=' + first["id"] + '"]').click()
        row = first["rows"][0]
        query = str(row.get(first["name"]) or row[first["identity"][0]])
        group = str(row[first["group"]])
        page.locator("#group").select_option(group)
        page.locator("#search").fill(query)
        page.evaluate("scrollTo(0, Math.max(0, document.documentElement.scrollHeight - innerHeight - 24))")
        target = bundle["datasets"][1]
        target_link = page.locator('#views a[href="?view=' + target["id"] + '"]')
        target_link.scroll_into_view_if_needed()
        expected_scroll = page.evaluate("scrollY")
        target_link.click()
        assert page.locator("#status").inner_text().startswith(target["label"])
        page.evaluate("history.back()")
        page.wait_for_function("(view) => new URLSearchParams(location.search).get('view') === view", arg=first["id"])
        expect(page.locator("#search")).to_have_value(query)
        expect(page.locator("#group")).to_have_value(group)
        assert abs(page.evaluate("scrollY") - expected_scroll) <= 2
        page.evaluate("history.forward()")
        page.wait_for_function("(view) => new URLSearchParams(location.search).get('view') === view", arg=target["id"])
        assert page.locator("#search").input_value() == ""
        page.locator('#views a[href="?view=' + first["id"] + '"]').click()
        page.locator("#reset").click()
    # Route changes clear prior-view selections and focus a persistent content target.
    if len(bundle["datasets"]) > 1:
        page.locator('#views a[href="?view=' + first["id"] + '"]').click()
        page.locator('#table input[type="checkbox"]').first.check()
        target = bundle["datasets"][1]
        page.locator('#views a[href="?view=' + target["id"] + '"]').focus()
        page.keyboard.press("Enter")
        assert page.locator("#main").evaluate("(node) => node === document.activeElement")
        assert page.locator('#table input[type="checkbox"]:checked').count() == 0
        assert page.locator("#selection-download").is_disabled()
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
            for index, shape in enumerate(("circle", "square", "triangle")):
                assert page.locator('#chart .event-point.series-' + str(index) + '[data-shape="' + shape + '"]').count() > 0
                assert page.locator('#legend .legend-marker .series-' + str(index) + '[data-shape="' + shape + '"]').count() == 1
        if bundle["kind"] == "aqi" and view["id"] == "anomaly":
            assert page.locator("#chart .anomaly-point").count() > 0
            assert "三角形" in page.locator("#legend").inner_text()


def text_spacing_check(page, url, bundle):
    spacing_rules = """* { letter-spacing: .12em !important; word-spacing: .16em !important; line-height: 1.5 !important; }
      p { margin-block-end: 2em !important; }"""

    def serve_test_spacing(route):
        response = route.fetch()
        route.fulfill(response=response, body=response.text() + "\\n" + spacing_rules)

    # Keep the site's strict style-src 'self' CSP intact: serve the test override
    # from the existing same-origin stylesheet request instead of injecting inline CSS.
    page.route("**/styles.css", serve_test_spacing)
    page.goto(url)
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    page.set_viewport_size({"width": 320, "height": 844})
    for view in bundle["datasets"]:
        page.locator('#views a[href="?view=' + view["id"] + '"]').click()
        layout_check(page)
    page.emulate_media(forced_colors="active")
    for view in bundle["datasets"]:
        page.locator('#views a[href="?view=' + view["id"] + '"]').click()
        layout_check(page)
    page.emulate_media(forced_colors="none")


def synthetic_chart_check(browser, url, template):
    """Deterministically cover dense extrema, degenerate values and event marker semantics."""
    bundle = copy.deepcopy(template)
    bundle.update({"kind": "market", "project": "synthetic-chart-qa", "title": "Chart regression fixture",
                   "brand": "Chart QA", "notice": "測試資料", "disclaimer": "測試用途",
                   "source": {"mode": "synthetic", "range": "deterministic fixture"}, "quality": {"fixture": "synthetic"}})
    fields = [{"key": "id", "label": "識別碼", "kind": "text"},
              {"key": "group", "label": "分組", "kind": "text"},
              {"key": "date", "label": "日期", "kind": "date"},
              {"key": "value", "label": "數值", "kind": "number"}]

    def view(view_id, label, rows):
        return {"id": view_id, "label": label, "fields": fields, "identity": ["id"], "group": "group",
                "groupLabel": "分組", "value": "value", "date": "date", "chartLabel": label,
                "sort": "date", "name": "id", "rows": rows}

    start = date(2020, 1, 1)
    dense = []
    for index in range(2405):
        value = 10 + index / 1000
        if index == 11:
            value = 1000
        elif index == 16:
            value = -1000
        day_offset = index + (8 if index >= 12 else 0)
        dense.append({"id": "dense-" + str(index), "group": "dense",
                      "date": (start + timedelta(days=day_offset)).isoformat(), "value": value})
    single = [{"id": "one", "group": "one", "date": "2024-01-01", "value": 7}]
    constant = [{"id": "flat-" + str(index), "group": "flat",
                 "date": "2024-02-0" + str(index + 1), "value": 7} for index in range(3)]
    empty = [{"id": "missing-" + str(index), "group": "missing",
              "date": "2024-03-0" + str(index + 1), "value": None} for index in range(2)]
    events = [{"id": name + "-" + str(index), "group": name, "date": "2024-04-0" + str(index + 1),
               "value": (group_index + 1) * (index + 1)}
              for group_index, name in enumerate(("Alpha", "Bravo", "Charlie")) for index in range(2)]
    bundle["datasets"] = [view("dense", "密集趨勢", dense), view("single", "單點", single),
                          view("constant", "常數", constant), view("empty", "缺值", empty),
                          view("anomaly", "離散事件", events)]
    data_text = json.dumps(bundle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    integrity = json.dumps({"data_sha256": hashlib.sha256(data_text.encode("utf-8")).hexdigest()},
                           separators=(",", ":"))
    page = browser.new_page(viewport={"width": 390, "height": 844})
    page.route("**/integrity.json", lambda route: route.fulfill(body=integrity, content_type="application/json"))
    page.route("**/data.json", lambda route: route.fulfill(body=data_text, content_type="application/json"))
    page.goto(url)
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    coordinates = [tuple(map(float, point.split(","))) for point in
                   page.locator("#chart polyline").first.get_attribute("points").split()]
    assert 2 <= len(coordinates) <= 1200, len(coordinates)
    for index, expected_y in ((11, 10.0), (16, 210.0)):
        day_offset = index + (8 if index >= 12 else 0)
        expected_x = 5 + 890 * day_offset / (2404 + 8)
        assert any(abs(x - expected_x) < 1e-6 and abs(y - expected_y) < 1e-6 for x, y in coordinates), index
    assert "NaN" not in page.locator("#chart svg").evaluate("(node) => node.outerHTML")
    page.locator('#views a[href="?view=single"]').click()
    assert page.locator("#chart polyline").count() == 1 and page.locator("#chart circle.event-point").count() == 1
    page.locator('#views a[href="?view=constant"]').click()
    assert page.locator("#chart polyline").count() == 1
    page.locator('#views a[href="?view=empty"]').click()
    assert page.locator("#chart svg").count() == 0
    page.locator("#chart").filter(has_text="沒有可繪製").wait_for()
    page.locator('#views a[href="?view=anomaly"]').click()
    assert page.locator("#chart polyline").count() == 0
    for index, shape in enumerate(("circle", "square", "triangle")):
        assert page.locator('#chart .event-point.series-' + str(index) + '[data-shape="' + shape + '"]').count() == 2
        assert page.locator('#legend .legend-marker .series-' + str(index) + '[data-shape="' + shape + '"]').count() == 1
    page.close()


def synthetic_cpbl_innings_check(browser, url, template):
    """Verify thirds formatting boundaries without changing published rows or exports."""
    bundle = copy.deepcopy(template)
    bundle.update({"kind": "cpbl", "project": "synthetic-cpbl-qa", "title": "Innings display fixture",
                   "brand": "CPBL QA", "notice": "測試資料", "disclaimer": "測試用途",
                   "source": {"mode": "synthetic", "range": "deterministic fixture"}, "quality": {"fixture": "synthetic"}})
    fields = [{"key": "player_id", "label": "球員代碼", "kind": "text"},
              {"key": "player_name", "label": "球員", "kind": "text"},
              {"key": "team", "label": "球隊", "kind": "text"},
              {"key": "innings_pitched", "label": "投球局數", "kind": "number"}]
    values = [(0, "0"), (7, "7"), (10.333, "10⅓"), (10.667, "10⅔"),
              (10 + 1 / 3 + 1e-10, "10⅓"), (10.1, "10.1"), (10.334, "10.334"), (None, "—")]
    rows = [{"player_id": str(index + 1).zfill(10), "player_name": "測試投手" + str(index + 1),
             "team": "測試隊", "innings_pitched": value} for index, (value, _) in enumerate(values)]
    bundle["datasets"] = [{"id": "pitchers", "label": "投手", "fields": fields, "identity": ["player_id"],
                          "group": "team", "groupLabel": "球隊", "value": "innings_pitched", "date": None,
                          "chartLabel": "投球局數", "sort": "player_id", "name": "player_name", "rows": rows}]
    data_text = json.dumps(bundle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    integrity = json.dumps({"data_sha256": hashlib.sha256(data_text.encode("utf-8")).hexdigest()},
                           separators=(",", ":"))
    context = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
    page = context.new_page()
    page_errors = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.route("**/integrity.json", lambda route: route.fulfill(body=integrity, content_type="application/json"))
    page.route("**/data.json", lambda route: route.fulfill(body=data_text, content_type="application/json"))
    page.goto(url + "?view=pitchers")
    page.locator("#status").filter(has_text="筆符合條件").wait_for()
    for index, (value, expected) in enumerate(values):
        identity = rows[index]["player_id"]
        page.locator("#reset").click()
        page.locator("#search").fill(identity)
        page.locator("#status").filter(has_text="1 筆符合條件").wait_for()
        assert page.locator('td[data-field="innings_pitched"]').first.inner_text() == expected, (value, expected)
        assert page.locator("#json").is_enabled(), (page.locator("#status").inner_text(), page.locator("#table tbody tr").count())
        try:
            with page.expect_download(timeout=5000) as event:
                page.locator("#json").click()
            report = json.loads(Path(event.value.path()).read_text(encoding="utf-8-sig"))
        except Exception as error:
            page.wait_for_timeout(200)
            raise AssertionError("synthetic CPBL JSON export failed: " + page.locator("#selection-status").inner_text()
                                 + "; page errors=" + repr(page_errors)) from error
        assert report["rows"][0]["innings_pitched"] == value
        with page.expect_download() as event:
            page.locator("#csv").click()
        csv_rows = list(csv.DictReader(io.StringIO(Path(event.value.path()).read_text(encoding="utf-8-sig"))))
        exported = csv_rows[0]["innings_pitched"]
        assert (exported == "" if value is None else float(exported) == value), (value, exported)
        if expected.endswith(("⅓", "⅔")):
            page.locator('#table tbody tr input[type="checkbox"]').first.check()
            label = "投球局數"
            compared = page.locator("#comparison article").first.locator("dt").evaluate_all(
                "(nodes, label) => { const node = nodes.find(item => item.textContent === label); return node?.nextElementSibling?.textContent ?? null; }",
                label)
            assert compared == expected
            page.locator("#table tbody tr").first.locator("button").click()
            detail = page.locator("#detail").locator("dt").evaluate_all(
                "(nodes, label) => { const node = nodes.find(item => item.textContent === label); return node?.nextElementSibling?.textContent ?? null; }",
                label)
            assert detail == expected
            page.locator("#close-detail").click()
            page.locator("#clear-selection").click()
    context.close()


def cpbl_innings_display_check(page, url, bundle):
    dataset = next(item for item in bundle["datasets"] if item["id"] == "pitchers")
    field = next(item for item in dataset["fields"] if item["key"] == "innings_pitched")
    samples = {}
    for row in dataset["rows"]:
        value = row["innings_pitched"]
        if not isinstance(value, (int, float)):
            continue
        fraction = value - int(value)
        for expected, target in ((1 / 3, "⅓"), (2 / 3, "⅔")):
            if target not in samples and abs(fraction - expected) <= 0.0005:
                samples[target] = row
    assert set(samples) == {"⅓", "⅔"}, "published pitcher fixture must include both outs-based thirds"
    for symbol, row in samples.items():
        identity = json.dumps([row[key] for key in dataset["identity"]], ensure_ascii=False, separators=(",", ":"))
        selected = quote(json.dumps([identity], ensure_ascii=False, separators=(",", ":")), safe="")
        detail_query = quote(identity, safe="")
        page.goto(url + "?view=pitchers&selected=" + selected + "&detail=" + detail_query)
        page.locator("#status").filter(has_text="筆符合條件").wait_for()
        label = field["label"]
        compared = page.locator("#comparison article").first.locator("dt").evaluate_all(
            "(nodes, label) => { const node = nodes.find(item => item.textContent === label); return node?.nextElementSibling?.textContent ?? null; }",
            label)
        detail = page.locator("#detail").locator("dt").evaluate_all(
            "(nodes, label) => { const node = nodes.find(item => item.textContent === label); return node?.nextElementSibling?.textContent ?? null; }",
            label)
        assert compared.endswith(symbol), (row["innings_pitched"], compared)
        assert detail.endswith(symbol), (row["innings_pitched"], detail)


def cross_browser_smoke(browser_type, url, bundle):
    """Firefox/WebKit smoke; Chromium retains the exhaustive 280-state matrix."""
    browser = browser_type.launch()
    try:
        for theme in ("light", "dark"):
            for width in (390, 1440):
                context = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme,
                                              reduced_motion="reduce", accept_downloads=True)
                page = context.new_page()
                first = bundle["datasets"][0]
                page.goto(url + "?view=" + first["id"])
                page.locator("#status").filter(has_text="筆符合條件").wait_for()
                assert page.locator("html").get_attribute("data-theme") == theme
                contrast_check(page)
                for view in bundle["datasets"]:
                    page.locator('#views a[href="?view=' + view["id"] + '"]').click()
                    assert page.locator("#status").inner_text().startswith(view["label"])
                    layout_check(page)
                    if bundle["kind"] == "market" and view["id"] == "anomaly":
                        for index, shape in enumerate(("circle", "square", "triangle")):
                            assert page.locator('#chart .event-point.series-' + str(index) + '[data-shape="' + shape + '"]').count() > 0
                if theme == "light" and width == 390:
                    first = bundle["datasets"][0]
                    page.locator('#views a[href="?view=' + first["id"] + '"]').click()
                    page.locator("#theme").click()
                    assert page.locator("html").get_attribute("data-theme") == "dark"
                    contrast_check(page)
                    page.locator("#theme").click()
                    assert page.locator("html").get_attribute("data-theme") == "light"
                    report = downloaded_json(page, "#json")
                    assert report["project"] == bundle["project"] and report["dataset"] == first["id"]
                    assert report["sha256"] == report_hash(report, page)
                    if first["date"]:
                        page.locator("#advanced-filters").evaluate("(node) => node.open = true")
                        day = min(row[first["date"]][:10] for row in first["rows"])
                        page.locator("#start").fill(day)
                        page.locator("#end").fill("2000-01-01")
                        assert page.locator("#filter-error").is_visible()
                        for control in ("start", "end"):
                            assert page.locator("#" + control).get_attribute("aria-describedby") == "filter-error"
                            assert page.locator("#" + control).get_attribute("aria-invalid") == "true"
                    if bundle["kind"] == "market":
                        page.locator('#views a[href="?view=overview"]').click()
                        original = downloaded_json(page, "#json")
                        payload = {"name": "snapshot.json", "mimeType": "application/json",
                                   "buffer": page.evaluate("(report) => JSON.stringify(report)", original).encode("utf-8")}
                        page.locator("#snapshot-a").set_input_files(payload)
                        page.locator("#snapshot-b").set_input_files(payload)
                        page.locator("#snapshot-status").filter(has_text="核對通過").wait_for()
                        comparison = downloaded_json(page, "#snapshot-download")
                        assert comparison["added"] == comparison["removed"] == comparison["changed"] == []
                context.close()
    finally:
        browser.close()


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
            text_spacing_check(page, args.url, bundle)
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
        for missing_path in ("**/integrity.json", "**/data.json"):
            failed_context = browser.new_context()
            failed_page = failed_context.new_page()
            failed_page.route(missing_path, lambda route: route.fulfill(status=404, body="missing"))
            failed_page.goto(args.url)
            failed_page.locator("#fatal").wait_for()
            assert failed_page.locator("#json").is_disabled()
            assert failed_page.locator("#table tbody tr").count() == 0
            assert failed_page.locator("#retry").is_enabled() and failed_page.locator("#theme").is_enabled()
            failed_page.unroute(missing_path)
            failed_page.locator("#retry").click()
            failed_page.locator("#status").filter(has_text="筆符合條件").wait_for(timeout=15000)
            assert not failed_page.locator("#fatal").is_visible()
            assert failed_page.locator("#json").is_enabled() and failed_page.locator("#table tbody tr").count() > 0
            failed_context.close()
        synthetic_chart_check(browser, args.url, bundle)
        if bundle["kind"] == "cpbl":
            synthetic_cpbl_innings_check(browser, args.url, bundle)
            page = browser.new_page(viewport={"width": 390, "height": 844}, accept_downloads=True)
            cpbl_innings_display_check(page, args.url, bundle)
            page.close()
        browser.close()
        for browser_type in (engine.firefox, engine.webkit):
            cross_browser_smoke(browser_type, args.url, bundle)
    print("PASS: Chromium 2 themes x 5 viewports x 2 text scales x every page; history, invalid filters, snapshot limits, dense extrema, degenerate charts, marker shapes, raw innings exports; Firefox/WebKit responsive, theme, route, download, snapshot and date smoke")


if __name__ == "__main__":
    main()
