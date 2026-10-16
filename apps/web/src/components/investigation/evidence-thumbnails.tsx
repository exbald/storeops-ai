"use client";

import React, { useState } from "react";
import type { EvidenceItem } from "../../lib/use-investigation-evidence";

export interface EvidenceThumbnailsProps {
  evidenceIds: string[];
  evidenceById: Record<string, EvidenceItem>;
  loading: boolean;
}

const KIND_LABELS: Record<string, string> = {
  PHOTO: "Photo",
  PDF: "Agreement",
  SALES_ROWS: "Sales data",
  STOCK_ROWS: "Stock data",
  VISIT_NOTE: "Visit note",
  POLICY: "Policy",
  METRIC: "Metric",
  HUMAN: "Rep input",
  CATALOG: "Catalog",
};

function PhotoThumb({ url, summary }: { url: string; summary: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <span title={summary} className="block max-w-xs text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded px-2 py-1">
        <span className="font-semibold">Photo:</span> {summary} (image could not be displayed)
      </span>
    );
  }
  return (
    <a href={url} target="_blank" rel="noopener noreferrer" title={summary} className="block">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt={summary}
        onError={() => setFailed(true)}
        className="h-20 w-28 object-cover rounded border border-gray-200 hover:ring-2 hover:ring-blue-500"
        loading="lazy"
      />
    </a>
  );
}

/** Cited evidence for one claim, check or action: photo thumbnails plus labelled source chips. */
export function EvidenceThumbnails({ evidenceIds, evidenceById, loading }: EvidenceThumbnailsProps) {
  if (evidenceIds.length === 0) return null;
  if (loading && Object.keys(evidenceById).length === 0) {
    return <div className="h-16 w-24 rounded bg-gray-200 animate-pulse" aria-label="Loading evidence" />;
  }

  return (
    <ul className="flex flex-wrap gap-2" aria-label="Cited evidence">
      {evidenceIds.map((id) => {
        const item = evidenceById[id];
        if (!item) {
          return (
            <li key={id} className="text-xs text-gray-500 bg-gray-100 border border-gray-200 rounded px-2 py-1">
              Evidence {id.slice(0, 8)}
            </li>
          );
        }
        const { evidence, imageUrl, imageError } = item;
        if (evidence.kind === "PHOTO" && imageUrl) {
          return (
            <li key={id}>
              <PhotoThumb url={imageUrl} summary={evidence.summary} />
            </li>
          );
        }
        return (
          <li
            key={id}
            title={imageError ?? evidence.summary}
            className="max-w-xs text-xs bg-blue-50 border border-blue-100 text-blue-900 rounded px-2 py-1"
          >
            <span className="font-semibold">{KIND_LABELS[evidence.kind] ?? evidence.kind}:</span>{" "}
            <span className="line-clamp-2">{imageError ? `Photo unavailable (${imageError})` : evidence.summary}</span>
          </li>
        );
      })}
    </ul>
  );
}
