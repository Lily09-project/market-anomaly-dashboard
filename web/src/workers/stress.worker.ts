/// <reference lib="webworker" />
import { blockBootstrap, summarise } from "../lib/stress";
import type { WorkerRequest, WorkerResponse } from "./protocol";

const post = (message: WorkerResponse) => (self as DedicatedWorkerGlobalScope).postMessage(message);

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  const { id, returns, params } = event.data;
  try {
    const paths = blockBootstrap(returns, params, (done) => post({ id, type: "progress", fraction: done / params.paths }));
    post({ id, type: "done", summary: summarise(paths) });
  } catch (error) {
    post({ id, type: "error", message: error instanceof Error ? error.message : String(error) });
  }
};
