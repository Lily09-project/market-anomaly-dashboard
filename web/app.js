const $ = id => document.getElementById(id);

const controlPaths = {
  download: ["M12 3v12", "m7 10 5 5 5-5", "M4 16v4h16v-4"],
  reset: ["M3 10a9 9 0 1 1 2 8", "M3 4v6h6"],
  left: ["m14 5-7 7 7 7"], right: ["m10 5 7 7-7 7"],
  sort: ["M8 3v18", "m4 7 4-4 4 4", "M16 21V3", "m12 17 4 4 4-4"],
  compare: ["m12 3 9 5-9 5-9-5 9-5", "m3 12 9 5 9-5", "m3 16 9 5 9-5"],
  close: ["m6 6 12 12", "m6 18 12-12"],
  trash: ["M3 6h18", "M8 6V3h8v3", "M5 6l1 15h12l1-15", "M10 10v7", "M14 10v7"],
  chart: ["M4 3v18h17", "m7 14 4-4 4 3 5-7"],
  alert: ["m12 3 10 18H2L12 3", "M12 9v5", "M12 17h.01"],
  pin:["M12 21s7-7 7-12a7 7 0 0 0-14 0c0 5 7 12 7 12Z","M12 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6"],
  book:["M3 4h6a3 3 0 0 1 3 3v14a3 3 0 0 0-3-3H3Z","M12 7a3 3 0 0 1 3-3h6v14h-6a3 3 0 0 0-3 3"],
  clock:["M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20","M12 6v6l4 2"],bat:["m4 20 5-5","M9 15 18 3l3 3-12 9Z"],
  wave:["M2 12h4l3-7 5 14 3-7h5"],check:["m5 12 4 4L19 6"],tools:["m14 6 4 4","M3 21l10-10"],search:["m21 21-5-5","M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14"],
  wind: ["M3 8h13a3 3 0 1 0-3-3", "M3 12h17", "M3 16h10a3 3 0 1 1-3 3"],
  team: ["m12 3 8 3v6c0 5-8 9-8 9S4 17 4 12V6l8-3", "M8 11h8", "M12 7v9"],
  ball: ["M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18", "M7 5c5 4 5 10 0 14", "M17 5c-5 4-5 10 0 14"],
  code: ["m8 5-6 7 6 7", "m16 5 6 7-6 7"],
};
function controlIcon(name) {
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({viewBox: "0 0 24 24", class: "control-icon", "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor", "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round"})) icon.setAttribute(key, value);
  for (const d of controlPaths[name] || controlPaths.right) {
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d); icon.append(path);
  }
  return icon;
}
function buttonIcon(id, text) {
  return ({csv: "download", json: "download", "selection-download": "download", "snapshot-download": "download",
    reset: "reset", retry: "reset", previous: "left", next: "right", direction: "sort",
    "compare-jump": "compare", "clear-selection": "trash", "close-detail": "close"})[id] ||
    (text === "移除" ? "close" : "right");
}
function setButtonText(node, text) {
  node.replaceChildren(controlIcon(buttonIcon(node.id, text)), el("span", text, {class: "control-label"}));
}
function decorateControls() {
  for (const node of document.querySelectorAll("button")) setButtonText(node, node.textContent);
  const repository = $("repository");
  repository.replaceChildren(controlIcon("code"), el("span", repository.textContent, {class: "control-label"}));
}
let lastAnimatedView, viewAnimation;
function animateView() {
  if (lastAnimatedView === dataset.id) return;
  lastAnimatedView = dataset.id;
  viewAnimation?.cancel();
  const primary = bundle.kind === "aqi" && !$("chart-panel").hidden ? $("chart-panel") : $("table-title").closest("section");
  if (!primary.animate) return;
  viewAnimation = primary.animate([{transform: "translateY(6px)"}, {transform: "translateY(0)"}],
    {duration: bundle.kind === "market" ? 140 : 200, easing: "cubic-bezier(.2,.7,.2,1)"});
}

const el = (tag, text, attrs = {}) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  if (tag === "button" && text !== undefined) setButtonText(node, text);
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
  readProductState();
}
function saveState(push = false) {
  const query = new URLSearchParams();
  productQuery(query);
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
  setButtonText($("direction"), state.descending ? "遞減" : "遞增");
  syncAdvancedFilters();
  $("views").replaceChildren(...bundle.datasets.map(item => {
    const link = el("a", undefined, {href: "?view=" + encodeURIComponent(item.id)});
    const name = ({overview: bundle.kind === "aqi" ? "wind" : "chart", anomaly: "alert", comparison: "compare", teams: "team", batters: "ball", pitchers: "ball", roster: "team", refresh: "reset", history: "reset"})[item.id] || "chart";
    link.append(controlIcon(name), el("span", item.label, {class: "control-label"}));
    if (item.id === dataset.id) link.setAttribute("aria-current", "page");
    link.addEventListener("click", event => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      productState.screen="records";productState.entity="";
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
    (!(productState.entity && productState.screen==="records" && ["aqi","market"].includes(bundle.kind)) || String(row[bundle.kind==="aqi"?"site_name":"symbol"])===productState.entity) &&
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
  $("table-title").textContent = productState.screen==="board" ? (dataset.id==="batters"?"打者成績榜":dataset.id==="pitchers"?"投手成績榜":dataset.label) : dataset.label;
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
  setButtonText($("compare-jump"), "查看比較 · " + rows.length + "/3");
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
  renderMetrics(); renderChart(); renderTable(); renderComparison(); renderDetail(); animateView(); renderProduct();
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
  $("title").textContent = "MARKET / 標的研究"; document.title = $("title").textContent;
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
  renderProduct();
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
  $("direction").addEventListener("click", () => {state.descending = !state.descending; setButtonText($("direction"), state.descending ? "遞減" : "遞增"); saveState(); render();});
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

/* Product routes sit on the verified data engine; legacy ?view links stay usable. */
let productState = {screen:"home", entity:"", research:"history", datum:"", entities:[]};
let productAnimation;
// Stop positional entrance motion before a focused control is scrolled into view.
$("product-root").addEventListener("focusin", () => {
  productAnimation?.cancel();
  productAnimation = null;
});
function readProductState() {
  const q = new URLSearchParams(location.search);
  const routes = ["home","report","stations","research","board","person","team","records","methods","tools"];
  const requested = q.get("screen");
  productState = {
    screen:routes.includes(requested) ? requested : q.has("view") ? "records" : "home",
    entity:(q.get("entity") || "").slice(0,500),
    research:["history","forecast","anomaly","price","volatility"].includes(q.get("research")) ? q.get("research") : bundle.kind==="market" ? "price":"history",
    datum:(q.get("datum") || "").slice(0,500), entities:[]
  };
  if(productState.screen==="board"&&!q.has("sort")&&["batters","pitchers"].includes(dataset.id)){state.sort=dataset.id==="pitchers"?"era":"ops";state.descending=dataset.id!=="pitchers";}
  try {const ids=JSON.parse(q.get("entities")||"[]");if(Array.isArray(ids))productState.entities=[...new Set(ids.filter(x=>typeof x==="string"&&x.length<=500))].slice(0,3);} catch {}
}
function productQuery(query) {
  for(const [key,value] of [["screen",productState.screen],["entity",productState.entity],["research",productState.research],["datum",productState.datum]])if(value)query.set(key,value);
  if(productState.entities.length)query.set("entities",JSON.stringify(productState.entities));
}
function productLink(text, screen, params={}) {
  const q=new URLSearchParams({screen,...params});
  const a=el("a",undefined,{href:"?"+q});
  a.append(controlIcon(({home:bundle.kind==="aqi"?"pin":bundle.kind==="market"?"chart":"team",report:"pin",stations:"compare",research:"chart",board:params.view==="pitchers"?"ball":"bat",person:"team",records:"clock",methods:"book",tools:"tools",team:"team"})[screen]||"right"),el("span",text));
  a.addEventListener("click",event=>{
    if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    event.preventDefault();routeProduct(screen,params);
  });
  if(productState.screen===screen&&(!params.view||params.view===dataset.id))a.setAttribute("aria-current","page");
  return a;
}
function routeProduct(screen, params={}) {
  const primary=["home","report","research"].includes(screen)&&bundle.kind!=="cpbl";
  const next=bundle.datasets.find(x=>x.id===(params.view||(primary||screen==="tools"&&bundle.kind==="market"?"overview":"")));
  const priorPeriod={start:state.start,end:state.end};
  if(next&&next!==dataset){dataset=next;state={view:next.id,search:"",group:"",start:"",end:"",minimum:next.minimum?.value||0,sort:next.sort,descending:true,onlyAnomaly:false,detail:""};selected.clear();currentPage=0;}
  if(next?.date){state.start=priorPeriod.start;state.end=priorPeriod.end;}
  productState={...productState,screen,...Object.fromEntries(Object.entries(params).filter(([key])=>key!=="view"))};
  if(bundle.kind==="cpbl"&&screen==="board"&&!params.sort){state.sort=dataset.id==="pitchers"?"era":dataset.id==="batters"?"ops":dataset.sort;state.descending=dataset.id!=="pitchers";}
  if(params.group!==undefined)state.group=params.group;if(params.detail!==undefined)state.detail=params.detail;
  fillControls();saveState(true);render();$("main").focus({preventScroll:true});scrollTo({top:0,behavior:"auto"});
}
function fieldValue(view,row,key) {return formatField(view.fields.find(f=>f.key===key)||{key},row?.[key]);}
function productValues(view,row) {const dl=el("dl");for(const f of view.fields)dl.append(el("dt",f.label),el("dd",fieldValue(view,row,f.key)));return dl;}
function productButton(text, fn, name="right", cls="") {
  const b=el("button",undefined,{type:"button",class:cls});
  b.append(controlIcon(name),el("span",text));b.addEventListener("click",fn);return b;
}
function sectionTitle(title,subtitle="") {const head=el("div",undefined,{class:"product-heading"});head.append(el("h2",title));if(subtitle)head.append(el("p",subtitle,{class:"metadata"}));return head;}
function latestRow(rows,key){return [...rows].filter(r=>Number.isFinite(chartTime(r[key]))).sort((a,b)=>chartTime(b[key])-chartTime(a[key]))[0];}
function nativeTrend(rows,view,key,secondary=null) {
  const root=el("div",undefined,{class:"native-trend"});
  const sorted=[...rows].filter(r=>Number.isFinite(chartTime(r[view.date]))).sort((a,b)=>chartTime(a[view.date])-chartTime(b[view.date]));
  const keys=[key,secondary].filter(Boolean), valid=sorted.flatMap(r=>keys.map(k=>r[k]).filter(number));
  if(!sorted.length||!valid.length){root.append(el("p","此範圍沒有可繪製的數值。",{class:"empty"}));return root;}
  let lo=Math.min(...valid),hi=Math.max(...valid);if(lo===hi){lo-=Math.max(1,Math.abs(lo)*.05);hi+=Math.max(1,Math.abs(hi)*.05);}
  const first=chartTime(sorted[0][view.date]),last=chartTime(sorted.at(-1)[view.date]);
  const svg=svgEl("svg",{viewBox:"0 0 900 250",role:"img","aria-label":view.fields.find(f=>f.key===key)?.label+"歷史趨勢；完整原始數值見紀錄",preserveAspectRatio:"none"});
  for(const y of [20,115,220])svg.append(svgEl("path",{d:"M10 "+y+"H890",class:"grid"}));
  keys.forEach((k,index)=>{
    // Missing values deliberately break paths; never bridge unknown observations.
    let d="",continues=false;
    for(const r of sorted){if(!number(r[k])){continues=false;continue;}
      const x=10+880*(chartTime(r[view.date])-first)/(last-first||1),y=220-200*(r[k]-lo)/(hi-lo);
      d+=(continues?"L":"M")+x+" "+y+" ";continues=true;
    }
    svg.append(svgEl("path",{d,class:"line series-"+index}));
    if(sorted.length===1&&number(sorted[0][k]))svg.append(svgEl("circle",{cx:10,cy:220-200*(sorted[0][k]-lo)/(hi-lo),r:4,class:"event-point series-"+index}));
  });
  if(productState.research==="anomaly")for(const row of sorted.filter(r=>(r.model_anomaly===1||r.is_anomaly===1)&&number(r[key]))){
    const x=10+880*(chartTime(row[view.date])-first)/(last-first||1),y=220-200*(row[key]-lo)/(hi-lo);
    svg.append(svgEl("path",{d:"M"+x+" "+(y-5)+"l5 9h-10Z",class:"anomaly-point"}));
  }
  const legend=el("div",undefined,{class:"legend"});keys.forEach((k,i)=>legend.append(el("span",view.fields.find(f=>f.key===k)?.label||k,{class:"series-"+i})));
  const axis=el("div",undefined,{class:"axis"});axis.append(el("span",String(sorted[0][view.date])),el("span",fieldValue(view,{[key]:lo},key)+"–"+fieldValue(view,{[key]:hi},key)),el("span",String(sorted.at(-1)[view.date])));
  if(productState.research==="anomaly")legend.append(el("span","三角形：模型標記",{class:"anomaly-legend"}));
  root.append(svg,axis,legend);return root;
}
function productSelect(label, options, value, onChange, id) {
  const wrap=el("label",label);const select=el("select",undefined,{id,"aria-label":label});
  for(const [v,text] of options)select.append(el("option",text,{value:v}));select.value=value;
  select.addEventListener("change",()=>onChange(select.value));wrap.append(select);return wrap;
}
function scopedRows(view,entity,key) {
  const entityRows=view.rows.filter(r=>String(r[key])===entity);const last=view.date?latestRow(entityRows,view.date):null;const cutoff=last?chartTime(last[view.date])-(bundle.kind==="aqi"?86400000:90*86400000):null;
  return entityRows.filter(r=>(state.start||state.end||cutoff===null||chartTime(r[view.date])>=cutoff)&&(!view.date||!state.start||String(r[view.date]).slice(0,10)>=state.start)&&(!view.date||!state.end||String(r[view.date]).slice(0,10)<=state.end));
}
function productPeriod(root){
  const form=el("div",undefined,{class:"product-period"});
  for(const [key,label] of [["start","開始日期"],["end","結束日期"]]){
    const wrap=el("label",label),input=el("input",undefined,{id:"period-"+key,type:"date",value:state[key],"aria-label":"研究"+label});
    input.addEventListener("change",()=>{state[key]=input.value;saveState();renderProduct();$("period-"+key)?.focus({preventScroll:true});});
    wrap.append(input);form.append(wrap);
  }
  form.append(productButton("清除日期",()=>{state.start="";state.end="";saveState();renderProduct();},"reset"));
  root.append(form);if(state.start&&state.end&&state.start>state.end)root.append(el("p","結束日期不能早於開始日期。",{class:"error",role:"alert"}));
}
function renderAirProduct(root) {
  const observations=bundle.datasets.find(v=>v.id==="overview");
  const sites=[...new Set(observations.rows.map(r=>r.site_name))].sort((a,b)=>a.localeCompare(b,"zh-TW"));
  const active=sites.includes(productState.entity)?productState.entity:sites[0];
  if(!productState.entity)productState.entity=active;
  const stationRows=observations.rows.filter(r=>r.site_name===active);
  const current=latestRow(stationRows,"datetime");
  if(productState.screen==="home"||productState.screen==="report") {
    root.append(sectionTitle("先找到測站，再讀懂這次觀測。"));
    const form=el("div",undefined,{class:"place-form"});
    const counties=[...new Set(observations.rows.map(r=>r.county).filter(Boolean))].sort();
    const county=current?.county||counties[0],local=sites.filter(s=>observations.rows.some(r=>r.site_name===s&&r.county===county));
    form.append(productSelect("縣市",counties.map(x=>[x,x]),county,value=>{
      const site=sites.find(s=>observations.rows.some(r=>r.site_name===s&&r.county===value));routeProduct("home",{entity:site||""});
    },"place-county"));
    form.append(productSelect("測站",local.map(x=>[x,x]),active,value=>routeProduct("home",{entity:value}),"place-station"));
    form.append(productButton("開啟報告",()=>routeProduct("report",{entity:active}),"pin","primary"));root.append(form);
    if(productState.screen==="home"){
      const choices=el("div",undefined,{class:"station-options"});
      for(const name of sites)choices.append(productButton(name,()=>routeProduct("report",{entity:name}),"pin"));root.append(choices);return;
    }
    if(!current){root.append(el("p","沒有這個測站的觀測。"));return;}
    const readout=el("section",undefined,{class:"air-report"});
    const values=el("div");values.append(el("p",current.county,{class:"kicker"}),el("h2",active),el("p","示範資料時間 · "+current.datetime,{class:"metadata"}));
    const readings=el("div",undefined,{class:"air-reading"});
    for(const [key,label]of[["aqi","AQI"],["pm25","PM2.5 · μg/m³"]]){const box=el("div");box.append(el("p",label),el("strong",fieldValue(observations,current,key),{class:key==="aqi"?"big":"mid"}));readings.append(box);}
    values.append(readings);
    const actions=el("div",undefined,{class:"surface"});actions.append(el("h3","示範觀測"),el("p","非即時空品或正式預報。"),productLink("比較測站","stations"),productLink("觀測紀錄","records",{view:"overview",entity:active}));
    readout.append(values,actions);root.append(readout);productPeriod(root);
    const tabs=el("div",undefined,{class:"air-tabs"});
    for(const [m,label] of [["history","歷史"],["anomaly","異常紀錄"],["forecast","預測核對"]]){
      const b=productButton(label,()=>routeProduct("report",{research:m,entity:active}),m==="anomaly"?"alert":m==="forecast"?"check":"clock");b.setAttribute("aria-pressed",String(productState.research===m));tabs.append(b);
    }root.append(tabs);
    const id=productState.research==="forecast"?"forecast":productState.research==="anomaly"?"anomaly":"overview";
    const view=bundle.datasets.find(v=>v.id===id),rows=scopedRows(view,active,"site_name");
    root.append(nativeTrend(rows,view,view.value,view.secondary));
    if(id==="forecast")root.append(el("p","歷史留出集的次小時預測核對，不是未來正式預報。",{class:"metadata"}));
    if(id==="anomaly"){const marked=rows.filter(r=>r.is_anomaly===1);root.append(sectionTitle("模型標記紀錄",marked.length?"":"這段期間没有模型標記，不代表沒有風險。"));
      const events=el("ul",undefined,{class:"event-list"});for(const r of marked.slice(-50).reverse()){const li=el("li");li.append(productLink(r.datetime+" · AQI "+format(r.aqi),"records",{view:"anomaly",entity:active,detail:JSON.stringify(view.identity.map(k=>r[k]))}));events.append(li);}root.append(events);}
    root.append(productLink("完整紀錄與下載","records",{view:id,entity:active}));return;
  }
  const view=bundle.datasets.find(v=>v.id==="stations");
  root.append(sectionTitle("測站最新觀測比較","各站顯示自己的資料時間；最多三站，不假定同步觀測。"));
  const chosen=productState.entities.filter(s=>sites.includes(s));
  const form=el("div",undefined,{class:"station-options"});
  for(const site of sites){const selectedSite=chosen.includes(site);const b=productButton((selectedSite?"移除 ":"加入 ")+site,()=>{
    productState.entities=selectedSite?chosen.filter(s=>s!==site):chosen.length<3?[...chosen,site]:chosen;saveState();renderProduct();$("station-pick-"+site)?.focus({preventScroll:true});
  },selectedSite?"close":"compare");b.id="station-pick-"+site;b.disabled=!selectedSite&&chosen.length>=3;form.append(b);}root.append(form);
  const grid=el("div",undefined,{class:"comparison"});
  for(const site of chosen){const row=view.rows.find(r=>r.site_name===site);if(row){const card=el("article");card.append(el("h3",site),productValues(view,row));grid.append(card);}}
  root.append(grid);if(!chosen.length)root.append(el("p","請選取要比較的測站。"));
}
function renderMarketProduct(root) {
  const overview=bundle.datasets.find(v=>v.id==="overview"),symbols=[...new Set(overview.rows.map(r=>r.symbol))].sort();
  const symbol=symbols.includes(productState.entity)?productState.entity:symbols[0];if(!productState.entity)productState.entity=symbol;
  const frame=el("div",undefined,{class:"market-frame"}),rail=el("aside",undefined,{class:"market-rail"});
  rail.append(el("h2","研究標的"),productSelect("股票代碼",symbols.map(x=>[x,x]),symbol,value=>routeProduct("research",{entity:value,datum:""}),"instrument"));
  const center=el("section"),side=el("aside",undefined,{class:"market-side"});
  const all=overview.rows.filter(r=>r.symbol===symbol),latest=latestRow(all,"date");
  center.append(el("p",symbol,{class:"kicker"}),sectionTitle("標的研究"));
  if(latest){const amount=el("div",undefined,{class:"market-amount"});amount.append(el("strong",fieldValue(overview,latest,"close"),{class:"mid"}),el("span",fieldValue(overview,latest,"daily_return")+" 日報酬"));center.append(amount,el("p","最新樣本日 "+latest.date,{class:"metadata"}));}
  productPeriod(center);
  const modes=el("div",undefined,{class:"market-modes"});
  for(const [m,label]of[["price","價格"],["volatility","波動"],["anomaly","異常"]]){const b=productButton(label,()=>routeProduct("research",{research:m,entity:symbol}),m==="anomaly"?"alert":m==="volatility"?"wave":"chart");b.setAttribute("aria-pressed",String(productState.research===m));modes.append(b);}center.append(modes);
  const rows=scopedRows(overview,symbol,"symbol"),metric=productState.research==="volatility"?"volatility_20":"close";
  center.append(nativeTrend(rows,overview,metric));if(metric==="volatility_20")center.append(el("p","原始 20 日滾動波動率；未年化。",{class:"metadata"}));
  const visible=productState.research==="anomaly"?rows.filter(r=>r.model_anomaly===1):rows;
  const eventRows=[...visible].sort((a,b)=>b.date.localeCompare(a.date));
  center.append(sectionTitle(productState.research==="anomaly"?"模型標記日期":"日期紀錄"));
  if(!eventRows.length)center.append(el("p","這段期間沒有符合條件的紀錄；模型未標記不代表沒有風險。"));
  const dates=el("div",undefined,{class:"event-list"});
  for(const r of eventRows.slice(0,7)){const b=productButton(r.date+" · "+fieldValue(overview,r,"close"),()=>{productState.datum=r.date;saveState();renderProduct();$("datum-"+r.date)?.focus({preventScroll:true});$("product-feedback").textContent="已選 "+symbol+" "+r.date+" 的紀錄";},"clock");b.id="datum-"+r.date;b.setAttribute("aria-pressed",String(productState.datum===r.date));dates.append(b);}
  center.append(dates,productLink("完整歷史紀錄與下載","records",{view:productState.research==="volatility"?"volatility":productState.research==="anomaly"?"anomaly":"overview",entity:symbol}),productLink("資料工具","tools",{view:"overview",group:productState.entity}));
  const chosen=rows.find(r=>r.date===productState.datum)||latestRow(rows,"date");
  side.append(el("p","所選日期",{class:"kicker"}));
  if(chosen)side.append(el("h2",chosen.date),productValues(overview,chosen));else side.append(el("p","此範圍沒有資料。"));
  side.append(el("p","DEMO · 非即時行情；分析分數不是機率或投資勝率。",{class:"metadata"}));
  frame.append(rail,center,side);root.append(frame);
}
function renderCPBLProduct(root){
  const view=dataset;
  if(productState.screen==="home"){
    const teams=bundle.datasets.find(v=>v.id==="teams"),years=[...new Set(teams.rows.map(r=>r.season))].sort((a,b)=>b-a);
    const season=years.map(String).includes(productState.entity)?Number(productState.entity):years[0];
    root.append(sectionTitle("球隊戰績","快照統計依勝率排序，非官方名次。"),productSelect("球季",years.map(y=>[String(y),String(y)]),String(season),value=>routeProduct("home",{entity:value}),"season"));
    const grid=el("div",undefined,{class:"almanac-grid"}),standings=el("section"),preview=el("section");
    const list=el("ul",undefined,{class:"standings"});
    for(const r of teams.rows.filter(r=>r.season===season).sort((a,b)=>(b.win_pct??-1)-(a.win_pct??-1))){
      const li=el("li");li.append(productLink(r.team,"team",{view:"teams",entity:r.team}),el("span","場次 "+format(r.games)),el("span","勝／敗 "+format(r.wins)+" / "+format(r.losses)),el("strong","勝率 "+fieldValue(teams,r,"win_pct")));list.append(li);
    }standings.append(list);
    for(const [id,key,title]of[["batters","ops","OPS"],["pitchers","era","ERA"]]){
      const d=bundle.datasets.find(v=>v.id===id),eligible=d.rows.filter(r=>number(r[key])&&number(r[d.minimum.key])&&r[d.minimum.key]>=d.minimum.value).sort((a,b)=>id==="pitchers"?a[key]-b[key]:b[key]-a[key]).slice(0,3);
      preview.append(sectionTitle(title,d.minimum.label+" "+d.minimum.value+" · 快照成績排序"),productLink(id==="batters"?"打者榜":"投手榜","board",{view:id}));
      const ol=el("ol",undefined,{class:"rank-preview"});for(const r of eligible){const li=el("li");li.append(productLink(r.player_name,"person",{view:id,entity:r.player_id}),el("small",r.team),el("strong",fieldValue(d,r,key)));ol.append(li);}preview.append(ol);
    }grid.append(standings,preview);root.append(grid);return;
  }
  if(productState.screen==="team"){
    const teams=bundle.datasets.find(v=>v.id==="teams");root.append(sectionTitle(productState.entity));
    for(const r of teams.rows.filter(r=>r.team===productState.entity))root.append(productValues(teams,r));
    root.append(productLink("打者名單","board",{view:"batters",entity:productState.entity,group:productState.entity}),productLink("投手名單","board",{view:"pitchers",entity:productState.entity,group:productState.entity}),productLink("完整球員名單","records",{view:"roster",group:productState.entity}));return;
  }
  const person=view.rows.find(r=>r.player_id===productState.entity);
  root.append(sectionTitle(person?.player_name||"找不到球員"));
  if(!person){root.append(productLink("返回成績榜","board",{view:view.id}));return;}
  root.append(el("p",person.team),el("p","發布快照 · "+bundle.source.range,{class:"metadata"}),productValues(view,person));
  if(/^\d{10}$/u.test(person.player_id||""))root.append(el("a","CPBL 官方球員頁",{href:"https://www.cpbl.com.tw/team/person?acnt="+person.player_id,rel:"noopener noreferrer"}));
  root.append(productLink("返回成績榜","board",{view:view.id}));
  const id=JSON.stringify(view.identity.map(k=>person[k])),picked=selected.has(id);
  root.append(productButton(picked?"移出比較":"加入比較",()=>{if(picked)selected.delete(id);else if(selected.size<3)selected.add(id);saveState();renderComparison();renderProduct();},"compare"));
  root.append(productLink("比較已選紀錄","records",{view:view.id}));
}
function renderProduct() {
  if(!bundle)return;
  document.documentElement.dataset.screen=productState.screen;
  const screen=productState.screen,record=screen==="records"||screen==="board"||screen==="methods"||screen==="tools";
  $("record-browser").hidden=!record;$("product-root").hidden=record;
  $("snapshot-panel").hidden=!(bundle.kind==="market"&&(screen==="tools"||screen==="records"));
  $("product-nav").replaceChildren(...(bundle.kind==="aqi"?[productLink("查測站","home"),productLink("測站比較","stations"),productLink("資料與方法","methods",{view:"metrics"})]:
    bundle.kind==="market"?[productLink("標的研究","research"),productLink("資料與方法","methods",{view:"metrics"}),productLink("資料工具","tools",{view:"overview",group:productState.entity})]:
    [productLink("球隊戰績","home"),productLink("打者榜","board",{view:"batters"}),productLink("投手榜","board",{view:"pitchers"}),productLink("球員搜尋","records",{view:"roster"}),productLink("資料版本","methods",{view:"history"})]));
  const root=$("product-root");root.replaceChildren();
  if(!record){
    if(bundle.kind==="aqi")renderAirProduct(root);else if(bundle.kind==="market")renderMarketProduct(root);else renderCPBLProduct(root);
    productAnimation?.cancel();productAnimation=root.animate([{opacity:.8,transform:"translateY(5px)"},{opacity:1,transform:"translateY(0)"}],{duration:200,easing:"cubic-bezier(.2,.8,.2,1)"});
  }
  $("metrics").closest(".engine-summary").hidden=screen!=="records";
  $("chart-panel").hidden=screen==="board"||screen==="tools"||dataset.id==="metrics";
  $("views").hidden=screen!=="records";
  $("product-feedback").textContent="";
}

$("retry").addEventListener("click", () => location.reload());
decorateControls();
initialize().catch(() => {
  $("mode").textContent = "載入失敗"; $("status").textContent = "未顯示未驗證資料。";
  $("fatal").hidden = false;
  for (const id of ["only-anomaly", "compare-jump", "csv", "json", "selection-download", "clear-selection", "previous", "next", "search", "group", "start", "end", "minimum", "sort", "reset", "direction"]) $(id).disabled = true;
});
