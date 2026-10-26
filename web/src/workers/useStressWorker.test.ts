import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useStressWorker } from "./useStressWorker";

class ControlledWorker extends EventTarget {
  static instances: ControlledWorker[] = [];
  static failConstruction = false;
  static failPost = false;
  request: { id: number } = { id: 0 };
  terminated = false;
  onmessage: ((event: MessageEvent) => void) | null = null;
  constructor() {
    super();
    if (ControlledWorker.failConstruction) throw new Error("worker construction failed");
    ControlledWorker.instances.push(this);
  }
  postMessage(request: { id: number }) {
    if (ControlledWorker.failPost) throw new Error("worker post failed");
    this.request = request;
  }
  terminate() { this.terminated = true; }
  deliver(data: object) {
    // Queued messages can arrive after terminate; test ownership rather than mock suppression.
    const event = new MessageEvent("message", { data });
    this.dispatchEvent(event);
    this.onmessage?.(event);
  }
}
const latest = () => ControlledWorker.instances.at(-1)!;
const completed = (worker: ControlledWorker) => ({ id: worker.request.id, type: "done", summary: { var95: 0.2 } });
const start = (run: ReturnType<typeof useStressWorker>["run"]) => run([0.01, -0.02], { horizon: 20, paths: 500, block: 2, seed: 1 });

describe("worker ownership and failure recovery", () => {
  beforeEach(() => {
    ControlledWorker.instances = [];
    ControlledWorker.failConstruction = false;
    ControlledWorker.failPost = false;
    vi.stubGlobal("Worker", ControlledWorker);
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

  it("settles every cancellation and can restart repeatedly", async () => {
    const { result } = renderHook(() => useStressWorker());
    for (let i = 0; i < 20; i += 1) {
      let outcome = "";
      act(() => { start(result.current.run).then(() => { outcome = "done"; }, (e: Error) => { outcome = e.name; }); });
      const old = latest();
      act(() => result.current.cancel());
      await act(async () => { await Promise.resolve(); });
      expect(outcome).toBe("AbortError");
      expect(old.terminated).toBe(true);
      act(() => old.deliver(completed(old)));
      expect(result.current.running).toBe(false);
      expect(result.current.error).toBeNull();
    }
  });

  it("rejects a superseded run and ignores its late progress and result", async () => {
    const { result } = renderHook(() => useStressWorker());
    let first = "", second = "";
    act(() => { start(result.current.run).then(() => { first = "done"; }, (e: Error) => { first = e.name; }); });
    const old = latest();
    const oldId = old.request.id;
    act(() => { start(result.current.run).then(() => { second = "done"; }, (e: Error) => { second = e.name; }); });
    const current = latest();
    await act(async () => { await Promise.resolve(); });
    expect(first).toBe("AbortError");
    act(() => {
      old.deliver({ id: oldId, type: "progress", fraction: 0.9 });
      old.deliver({ ...completed(old), id: oldId });
    });
    expect(second).toBe("");
    expect(result.current.progress).toBe(0);
    await act(async () => { current.deliver(completed(current)); await Promise.resolve(); });
    expect(second).toBe("done");
  });

  it("settles on unmount without applying queued work", async () => {
    const { result, unmount } = renderHook(() => useStressWorker());
    let outcome = "";
    act(() => { start(result.current.run).then(() => { outcome = "done"; }, (e: Error) => { outcome = e.name; }); });
    const old = latest();
    unmount();
    await act(async () => { await Promise.resolve(); });
    expect(outcome).toBe("AbortError");
    old.deliver(completed(old));
    expect(old.terminated).toBe(true);
  });

  it.each(["error", "messageerror"])("recovers from native %s events", async (kind) => {
    const { result } = renderHook(() => useStressWorker());
    let outcome = "";
    act(() => { start(result.current.run).then(() => { outcome = "done"; }, (e: Error) => { outcome = e.name; }); });
    const failed = latest();
    await act(async () => { failed.dispatchEvent(new Event(kind, { cancelable: true })); await Promise.resolve(); });
    expect(outcome).toBe("Error");
    expect(result.current.running).toBe(false);
    expect(result.current.error).toBeTruthy();
    expect(failed.terminated).toBe(true);
    act(() => { start(result.current.run).then(() => { outcome = "recovered"; }, () => { outcome = "failed"; }); });
    await act(async () => { latest().deliver(completed(latest())); await Promise.resolve(); });
    expect(outcome).toBe("recovered");
    expect(result.current.error).toBeNull();
  });

  it.each(["construction", "post"])("clears busy state after synchronous %s failure", async (kind) => {
    const { result } = renderHook(() => useStressWorker());
    ControlledWorker.failConstruction = kind === "construction";
    ControlledWorker.failPost = kind === "post";
    let outcome = "";
    await act(async () => {
      try { await start(result.current.run); } catch { outcome = "rejected"; }
    });
    expect(outcome).toBe("rejected");
    expect(result.current.running).toBe(false);
    expect(result.current.error).toBeTruthy();
  });
});
