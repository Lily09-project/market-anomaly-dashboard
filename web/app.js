const $ = id => document.getElementById(id);
const el = (tag, text, attrs = {}) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
};
const number = value => typeof value === "number" && Number.isFinite(value);
const format = value => value === null || value === undefined || value === "" ? "—" :
  number(value) ? new Intl.NumberFormat("zh-TW", {maximumFractionDigits: 3}).format(value) : String(value);

function formatField(field, value) {
  if (["is_anomaly", "model_anomaly"].includes(field.key)) return value === 1 ? "異常" : value === 0 ? "正常" : "—";
  if (!number(value)) return format(value);
  const key = field.key;
  if (bundle?.kind === "cpbl" && key === "innings_pitched" && value >= 0) {
    const innings = Math.floor(value), fraction = value - innings;
    if (Math.abs(fraction - 1 / 3) <= 0.0005) return innings + "⅓";
    if (Math.abs(fraction - 2 / 3) <= 0.0005) return innings + "⅔";
  }
  if (key === "season") return String(Math.trunc(value));
  if (["daily_return", "volatility_20"].includes(key)) return new Intl.NumberFormat("zh-TW", {style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2}).format(value);
  const digits = ["batting_average", "ops", "win_pct", "whip"].includes(key) ? 3 : ["close", "era"].includes(key) ? 2 : null;
  return digits === null ? format(value) : new Intl.NumberFormat("zh-TW", {minimumFractionDigits: digits, maximumFractionDigits: digits}).format(value);
}
// Published naive timestamps are Taiwan wall time; calendar dates never use viewer time.
function chartTime(value) {
  const text = String(value);
  if (/^\d{4}-\d{2}-\d{2}$/u.test(text)) return Date.parse(text + "T00:00:00Z");
  if (/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/u.test(text) && !/(?:Z|[+-]\d{2}:?\d{2})$/u.test(text)) return Date.parse(text.replace(" ", "T") + "+08:00");
  return Date.parse(text);
}
function chartDate(time) {
  return new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit"}).format(new Date(time));
}
function compactFields() {
  const extra = bundle.kind === "market" ? ["daily_return", "model_anomaly"] : dataset.id === "batters" ? ["batting_average", "pa"] :
    dataset.id === "pitchers" ? ["era", "innings_pitched"] : dataset.id === "roster" ? ["roster_status", "player_type"] : dataset.id === "teams" ? ["season", "wins", "losses"] : bundle.kind === "aqi" ? ["pm25", "is_anomaly", "actual_next_hour_aqi"] : [];
  return new Set([dataset.name === "snapshot_id" ? null : dataset.name, dataset.group, dataset.date, dataset.value, ...extra].filter(Boolean));
}
function tablePageSize() {
  return $("table").clientWidth <= 56 * parseFloat(getComputedStyle($("table")).fontSize) ? 8 : 20;
}
function focusView() {
  $("main").focus({preventScroll: true});
  $("views").scrollIntoView({block: "start", behavior: "auto"});
}
function focusResults() {
  $("table-title").focus({preventScroll: true});
  $("table-title").scrollIntoView({block: "start", behavior: "auto"});
}
function syncAdvancedFilters() {
  const active = !!(state.start || state.end || (dataset.minimum && state.minimum !== dataset.minimum.value));
  $("advanced-filters").hidden = !(dataset.date || dataset.minimum);
  $("advanced-summary").textContent = active ? "進階篩選 · 已套用" :
    dataset.minimum && state.minimum > 0 ? "進階篩選 · " + dataset.minimum.label + " " + state.minimum : "進階篩選";
  // Keep the user’s disclosure choice when sorting or filtering re-renders results.
}

const hash = async text => Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text))))
  .map(byte => byte.toString(16).padStart(2, "0")).join("");
const csvCell = value => {
  let text = value === null || value === undefined ? "" : String(value);
  if (!number(value) && /^[\s]*[=+\-@\t\r]/u.test(text)) text = "'" + text;
  return '"' + text.replaceAll('"', '""') + '"';
};
function download(text, name, mime) {
  const url = URL.createObjectURL(new Blob([text], {type: mime}));
  const link = el("a", "", {href: url, download: name});
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
}
let bundle, dataset, state, displayed = [], selected = new Set(), currentPage = 0, lastDetailButton;
let pageSize = 20, resizeFrame = 0;
const rowId = row => JSON.stringify(dataset.identity.map(key => row[key]));
const rowName = row => [...new Set([dataset.name, ...dataset.identity].filter(Boolean))]
  .map(key => formatField(dataset.fields.find(field => field.key === key) || {key}, row[key])).join(" · ");
const selectedRows = () => [...selected].map(id => dataset.rows.find(row => rowId(row) === id)).filter(Boolean);
function readState() {
  const query = new URLSearchParams(location.search);
  const view = bundle.datasets.find(item => item.id === query.get("view")) || bundle.datasets[0];
  state = {
    view: view.id, search: (query.get("q") || "").slice(0, 150), group: query.get("group") || "",
    start: /^\d{4}-\d{2}-\d{2}$/u.test(query.get("start") || "") ? query.get("start") : "",
    end: /^\d{4}-\d{2}-\d{2}$/u.test(query.get("end") || "") ? query.get("end") : "",
    onlyAnomaly: query.get("anomaly") === "1" && view.fields.some(field => field.key === "is_anomaly" || field.key === "model_anomaly"),
    minimum: Number(query.get("min") ?? view.minimum?.value ?? 0),
    sort: query.get("sort") || view.sort, descending: query.get("direction") !== "asc",
    detail: (query.get("detail") || "").slice(0, 500)
  };
  if (!Number.isFinite(state.minimum) || state.minimum < 0 || state.minimum > 100000) state.minimum = view.minimum?.value || 0;
  selected = new Set();
  try {
    const ids = JSON.parse(query.get("selected") || "[]");
    if (Array.isArray(ids)) selected = new Set(ids.filter(item => typeof item === "string").slice(0, 3));
  } catch { /* Ignore invalid, untrusted URL state. */ }
  dataset = view;
  if (!dataset.fields.some(field => field.key === state.sort)) state.sort = dataset.sort;
  const page = Number(query.get("page") || 1);
  currentPage = Number.isSafeInteger(page) && page > 0 && page <= 20000 ? page - 1 : 0;
  const valid = new Set(dataset.rows.map(rowId));
  selected = new Set([...selected].filter(id => valid.has(id)));
}
function saveState(push = false) {
  const query = new URLSearchParams();
  query.set("view", state.view);
  for (const [key, value] of [["q", state.search], ["group", state.group], ["start", state.start],
    ["end", state.end], ["sort", state.sort], ["direction", state.descending ? "desc" : "asc"],
    ["min", dataset.minimum ? String(state.minimum) : ""], ["anomaly", state.onlyAnomaly ? "1" : ""], ["detail", state.detail]]) {
    if (value) query.set(key, value);
  }
  if (selected.size) query.set("selected", JSON.stringify([...selected]));
  if (currentPage) query.set("page", String(currentPage + 1));
  if (push) history.replaceState({...history.state, scrollY: scrollY}, "", location.href);
  history[push ? "pushState" : "replaceState"](push ? {scrollY: 0} : history.state, "", location.pathname + "?" + query);
}
function fillControls() {
  $("search").value = state.search;
  $("search").placeholder = dataset.id === "metrics" ? "搜尋模型或評估指標" : "搜尋股票代碼或關鍵字";
  $("anomaly-label").hidden = !dataset.fields.some(field => ["is_anomaly", "model_anomaly"].includes(field.key));
  $("only-anomaly").checked = !!state.onlyAnomaly;
  $("group").replaceChildren(el("option", "全部" + dataset.groupLabel, {value: ""}));
  const groups = [...new Set(dataset.rows.map(row => row[dataset.group]).filter(value => value !== null))].sort();
  for (const value of groups) $("group").append(el("option", String(value), {value}));
  if (!groups.map(String).includes(state.group)) state.group = "";
  $("group").value = state.group;
  $("group-label").firstChild.textContent = dataset.groupLabel;
  for (const id of ["start", "end"]) {
    $(id + "-label").hidden = !dataset.date;
    $(id).value = state[id];
  }
  $("minimum-label").hidden = !dataset.minimum;
  if (dataset.minimum) {
    $("minimum-label").firstChild.textContent = dataset.minimum.label;
    $("minimum").value = state.minimum;
  }
  $("sort").replaceChildren(...dataset.fields.map(field => el("option", field.label, {value: field.key})));
  $("sort").value = state.sort;
  $("direction").textContent = state.descending ? "遞減" : "遞增";
  syncAdvancedFilters();
  $("views").replaceChildren(...bundle.datasets.map(item => {
    const link = el("a", item.label, {href: "?view=" + encodeURIComponent(item.id)});
    if (item.id === dataset.id) link.setAttribute("aria-current", "page");
    link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      state = {view: item.id, search: "", group: "", start: "", end: "", minimum: item.minimum?.value || 0,
        sort: item.sort, descending: true, onlyAnomaly: false, detail: ""};
      dataset = item; selected.clear(); currentPage = 0; fillControls(); saveState(true); render();
      focusView();
    });
    return link;
  }));
}
function filteredRows() {
  const query = state.search.trim().toLocaleLowerCase("zh-TW");
  if (dataset.date && state.start && state.end && state.start > state.end) return [];
  return dataset.rows.filter(row =>
    (!state.group || String(row[dataset.group]) === state.group) &&
    (!state.onlyAnomaly || row.is_anomaly === 1 || row.model_anomaly === 1) &&
    (!query || dataset.fields.some(field => String(row[field.key] ?? "").toLocaleLowerCase("zh-TW").includes(query))) &&
    (!dataset.date || !state.start || String(row[dataset.date]).slice(0, 10) >= state.start) &&
    (!dataset.date || !state.end || String(row[dataset.date]).slice(0, 10) <= state.end) &&
    (!dataset.minimum || (number(row[dataset.minimum.key]) && row[dataset.minimum.key] >= state.minimum))
  ).sort((a, b) => {
    const left = a[state.sort], right = b[state.sort];
    if (left === null) return right === null ? 0 : 1;
    if (right === null) return -1;
    const value = number(left) && number(right) ? left - right : String(left).localeCompare(String(right), "zh-TW");
    return state.descending ? -value : value;
  });
}
function renderMetrics() {
  if (dataset.id === "metrics") {
    $("metrics").replaceChildren(...[["評估指標", displayed.length], ["模型數", new Set(displayed.map(row => row.model)).size]].map(([label, value]) => {
      const card = el("article", undefined, {class: "metric"}); card.append(el("p", label), el("strong", format(value))); return card;
    })); return;
  }
  const values = displayed.map(row => row[dataset.value]).filter(number);
  const missing = displayed.reduce((count, row) => count + dataset.fields.filter(field => row[field.key] === null).length, 0);
  const hasAnomalies = dataset.fields.some(field => ["is_anomaly", "model_anomaly"].includes(field.key));
  const anomalyCount = displayed.filter(row => row.is_anomaly === 1 || row.model_anomaly === 1).length;
  const cards = [["符合條件筆數", displayed.length], [dataset.groupLabel + "數", new Set(displayed.map(row => row[dataset.group])).size],
    [dataset.fields.find(field => field.key === dataset.value).label + " 樣本平均", values.length ? values.reduce((a, b) => a + b, 0) / values.length : null],
    [hasAnomalies ? "異常紀錄" : "缺值數", hasAnomalies ? anomalyCount : missing]];
  $("metrics").replaceChildren(...cards.map(([label, value]) => {
    const card = el("article", undefined, {class: "metric", title: label === "缺值數" ? "符合條件資料中的空白儲存格數" : label === "異常紀錄" ? "任一已發布異常標記為異常的紀錄數；不是即時警報" : label.includes("樣本平均") ? "符合篩選條件的有效數值平均；不是最新一筆或預測信心" : label});
    card.append(el("p", label), el("strong", label.includes("樣本平均") ? formatField(dataset.fields.find(field => field.key === dataset.value), value) : format(value))); return card;
  }));
}
const svgNS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs) {
  const node = document.createElementNS(svgNS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}
function sampleTrendRows(rows, key, maxPoints = 1200) {
  if (rows.length <= maxPoints) return rows;
  const bucketCount = Math.max(1, Math.floor((maxPoints - 2) / 2));
  const bucketSize = Math.ceil(rows.length / bucketCount);
  const selected = new Set([0, rows.length - 1]);
  for (let start = 0; start < rows.length; start += bucketSize) {
    const end = Math.min(rows.length, start + bucketSize);
    let minimum = start, maximum = start;
    for (let index = start + 1; index < end; index++) {
      if (rows[index][key] < rows[minimum][key]) minimum = index;
      if (rows[index][key] > rows[maximum][key]) maximum = index;
    }
    selected.add(minimum); selected.add(maximum);
  }
  return [...selected].sort((a, b) => a - b).map(index => rows[index]);
}
function appendEventMarker(parent, index, cx, cy, seriesClass) {
  const shape = ["circle", "square", "triangle"][index % 3];
  const common = {class: "event-point " + seriesClass, "data-shape": shape};
  const marker = shape === "circle" ? svgEl("circle", {...common, cx, cy, r: 3.5}) :
    shape === "square" ? svgEl("rect", {...common, x: cx - 3.5, y: cy - 3.5, width: 7, height: 7}) :
      svgEl("path", {...common, d: "M " + cx + " " + (cy - 4.5) + " l 4.5 8 h -9 Z"});
  parent.append(marker);
}
function eventLegendMarker(index, seriesClass) {
  const marker = svgEl("svg", {class: "legend-marker", viewBox: "0 0 12 12", "aria-hidden": "true", focusable: "false"});
  appendEventMarker(marker, index, 6, 6, seriesClass);
  return marker;
}
function renderChart() {
  $("chart-panel").hidden = dataset.id === "metrics";
  if (dataset.id === "metrics") return;
  $("chart").replaceChildren(); $("legend").replaceChildren(); $("legend").classList.remove("events");
  $("chart-title").textContent = dataset.chartLabel;
  $("chart").className = "chart";
  if (!displayed.length) { $("chart").append(el("p", "沒有符合條件的資料。", {class: "empty"})); return; }
  if (!dataset.date) {
    const rows = [...displayed].filter(row => number(row[dataset.value])).sort((a, b) => b[dataset.value] - a[dataset.value]).slice(0, 10);
    const max = Math.max(1, ...rows.map(row => row[dataset.value]));
    $("chart").className = "chart bars";
    for (const row of rows) {
      const wrap = el("div", undefined, {class: "bar-row"});
      const name = row[dataset.name] || row[dataset.group];
      wrap.append(el("p", String(name) + " · " + formatField(dataset.fields.find(field => field.key === dataset.value), row[dataset.value])),
        el("meter", formatField(dataset.fields.find(field => field.key === dataset.value), row[dataset.value]), {min: 0, max, value: row[dataset.value], "aria-label": String(name)}));
      $("chart").append(wrap);
    }
    return;
  }
  const groupOrder = [...new Set(dataset.rows.map(row => row[dataset.group]))].sort((a, b) => String(a).localeCompare(String(b), "zh-TW"));
  const present = new Set(displayed.map(row => row[dataset.group]));
  const groups = groupOrder.filter(group => present.has(group)).slice(0, 3);
  const series = dataset.secondary ?
    [{key: dataset.value, label: dataset.fields.find(field => field.key === dataset.value).label, group: groups[0]},
      {key: dataset.secondary, label: dataset.fields.find(field => field.key === dataset.secondary).label, group: groups[0]}] :
    groups.map(group => ({key: dataset.value, label: String(group), group}));
  const all = series.flatMap(item => displayed.filter(row => row[dataset.group] === item.group && number(row[item.key])));
  if (!all.length) { $("chart").append(el("p", "此範圍沒有可繪製的數值。")); return; }
  const xs = all.map(row => chartTime(row[dataset.date]));
  const lowX = Math.min(...xs), highX = Math.max(...xs);
  const ys = series.flatMap(item => all.filter(row => row[dataset.group] === item.group).map(row => row[item.key]).filter(number));
  let lowY = Math.min(...ys), highY = Math.max(...ys);
  if (lowY === highY) { const padding = Math.max(1, Math.abs(lowY) * .05); lowY -= padding; highY += padding; }
  const eventChart = bundle.kind === "market" && dataset.id === "anomaly";
  if (eventChart) $("legend").classList.add("events");
  const point = row => [5 + 890 * (chartTime(row[dataset.date]) - lowX) / (highX - lowX || 1), 210 - 200 * (row[dataset.value] - lowY) / (highY - lowY)];
  const svg = svgEl("svg", {viewBox: "0 0 900 220", role: "img", "aria-label": dataset.chartLabel + "；完整數值見資料明細", preserveAspectRatio: "none"});
  for (let y = 10; y <= 210; y += 50) svg.append(svgEl("line", {x1: 5, x2: 895, y1: y, y2: y, class: "grid"}));
  series.forEach((item, index) => {
    const buckets = new Map();
    for (const row of displayed.filter(row => row[dataset.group] === item.group && number(row[item.key]))) {
      const key = row[dataset.date];
      const bucket = buckets.get(key) || {sum: 0, count: 0};
      bucket.sum += row[item.key]; bucket.count++; buckets.set(key, bucket);
    }
    const rows = [...buckets].map(([time, bucket]) => ({[dataset.date]: time, [item.key]: bucket.sum / bucket.count}))
      .sort((a, b) => String(a[dataset.date]).localeCompare(String(b[dataset.date])));
    const lineRows = sampleTrendRows(rows, item.key);
    const points = lineRows.map(row =>
      (5 + 890 * (chartTime(row[dataset.date]) - lowX) / (highX - lowX || 1)) + "," +
      (210 - 200 * (row[item.key] - lowY) / (highY - lowY || 1))).join(" ");
    const seriesIndex = dataset.secondary ? index : groupOrder.indexOf(item.group) % 3;
    const seriesClass = "series-" + seriesIndex;
    if (eventChart) {
      for (const row of rows) {
        const [cx, cy] = point(row);
        appendEventMarker(svg, seriesIndex, cx, cy, seriesClass);
      }
    } else {
      svg.append(svgEl("polyline", {points, class: "line " + seriesClass}));
      if (rows.length === 1) {
        const row = rows[0], cx = 5, cy = 210 - 200 * (row[item.key] - lowY) / (highY - lowY);
        svg.append(svgEl("circle", {cx, cy, r: 4, class: "event-point " + seriesClass}));
      }
    }
    if (bundle.kind === "aqi" && dataset.id === "anomaly") {
      for (const row of displayed.filter(row => row[dataset.group] === item.group && row.is_anomaly === 1 && number(row[item.key]))) {
        const [cx, cy] = point(row);
        svg.append(svgEl("path", {d: "M " + cx + " " + (cy - 5) + " l 5 10 h -10 Z", class: "anomaly-point"}));
      }
    }
    if (eventChart) {
      const entry = el("span", undefined, {class: "event-legend " + seriesClass});
      entry.append(eventLegendMarker(seriesIndex, seriesClass), document.createTextNode(item.label));
      $("legend").append(entry);
    } else $("legend").append(el("span", item.label, {class: seriesClass}));
  });
  const axis = el("div", undefined, {class: "axis"});
  axis.append(el("span", chartDate(lowX)), el("span", dataset.fields.find(field => field.key === dataset.value).label + " " + formatField(dataset.fields.find(field => field.key === dataset.value), lowY) + "–" + formatField(dataset.fields.find(field => field.key === dataset.value), highY)),
    el("span", chartDate(highX)));
  const plot = el("div", undefined, {class: "chart-plot"});
  const scale = el("div", undefined, {class: "y-scale", "aria-hidden": "true"});
  const field = dataset.fields.find(field => field.key === dataset.value);
  for (const value of [highY, (highY + lowY) / 2, lowY]) scale.append(el("span", formatField(field, value)));
  plot.append(scale, svg);
  $("chart").append(plot, axis);
  if (bundle.kind === "aqi" && dataset.id === "anomaly") $("legend").append(el("span", "三角形：模型標記異常", {class: "anomaly-legend"}));
  if (!dataset.secondary && new Set(displayed.map(row => row[dataset.group])).size > 3) $("legend").append(el("p", "圖表顯示前三組；完整資料見明細。"));
  if (dataset.secondary) $("legend").append(el("p", "測站：" + String(groups[0])));
}
function renderTable() {
  pageSize = tablePageSize();
  $("table-title").textContent = dataset.label;
  const pages = Math.max(1, Math.ceil(displayed.length / pageSize));
  currentPage = Math.min(currentPage, pages - 1);
  const table = el("table", undefined, {role: "table"});
  const columns = el("colgroup");
  columns.append(el("col", undefined, {class: "action-column"}));
  for (const field of dataset.fields) columns.append(el("col", undefined, {class: field.key === "player_id" ? "identifier-column" : field.kind === "date" ? (field.key === "date" ? "date-column" : "timestamp-column") : field.key === "volume" ? "volume-column" : ""}));
  columns.append(el("col", undefined, {class: "action-column"}));
  table.append(columns);
  const head = el("thead"), hrow = el("tr");
  const compact = compactFields();
  hrow.append(el("th", "比較", {scope: "col"}));
  for (const field of dataset.fields) {
    const th = el("th", field.label, {scope: "col", "data-kind": field.kind, class: compact.has(field.key) ? "" : "secondary-field"});
    if (field.key === state.sort) th.setAttribute("aria-sort", state.descending ? "descending" : "ascending");
    hrow.append(th);
  }
  hrow.append(el("th", "詳情", {scope: "col"}));
  head.append(hrow); table.append(head);
  const body = el("tbody");
  for (const row of displayed.slice(currentPage * pageSize, (currentPage + 1) * pageSize)) {
    const id = rowId(row), tr = el("tr", undefined, {"data-row-id": id}), pick = el("td", undefined, {"data-label": "比較"});
    const label = el("label", undefined, {class: "pick"});
    const check = el("input", undefined, {type: "checkbox", "aria-label": "比較 " + rowName(row)});
    check.checked = selected.has(id);
    check.disabled = !check.checked && selected.size >= 3;
    check.addEventListener("change", () => {
      if (check.checked) selected.add(id); else selected.delete(id);
      saveState(); renderComparison();
      for (const input of $("table").querySelectorAll('input[type="checkbox"]')) input.disabled = !input.checked && selected.size >= 3;
    });
    label.append(check, el("span", "選取")); pick.append(label); tr.append(pick);
    for (const field of dataset.fields) tr.append(el("td", formatField(field, row[field.key]), {
      "data-label": field.label, "data-field": field.key, "data-kind": field.kind, class: compact.has(field.key) ? "" : "secondary-field"
    }));
    const cell = el("td", undefined, {"data-label": "詳情"});
    const button = el("button", "查看", {type: "button", "aria-label": "查看 " + rowName(row)});
    button.addEventListener("click", () => {lastDetailButton = button; state.detail = id; saveState(true); renderDetail(true);});
    cell.append(button); tr.append(cell); body.append(tr);
  }
  table.append(body);
  $("table").replaceChildren(displayed.length ? table : el("p", "找不到資料，請調整或重設篩選。", {class: "empty"}));
  $("page-count").textContent = (currentPage + 1) + " / " + pages;
  $("previous").disabled = currentPage === 0; $("next").disabled = currentPage + 1 >= pages;
  $("csv").disabled = !displayed.length; $("json").disabled = !displayed.length;
}
function valuesDl(row) {
  const dl = el("dl");
  for (const field of dataset.fields) dl.append(el("dt", field.label), el("dd", formatField(field, row[field.key])));
  return dl;
}
function renderComparison() {
  const rows = selectedRows();
  $("compare-jump").disabled = !rows.length;
  $("compare-jump").textContent = "查看比較 · " + rows.length + "/3";
  $("comparison").replaceChildren(...rows.map(row => {
    const card = el("article"); card.append(el("h3", rowName(row)), valuesDl(row));
    const remove = el("button", "移除", {type: "button", "aria-label": "移除 " + rowName(row)});
    remove.addEventListener("click", () => {
      selected.delete(rowId(row)); saveState(); renderTable(); renderComparison();
      ($("comparison").querySelector("button") || $("compare-title")).focus();
    });
    card.append(remove); return card;
  }));
  $("selection-status").textContent = rows.length ? "已選取 " + rows.length + " / 3 筆資料。" : "勾選表格的比較欄，最多可比較 3 筆資料。";
  $("clear-selection").disabled = !rows.length; $("selection-download").disabled = !rows.length;
}
function renderDetail(focus = false) {
  const row = dataset.rows.find(item => rowId(item) === state.detail);
  $("detail-panel").hidden = !row;
  if (!row) return;
  $("detail-title").textContent = rowName(row);
  $("detail").replaceChildren(valuesDl(row));
  if (bundle.kind === "cpbl" && /^\d{10}$/u.test(row.player_id || "")) {
    $("detail").append(el("a", "CPBL 官方球員頁", {href: "https://www.cpbl.com.tw/team/person?acnt=" + row.player_id, rel: "noopener noreferrer"}));
  }
  if (focus) $("detail-title").focus();
}
function render() {
  const invalid = dataset.date && state.start && state.end && state.start > state.end;
  $("filter-error").hidden = !invalid;
  $("filter-error").textContent = invalid ? "結束日期不能早於開始日期，請修正日期或重設篩選。" : "";
  for (const id of ["start", "end"]) {
    if (dataset.date) $(id).setAttribute("aria-describedby", "filter-error");
    else $(id).removeAttribute("aria-describedby");
    if (invalid) $(id).setAttribute("aria-invalid", "true");
    else $(id).removeAttribute("aria-invalid");
  }
  syncAdvancedFilters();
  displayed = filteredRows();
  $("status").textContent = dataset.label + " · " + displayed.length + " 筆符合條件";
  renderMetrics(); renderChart(); renderTable(); renderComparison(); renderDetail();
}
async function exportReport(rows) {
  const payload = {schema_version: "pages-report/1", project: bundle.project, dataset: dataset.id,
    source: bundle.source, filters: {search: state.search, group: state.group, start: state.start, end: state.end, minimum: state.minimum, only_anomaly: !!state.onlyAnomaly},
    columns: dataset.fields, rows};
  const canonical = JSON.stringify(payload);
  const report = {...payload, sha256: await hash(canonical)};
  download(JSON.stringify(report, null, 2), bundle.project + "-" + dataset.id + ".json", "application/json;charset=utf-8");
}

let comparisonReport = null;
function compactJson(text) {
  let compact = "", quoted = false, escaped = false, depth = 0;
  for (const char of text) {
    if (quoted) {
      compact += char;
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') { quoted = true; compact += char; }
    else if (!/\s/u.test(char)) {
      if (char === "{" || char === "[") depth++;
      if (char === "}" || char === "]") depth--;
      if (depth > 64) throw new Error("JSON 巢狀過深。");
      compact += char;
    }
  }
  return compact;
}
async function parseSnapshot(file) {
  if (file.size > 2 * 1024 * 1024) throw new Error("檔案不可超過 2 MiB。");
  const text = await file.text();
  const compact = compactJson(text);
  const report = JSON.parse(text);
  if (JSON.stringify(report) !== compact) throw new Error("請使用本網站匯出的原始 JSON，檔案含重複欄位或非標準格式。");
  const expected = ["schema_version", "project", "dataset", "source", "filters", "columns", "rows", "sha256"];
  if (!report || Object.keys(report).sort().join(",") !== expected.sort().join(",")) throw new Error("快照欄位不符。");
  if (report.schema_version !== "pages-report/1" || report.project !== bundle.project) throw new Error("快照不是此網站的匯出格式。");
  const {sha256, ...payload} = report;
  if (await hash(JSON.stringify(payload)) !== sha256) throw new Error("快照 SHA-256 不一致，內容可能已修改。");
  const view = bundle.datasets.find(item => item.id === report.dataset);
  if (!view || JSON.stringify(view.fields) !== JSON.stringify(report.columns)) throw new Error("快照分析頁面或欄位不符。");
  if (!Array.isArray(report.rows) || report.rows.length > 20000) throw new Error("快照資料量不符。");
  for (const row of report.rows) {
    if (!row || Array.isArray(row) || Object.keys(row).sort().join(",") !== view.fields.map(field => field.key).sort().join(",")) throw new Error("快照資料欄位不符。");
    for (const field of view.fields) {
      const value = row[field.key];
      if (value === null) continue;
      if (field.kind === "number" ? !number(value) : typeof value !== "string" || value.length > 500) throw new Error("快照資料型別不符。");
      if (field.kind === "date" && !Number.isFinite(Date.parse(value))) throw new Error("快照日期無效。");
    }
    if (view.identity.some(key => row[key] === null)) throw new Error("快照缺少資料識別。");
  }
  const identities = report.rows.map(row => JSON.stringify(view.identity.map(key => row[key])));
  if (new Set(identities).size !== identities.length) throw new Error("快照含重複識別。");
  return report;
}
let uploadGeneration = 0;
async function compareUploads() {
  const generation = ++uploadGeneration;
  comparisonReport = null; $("snapshot-download").disabled = true; $("snapshot-result").replaceChildren();
  const first = $("snapshot-a").files[0], second = $("snapshot-b").files[0];
  if (!first || !second) { $("snapshot-status").textContent = "請選擇兩份快照。"; return; }
  $("snapshot-status").textContent = "正在核對快照…";
  try {
    const [a, b] = await Promise.all([parseSnapshot(first), parseSnapshot(second)]);
    if (generation !== uploadGeneration) return;
    if (a.dataset !== b.dataset) throw new Error("兩份快照必須來自同一分析頁面。");
    const view = bundle.datasets.find(item => item.id === a.dataset);
    const key = row => JSON.stringify(view.identity.map(field => row[field]));
    const left = new Map(a.rows.map(row => [key(row), row])), right = new Map(b.rows.map(row => [key(row), row]));
    const added = [...right].filter(([id]) => !left.has(id)).map(([, row]) => row);
    const removed = [...left].filter(([id]) => !right.has(id)).map(([, row]) => row);
    const changed = [...left].filter(([id, row]) => right.has(id) && JSON.stringify(row) !== JSON.stringify(right.get(id)))
      .map(([id, row]) => ({identity: id, before: row, after: right.get(id)}));
    comparisonReport = {schema_version: "pages-comparison/1", project: bundle.project, dataset: a.dataset,
      first_sha256: a.sha256, second_sha256: b.sha256, added, removed, changed};
    $("snapshot-status").textContent = "內容完整性核對通過（非來源身分認證）。";
    const dl = el("dl");
    for (const [name, value] of [["新增", added.length], ["移除", removed.length], ["變更", changed.length]]) dl.append(el("dt", name), el("dd", String(value)));
    $("snapshot-result").append(dl); $("snapshot-download").disabled = false;
  } catch (error) {
    if (generation !== uploadGeneration) return;
    $("snapshot-status").textContent = error instanceof SyntaxError ? "JSON 格式錯誤，請使用原始匯出檔案。" : error.message;
  }
}

async function fetchPublic(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, {cache: "no-cache", signal: controller.signal});
    if (!response.ok) throw new Error("Public resource unavailable");
    return await response.text();
  } finally { clearTimeout(timer); }
}
async function initialize() {
  const integrity = JSON.parse(await fetchPublic("./integrity.json"));
  const text = await fetchPublic("./data.json");
  if (await hash(text) !== integrity.data_sha256) throw new Error("Data integrity mismatch");
  bundle = JSON.parse(text);
  if (bundle.schema_version !== "pages-data/1" || !Array.isArray(bundle.datasets) || !bundle.datasets.length) throw new Error("Invalid schema");
  document.documentElement.dataset.project = bundle.kind;
  $("title").textContent = bundle.title; document.title = bundle.title;
  $("brand").textContent = bundle.brand; $("repository").href = "https://github.com/Lily09-project/" + bundle.project;
  $("mode").textContent = bundle.source.mode;
  $("source-date").textContent = "資料期間 " + bundle.source.range;
  $("notice").textContent = bundle.notice;
  if (bundle.source.captured_at) {
    const age = Math.floor((Date.now() - Date.parse(bundle.source.captured_at)) / 86400000);
    $("source-date").textContent = "資料更新 " + bundle.source.captured_at.slice(0, 10) + (age > 7 ? " · 已超過 7 天未更新" : "");
  }
  $("disclaimer").textContent = bundle.disclaimer;
  for (const [key, value] of Object.entries(bundle.quality)) $("quality").append(el("dt", key), el("dd", format(value)));
  for (const node of document.querySelectorAll("[data-loading-control]")) node.disabled = false;
  $("chart-panel").hidden = false;
  readState(); fillControls(); render();
  $("snapshot-panel").hidden = bundle.kind !== "market";
  for (const id of ["snapshot-a", "snapshot-b"]) $(id).addEventListener("change", compareUploads);
  $("snapshot-download").addEventListener("click", () => { if (comparisonReport) download(JSON.stringify(comparisonReport, null, 2), "snapshot-comparison.json", "application/json;charset=utf-8"); });
  for (const [id, key] of [["search", "search"], ["group", "group"], ["start", "start"], ["end", "end"], ["sort", "sort"], ["minimum", "minimum"]]) {
    $(id).addEventListener(id === "search" ? "input" : "change", () => {
      state[key] = key === "minimum" ? Number($(id).value) : $(id).value;
      if (key === "minimum" && (!Number.isFinite(state.minimum) || state.minimum < 0 || state.minimum > 100000)) {
        state.minimum = dataset.minimum?.value || 0; $(id).value = state.minimum;
      }
      currentPage = 0; saveState(); render();
    });
  }
  $("only-anomaly").addEventListener("change", () => {state.onlyAnomaly = $("only-anomaly").checked; currentPage = 0; saveState(); render();});
  $("compare-jump").addEventListener("click", () => {$("compare-title").focus({preventScroll: true}); $("compare-title").scrollIntoView({block: "start"});});
  $("direction").addEventListener("click", () => {state.descending = !state.descending; $("direction").textContent = state.descending ? "遞減" : "遞增"; saveState(); render();});
  $("reset").addEventListener("click", () => {
    Object.assign(state, {onlyAnomaly: false, search: "", group: "", start: "", end: "", detail: "", minimum: dataset.minimum?.value || 0});
    currentPage = 0; fillControls(); saveState(); render();
  });
  for (const [id, delta] of [["previous", -1], ["next", 1]]) {
    $(id).addEventListener("click", () => {currentPage += delta; renderTable(); saveState(); focusResults();});
  }
  const resize = () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {
      const nextSize = tablePageSize();
      if (nextSize === pageSize) return;
      const firstIndex = currentPage * pageSize, focused = document.activeElement;
      const id = focused.closest?.("tr[data-row-id]")?.getAttribute("data-row-id");
      const control = focused.tagName;
      currentPage = Math.floor(firstIndex / nextSize);
      renderTable(); saveState();
      if (id) {
        const replacement = [...$("table").querySelectorAll("tr[data-row-id]")].find(item => item.getAttribute("data-row-id") === id);
        (replacement?.querySelector(control === "INPUT" ? "input" : "button") || $("table-title")).focus({preventScroll: true});
      }
    });
  };
  new ResizeObserver(resize).observe($("table"));
  $("csv").addEventListener("click", () => download("\ufeff" + [dataset.fields.map(field => csvCell(field.key)).join(","),
    ...displayed.map(row => dataset.fields.map(field => csvCell(row[field.key])).join(","))].join("\r\n"),
    bundle.project + "-" + dataset.id + ".csv", "text/csv;charset=utf-8"));
  const safeExport = rows => exportReport(rows).catch(() => {$("selection-status").textContent = "無法建立報告，請重新整理後再試。";});
  $("json").addEventListener("click", () => safeExport(displayed));
  $("selection-download").addEventListener("click", () => safeExport(selectedRows()));
  $("clear-selection").addEventListener("click", () => {selected.clear(); saveState(); renderTable(); renderComparison(); $("compare-title").focus();});
  $("close-detail").addEventListener("click", () => {state.detail = ""; saveState(); renderDetail(); if (lastDetailButton?.isConnected) lastDetailButton.focus(); else $("reset").focus();});
  addEventListener("popstate", event => {readState(); fillControls(); render(); if (state.detail) renderDetail(true); else { $("main").focus({preventScroll: true}); scrollTo({top: event.state?.scrollY ?? 0, behavior: "auto"}); }});
}
$("retry").addEventListener("click", () => location.reload());
initialize().catch(() => {
  $("mode").textContent = "載入失敗"; $("status").textContent = "未顯示未驗證資料。";
  $("fatal").hidden = false;
  for (const id of ["only-anomaly", "compare-jump", "csv", "json", "selection-download", "clear-selection", "previous", "next", "search", "group", "start", "end", "minimum", "sort", "reset", "direction"]) $(id).disabled = true;
});
