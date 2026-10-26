import { useCallback, useEffect, useRef, useState } from "react";
import type { StressSummary } from "../lib/stress";
import type { StressParams } from "../lib/types";
import type { WorkerRequest, WorkerResponse } from "./protocol";

/** Every run owns its worker, listeners and one settled promise. */
export function useStressWorker() {
  const pending = useRef<(() => void) | null>(null);
  const nextId = useRef(1);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const cancel = useCallback(() => {
    pending.current?.();
    setRunning(false);
    setProgress(0);
  }, []);
  useEffect(() => () => pending.current?.(), []);

  const run = useCallback((returns: number[], params: StressParams) => {
    pending.current?.();
    const id = nextId.current++;
    setRunning(true);
    setProgress(0);
    setError(null);
    return new Promise<StressSummary>((resolve, reject) => {
      let target: Worker | null = null;
      const owns = () => pending.current === abort;
      const dispose = () => {
        target?.removeEventListener("message", onMessage);
        target?.removeEventListener("error", onFailure);
        target?.removeEventListener("messageerror", onFailure);
        target?.terminate();
        if (owns()) pending.current = null;
      };
      const abort = () => {
        if (!owns()) return;
        dispose();
        reject(new DOMException("Cancelled", "AbortError"));
      };
      const fail = (cause: unknown) => {
        if (!owns()) return;
        const failure = cause instanceof Error ? cause : new Error("計算工作無法執行，請重新開始。");
        dispose();
        setRunning(false);
        setProgress(0);
        setError(failure.message);
        reject(failure);
      };
      const onFailure = (event: Event) => {
        event.preventDefault();
        fail(new Error("計算工作無法執行，請重新開始。"));
      };
      const onMessage = (event: MessageEvent<WorkerResponse>) => {
        if (!owns()) return;
        const message = event.data;
        if (message.id !== id) return;
        if (message.type === "progress") {
          setProgress(message.fraction);
          return;
        }
        if (message.type === "error") {
          fail(new Error(message.message));
          return;
        }
        dispose();
        setRunning(false);
        setProgress(1);
        resolve(message.summary);
      };
      pending.current = abort;
      try {
        target = new Worker(new URL("./stress.worker.ts", import.meta.url), { type: "module" });
        target.addEventListener("message", onMessage);
        target.addEventListener("error", onFailure);
        target.addEventListener("messageerror", onFailure);
        target.postMessage({ id, returns, params } satisfies WorkerRequest);
      } catch (cause) {
        fail(cause);
      }
    });
  }, []);

  return { run, cancel, running, progress, error };
}
