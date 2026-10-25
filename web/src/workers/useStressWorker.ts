import { useCallback, useEffect, useRef, useState } from "react";
import type { StressSummary } from "../lib/stress";
import type { StressParams } from "../lib/types";
import type { WorkerRequest, WorkerResponse } from "./protocol";

/**
 * Owns one dedicated worker. Cancelling terminates it outright (a busy
 * worker cannot be interrupted any other way); the next run starts a new one.
 */
export function useStressWorker() {
  const worker = useRef<Worker | null>(null);
  const nextId = useRef(1);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const cancel = useCallback(() => {
    worker.current?.terminate();
    worker.current = null;
    setRunning(false);
    setProgress(0);
  }, []);

  useEffect(() => () => worker.current?.terminate(), []);

  const run = useCallback((returns: number[], params: StressParams) => {
    worker.current?.terminate();
    const target = new Worker(new URL("./stress.worker.ts", import.meta.url), { type: "module" });
    worker.current = target;
    const id = nextId.current++;
    setRunning(true);
    setProgress(0);
    setError(null);
    return new Promise<StressSummary>((resolve, reject) => {
      target.onmessage = (event: MessageEvent<WorkerResponse>) => {
        const message = event.data;
        if (message.id !== id) return;
        if (message.type === "progress") {
          setProgress(message.fraction);
          return;
        }
        setRunning(false);
        setProgress(1);
        if (message.type === "error") {
          setError(message.message);
          reject(new Error(message.message));
        } else {
          resolve(message.summary);
        }
      };
      target.postMessage({ id, returns, params } satisfies WorkerRequest);
    });
  }, []);

  return { run, cancel, running, progress, error };
}
