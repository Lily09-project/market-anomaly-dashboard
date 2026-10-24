import type { StressSummary } from "../lib/stress";
import type { StressParams } from "../lib/types";

export type WorkerRequest = { id: number; returns: number[]; params: StressParams };

export type WorkerResponse =
  | { id: number; type: "progress"; fraction: number }
  | { id: number; type: "done"; summary: StressSummary }
  | { id: number; type: "error"; message: string };
