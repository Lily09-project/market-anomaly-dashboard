/**
 * Data loading with integrity verification.
 *
 * Every JSON file is checked against the SHA-256 recorded in manifest.json
 * before it is parsed, so a truncated or tampered deployment fails loudly
 * instead of rendering wrong numbers.
 */
import type { DataFiles, Manifest } from "./types";

export class IntegrityError extends Error {
  constructor(public readonly file: string) {
    super(`資料完整性檢查失敗：${file}`);
    this.name = "IntegrityError";
  }
}

export async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

type Fetcher = (url: string) => Promise<Response>;

export function createLoader(baseUrl: string, fetcher: Fetcher = (url) => fetch(url)) {
  let manifestPromise: Promise<Manifest> | null = null;
  const cache = new Map<string, Promise<unknown>>();
  const verified = new Set<string>();

  const getBytes = async (name: string): Promise<ArrayBuffer> => {
    const response = await fetcher(`${baseUrl}data/${name}`);
    if (!response.ok) throw new Error(`無法載入 ${name}（HTTP ${response.status}）`);
    return response.arrayBuffer();
  };

  const manifest = () => {
    manifestPromise ??= getBytes("manifest.json").then((bytes) => JSON.parse(new TextDecoder().decode(bytes)) as Manifest);
    return manifestPromise;
  };

  async function load<K extends keyof DataFiles>(name: K): Promise<DataFiles[K]> {
    if (!cache.has(name)) {
      const promise = (async () => {
        const [m, bytes] = await Promise.all([manifest(), getBytes(name)]);
        const expected = m.files[name];
        if (!expected || (await sha256Hex(bytes)) !== expected) throw new IntegrityError(name);
        verified.add(name);
        return JSON.parse(new TextDecoder().decode(bytes)) as DataFiles[K];
      })();
      promise.catch(() => cache.delete(name));
      cache.set(name, promise);
    }
    return cache.get(name) as Promise<DataFiles[K]>;
  }

  return { load, manifest, verifiedFiles: () => [...verified].sort() };
}

export type Loader = ReturnType<typeof createLoader>;
