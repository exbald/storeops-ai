"use client";

import React from "react";
import type { Job, JobEvent } from "@storeops/contracts";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

export interface ExtractionPanelProps {
  canExtract: boolean;
  disabledReason: string | null;
  hasProposals: boolean;
  isStarting: boolean;
  job: Job | null;
  events: JobEvent[];
  error: string | null;
  onExtract: () => void;
}

function jobVariant(status: Job["status"]) {
  if (status === "SUCCEEDED") return "success" as const;
  if (status === "FAILED") return "danger" as const;
  return "info" as const;
}

export function ExtractionPanel({
  canExtract,
  disabledReason,
  hasProposals,
  isStarting,
  job,
  events,
  error,
  onExtract,
}: ExtractionPanelProps) {
  const isRunning = Boolean(job && job.status !== "SUCCEEDED" && job.status !== "FAILED");

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm" aria-labelledby="extract-heading">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 id="extract-heading" className="text-lg font-semibold text-gray-900">
            Proposed rules
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Gemini proposes rules from the agreement. Nothing applies until you approve it.
          </p>
        </div>
        <Button onClick={onExtract} disabled={!canExtract || isRunning} isLoading={isStarting}>
          {hasProposals ? "Extract rules again" : "Extract rules with Gemini"}
        </Button>
      </div>

      {!canExtract && disabledReason && <p className="mt-2 text-xs text-gray-500">{disabledReason}</p>}

      {job && (
        <div className="mt-4 rounded border border-gray-200 bg-gray-50 p-3" role="status" aria-live="polite">
          <div className="flex items-center gap-2 text-sm">
            <span className="font-medium text-gray-800">Extraction</span>
            <Badge variant={jobVariant(job.status)} labelPrefix="Extraction status:">
              {job.status}
            </Badge>
            {job.stage && <span className="text-xs text-gray-500">Stage: {job.stage}</span>}
          </div>
          {events.length > 0 && (
            <ol className="mt-2 space-y-1 text-xs text-gray-700" data-testid="extraction-events">
              {events.map((ev) => (
                <li key={ev.sequence}>
                  <span className="font-mono text-gray-500">{ev.stage}</span> &mdash; {ev.summary}
                </li>
              ))}
            </ol>
          )}
          {job.status === "FAILED" && job.error && (
            <p className="mt-2 text-sm text-red-700">Extraction failed: {job.error.message}</p>
          )}
        </div>
      )}

      {error && (
        <div role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
    </section>
  );
}
