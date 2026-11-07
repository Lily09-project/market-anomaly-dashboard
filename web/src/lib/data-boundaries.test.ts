import { describe, expect, it } from "vitest";
import { createLoader, sha256Hex } from "./data";

const body = '{"items":[]}';
const respond = (value: string) => new Response(new TextEncoder().encode(value));

describe("deployment data boundaries", () => {
  it("rejects a foreign schema even when the content hash matches", async () => {
    const digest = await sha256Hex(new TextEncoder().encode(body).buffer as ArrayBuffer);
    const loader = createLoader("./", async (url) => respond(
      url.endsWith("manifest.json")
        ? JSON.stringify({ schema_version: "incompatible", files: { "overview.json": digest } })
        : body,
    ));
    await expect(loader.load("overview.json")).rejects.toThrow("資料格式版本不符");
    expect(loader.verifiedFiles()).toEqual([]);
  });

  it("does not mark a hash-matched but invalid JSON file as verified", async () => {
    const invalid = "{";
    const digest = await sha256Hex(new TextEncoder().encode(invalid).buffer as ArrayBuffer);
    let payload = invalid;
    const loader = createLoader("./", async (url) => respond(
      url.endsWith("manifest.json")
        ? JSON.stringify({ schema_version: "2.1", files: { "overview.json": digest } })
        : payload,
    ));
    await expect(loader.load("overview.json")).rejects.toThrow();
    expect(loader.verifiedFiles()).toEqual([]);
    payload = body;
    await expect(loader.load("overview.json")).rejects.toThrow();
  });

  it.each(["null", "[]", "{}", '{"files":null}'])("rejects a malformed manifest and allows a later retry: %s", async (invalid) => {
    const digest = await sha256Hex(new TextEncoder().encode(body).buffer as ArrayBuffer);
    let broken = true;
    const loader = createLoader("./", async (url) => respond(
      url.endsWith("manifest.json")
        ? broken ? invalid : JSON.stringify({ schema_version: "2.1", files: { "overview.json": digest } })
        : body,
    ));
    await expect(loader.load("overview.json")).rejects.toThrow("manifest.json");
    expect(loader.verifiedFiles()).toEqual([]);
    broken = false;
    await expect(loader.load("overview.json")).resolves.toEqual({ items: [] });
  });
});
