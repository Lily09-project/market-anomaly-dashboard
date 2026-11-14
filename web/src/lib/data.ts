/**
 * Data loading with integrity verification.
 *
 * Every JSON file is checked against the SHA-256 recorded in manifest.json
 * before it is parsed, and the manifest must declare the schema version this
 * build reads, so a truncated, tampered or mismatched deployment fails loudly
 * instead of rendering wrong numbers.
 */
import type { DataFiles, Manifest } from "./types";

/** Must equal SCHEMA_VERSION in src/export_web.py (a pytest keeps the two in sync). */
export const DATA_SCHEMA_VERSION = "2.1";

export class IntegrityError extends Error {
  constructor(public readonly file: string) {
    super(`資料完整性檢查失敗：${file}`);
    this.name = "IntegrityError";
  }
}

export class SchemaMismatchError extends Error {
  constructor(public readonly found: string | undefined) {
    super(`資料格式版本不符：網站需要 ${DATA_SCHEMA_VERSION}，部署的資料是 ${found ?? "未知"}`);
    this.name = "SchemaMismatchError";
  }
}

export class DeploymentChangedError extends Error {
  constructor() {
    super("網站資料已更新。請重新整理，讓所有頁面使用同一版本。");
    this.name = "DeploymentChangedError";
  }
}

function sameManifest(a: Manifest, b: Manifest): boolean {
  const files = Object.keys(a.files);
  return a.schema_version === b.schema_version &&
    files.length === Object.keys(b.files).length &&
    files.every((file) => a.files[file] === b.files[file]);
}

function parseJson<T>(name: string, bytes: ArrayBuffer): T {
  try {
    return JSON.parse(new TextDecoder().decode(bytes)) as T;
  } catch {
    throw new Error(`${name} 不是有效的 JSON`);
  }
}

function parseManifest(bytes: ArrayBuffer): Manifest {
  const value = parseJson<unknown>("manifest.json", bytes);
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new IntegrityError("manifest.json");
  }
  const manifest = value as Partial<Manifest>;
  if (typeof manifest.schema_version !== "string" || manifest.files === null ||
      typeof manifest.files !== "object" || Array.isArray(manifest.files)) {
    throw new IntegrityError("manifest.json");
  }
  return manifest as Manifest;
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;

export function createLoader(baseUrl: string, fetcher: Fetcher = (url, init) => fetch(url, init)) {
  let manifestPromise: Promise<Manifest> | null = null;
  const cache = new Map<string, Promise<unknown>>();
  const verified = new Set<string>();
  let deploymentChanged = false;
  const listeners = new Set<() => void>();
  const subscribe = (listener: () => void) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  };
  const requireCurrentDeployment = () => {
    if (deploymentChanged) throw new DeploymentChangedError();
  };

  const getBytes = async (name: string, init?: RequestInit): Promise<ArrayBuffer> => {
    let response: Response;
    try {
      response = await fetcher(`${baseUrl}data/${name}`, init);
    } catch {
      // Browsers reject with an English, engine-specific message ("Failed to fetch").
      throw new Error(`無法載入 ${name}（網路連線失敗）`);
    }
    if (!response.ok) throw new Error(`無法載入 ${name}（HTTP ${response.status}）`);
    return response.arrayBuffer();
  };

  const fetchManifest = (init?: RequestInit) => {
    const promise = getBytes("manifest.json", init).then((bytes) => parseManifest(bytes));
    // A failed manifest load must not be cached forever; the next call retries.
    promise.catch(() => {
      if (manifestPromise === promise) manifestPromise = null;
    });
    manifestPromise = promise;
    return promise;
  };

  const manifest = async () => {
    requireCurrentDeployment();
    const current = await (manifestPromise ?? fetchManifest());
    requireCurrentDeployment();
    return current;
  };

  const matches = async (m: Manifest, name: string, bytes: ArrayBuffer) => {
    const expected = m.files[name];
    return m.schema_version === DATA_SCHEMA_VERSION && Boolean(expected) && (await sha256Hex(bytes)) === expected;
  };

  async function load<K extends keyof DataFiles>(name: K): Promise<DataFiles[K]> {
    requireCurrentDeployment();
    if (!cache.has(name)) {
      const promise = (async () => {
        let [m, bytes] = await Promise.all([manifest(), getBytes(name)]);
        if (!(await matches(m, name, bytes))) {
          // After a redeploy this tab may hold an older manifest (or the HTTP
          // cache an older file); bypass both once before calling it corrupt.
          const [fresh, freshBytes] = await Promise.all([
            getBytes("manifest.json", { cache: "reload" }).then(parseManifest),
            getBytes(name, { cache: "reload" }),
          ]);
          if (m.schema_version === DATA_SCHEMA_VERSION && !sameManifest(m, fresh)) {
            deploymentChanged = true;
            cache.clear();
            verified.clear();
            listeners.forEach((listener) => listener());
            throw new DeploymentChangedError();
          }
          [m, bytes] = [fresh, freshBytes];
          if (m.schema_version !== DATA_SCHEMA_VERSION) throw new SchemaMismatchError(m.schema_version);
          if (!(await matches(m, name, bytes))) throw new IntegrityError(name);
        }
        requireCurrentDeployment();
        const data = parseJson<DataFiles[K]>(name, bytes);
        verified.add(name);
        return data;
      })();
      promise.catch(() => cache.delete(name));
      cache.set(name, promise);
    }
    const data = await (cache.get(name) as Promise<DataFiles[K]>);
    requireCurrentDeployment();
    return data;
  }

  return { load, manifest, subscribe, hasDeploymentChanged: () => deploymentChanged, verifiedFiles: () => [...verified].sort() };
}

export type Loader = ReturnType<typeof createLoader>;
