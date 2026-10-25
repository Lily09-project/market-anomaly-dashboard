/**
 * Research snapshots: a small, self-verifying JSON record of what was
 * analysed (data fingerprint, parameters) and what came out. The fingerprint
 * is the SHA-256 of the canonical JSON of everything else, so an edited file
 * is rejected on import.
 */
import { sha256Hex } from "./data";

export const SNAPSHOT_KIND = "market-regime-lab/snapshot";
export const SNAPSHOT_VERSION = 1;
export const MAX_SNAPSHOT_BYTES = 64 * 1024;
const MAX_LABEL = 120;

export interface SnapshotResults {
  regime_state: string;
  regime_probability: number;
  regime_accuracy: number | null;
  pbo: number;
  dsr: number;
  walk_forward_sharpe: number;
  event_post_car_3d: number | null;
  var95: number | null;
  cvar95: number | null;
  var99: number | null;
  cvar99: number | null;
}

export interface SnapshotBody {
  kind: typeof SNAPSHOT_KIND;
  version: typeof SNAPSHOT_VERSION;
  label: string;
  data: { input_sha256: string; schema_version: string; range: { start: string; end: string } };
  symbol: string;
  params: { horizon: number | null; block: number | null; paths: number | null; seed: number | null };
  results: SnapshotResults;
}

export interface Snapshot extends SnapshotBody {
  fingerprint: string;
}

/** JSON with object keys sorted at every level and no whitespace. */
export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value !== null && typeof value === "object") {
    const entries = Object.keys(value as Record<string, unknown>)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`);
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value);
}

async function fingerprintOf(body: SnapshotBody): Promise<string> {
  const bytes = new TextEncoder().encode(canonicalJson(body));
  return sha256Hex(bytes.buffer as ArrayBuffer);
}

export async function createSnapshot(body: Omit<SnapshotBody, "kind" | "version">): Promise<Snapshot> {
  const full: SnapshotBody = { kind: SNAPSHOT_KIND, version: SNAPSHOT_VERSION, ...body, label: body.label.slice(0, MAX_LABEL) };
  return { ...full, fingerprint: await fingerprintOf(full) };
}

export type ValidationResult = { ok: true; snapshot: Snapshot } | { ok: false; reason: string };

const isNum = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const isNumOrNull = (v: unknown) => v === null || isNum(v);
const isStr = (v: unknown) => typeof v === "string";

function structureError(value: Record<string, unknown>): string | null {
  const data = value.data as Record<string, unknown> | undefined;
  const params = value.params as Record<string, unknown> | undefined;
  const results = value.results as Record<string, unknown> | undefined;
  const range = data?.range as Record<string, unknown> | undefined;
  const checks: [string, boolean][] = [
    ["label", isStr(value.label) && (value.label as string).length <= MAX_LABEL],
    ["symbol", isStr(value.symbol) && /^[A-Za-z0-9._-]{1,16}$/.test(value.symbol as string)],
    ["data.input_sha256", isStr(data?.input_sha256) && /^[0-9a-f]{64}$/.test(data?.input_sha256 as string)],
    ["data.schema_version", isStr(data?.schema_version)],
    ["data.range", isStr(range?.start) && isStr(range?.end)],
    ["params", !!params && ["horizon", "block", "paths", "seed"].every((k) => isNumOrNull(params[k]))],
    ["results.regime_state", isStr(results?.regime_state)],
    ["results", !!results && ["regime_probability", "pbo", "dsr", "walk_forward_sharpe"].every((k) => isNum(results[k]))],
    [
      "results（可為空的欄位）",
      !!results && ["regime_accuracy", "event_post_car_3d", "var95", "cvar95", "var99", "cvar99"].every((k) => isNumOrNull(results[k])),
    ],
    ["fingerprint", isStr(value.fingerprint) && /^[0-9a-f]{64}$/.test(value.fingerprint as string)],
  ];
  const failed = checks.find(([, ok]) => !ok);
  return failed ? failed[0] : null;
}

/** Parse and verify an uploaded snapshot; every rejection says why. */
export async function validateSnapshot(text: string): Promise<ValidationResult> {
  if (new TextEncoder().encode(text).length > MAX_SNAPSHOT_BYTES) return { ok: false, reason: `檔案超過 ${MAX_SNAPSHOT_BYTES / 1024} KB 上限` };
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { ok: false, reason: "不是有效的 JSON 檔案" };
  }
  if (value === null || typeof value !== "object" || Array.isArray(value)) return { ok: false, reason: "內容不是 JSON 物件" };
  const record = value as Record<string, unknown>;
  if (record.kind !== SNAPSHOT_KIND || record.version !== SNAPSHOT_VERSION) return { ok: false, reason: "不是本工具產生的研究快照（kind／version 不符）" };
  const bad = structureError(record);
  if (bad) return { ok: false, reason: `欄位缺少或型別錯誤：${bad}` };
  const { fingerprint, ...body } = record as unknown as Snapshot;
  const expected = await fingerprintOf(body);
  if (expected !== fingerprint) return { ok: false, reason: "指紋不符：檔案在匯出後被修改過" };
  return { ok: true, snapshot: record as unknown as Snapshot };
}

export const RESULT_LABELS: Record<keyof SnapshotResults, string> = {
  regime_state: "目前市場狀態",
  regime_probability: "狀態機率",
  regime_accuracy: "狀態還原準確率",
  pbo: "回測過度擬合機率（PBO）",
  dsr: "Deflated Sharpe Ratio",
  walk_forward_sharpe: "Walk-forward 樣本外 Sharpe",
  event_post_car_3d: "負向衝擊後 3 日 CAR",
  var95: "VaR 95%",
  cvar95: "CVaR 95%",
  var99: "VaR 99%",
  cvar99: "CVaR 99%",
};

export interface DiffRow {
  key: string;
  label: string;
  a: string | number | null;
  b: string | number | null;
  changed: boolean;
}

export function diffSnapshots(a: Snapshot, b: Snapshot): DiffRow[] {
  const rows: DiffRow[] = [
    { key: "symbol", label: "標的", a: a.symbol, b: b.symbol, changed: a.symbol !== b.symbol },
    { key: "data", label: "資料指紋", a: a.data.input_sha256.slice(0, 12), b: b.data.input_sha256.slice(0, 12), changed: a.data.input_sha256 !== b.data.input_sha256 },
  ];
  for (const key of ["horizon", "block", "paths", "seed"] as const) {
    rows.push({ key: `params.${key}`, label: `參數：${key}`, a: a.params[key], b: b.params[key], changed: a.params[key] !== b.params[key] });
  }
  for (const key of Object.keys(RESULT_LABELS) as (keyof SnapshotResults)[]) {
    rows.push({ key: `results.${key}`, label: RESULT_LABELS[key], a: a.results[key], b: b.results[key], changed: a.results[key] !== b.results[key] });
  }
  return rows;
}
