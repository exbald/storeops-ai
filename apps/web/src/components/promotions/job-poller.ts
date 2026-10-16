/**
 * Polls GET /jobs/{id} and GET /jobs/{id}/events until the job reaches a terminal status.
 */

import type { Job, JobEvent } from "@storeops/contracts";
import { apiClient } from "../../lib/api-client";

export const TERMINAL_JOB_STATUSES: ReadonlyArray<Job["status"]> = ["SUCCEEDED", "FAILED"];

export function isTerminalJob(job: Job): boolean {
  return TERMINAL_JOB_STATUSES.includes(job.status);
}

export interface PollJobOptions {
  intervalMs?: number;
  /** Stops polling and rejects once the caller no longer needs the result (e.g. unmount). */
  isCancelled?: () => boolean;
  onUpdate?: (job: Job, events: JobEvent[]) => void;
}

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function pollJobUntilTerminal(jobId: string, options: PollJobOptions = {}): Promise<Job> {
  const { intervalMs = 1500, isCancelled = () => false, onUpdate } = options;
  for (;;) {
    if (isCancelled()) throw new Error("Job polling was cancelled.");
    const [job, events] = await Promise.all([apiClient.getJob(jobId), apiClient.getJobEvents(jobId)]);
    onUpdate?.(job, events.items);
    if (isTerminalJob(job)) return job;
    await wait(intervalMs);
  }
}
