/**
 * Loads an investigation's evidence (GET /investigations/{id}/evidence) and, for
 * photo evidence, the media record whose authorized download_url renders the image.
 */

"use client";

import { useCallback, useEffect, useState } from "react";
import type { Evidence } from "@storeops/contracts";
import { apiClient } from "./api-client";

export interface EvidenceItem {
  evidence: Evidence;
  /** Authorized image URL for photo evidence; null when not a photo or the media could not be read. */
  imageUrl: string | null;
  /** Set when the photo's media record failed to load. */
  imageError: string | null;
}

export interface InvestigationEvidenceState {
  evidenceById: Record<string, EvidenceItem>;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

const MAX_PAGES = 5;

async function listAllEvidence(investigationId: string): Promise<Evidence[]> {
  const items: Evidence[] = [];
  let cursor: string | undefined;
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const res = await apiClient.listEvidence(investigationId, { limit: 100, cursor });
    items.push(...res.items);
    if (!res.next_cursor) break;
    cursor = res.next_cursor;
  }
  return items;
}

function photoMediaId(ev: Evidence): string | null {
  return ev.kind === "PHOTO" ? ev.locator?.media_id ?? null : null;
}

async function resolvePhotoUrls(evidence: Evidence[]): Promise<Map<string, { url: string | null; error: string | null }>> {
  const mediaIds = Array.from(new Set(evidence.map(photoMediaId).filter((id): id is string => Boolean(id))));
  const results = await Promise.allSettled(mediaIds.map((id) => apiClient.getMedia(id)));
  const byMediaId = new Map<string, { url: string | null; error: string | null }>();
  results.forEach((res, i) => {
    if (res.status === "fulfilled") {
      const url = res.value.download_url ?? null;
      byMediaId.set(mediaIds[i], { url, error: url ? null : "Photo is not available for download yet" });
    } else {
      const reason = res.reason instanceof Error ? res.reason.message : "Failed to load photo";
      byMediaId.set(mediaIds[i], { url: null, error: reason });
    }
  });
  return byMediaId;
}

export function useInvestigationEvidence(investigationId: string | null): InvestigationEvidenceState {
  const [evidenceById, setEvidenceById] = useState<Record<string, EvidenceItem>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!investigationId) return;
    let cancelled = false;
    async function load(id: string) {
      setLoading(true);
      setError(null);
      try {
        const evidence = await listAllEvidence(id);
        const photos = await resolvePhotoUrls(evidence);
        if (cancelled) return;
        const next: Record<string, EvidenceItem> = {};
        for (const ev of evidence) {
          const mediaId = photoMediaId(ev);
          const photo = mediaId ? photos.get(mediaId) : undefined;
          next[ev.id] = { evidence: ev, imageUrl: photo?.url ?? null, imageError: photo?.error ?? null };
        }
        setEvidenceById(next);
      } catch (err: unknown) {
        if (cancelled) return;
        console.error("Failed to load investigation evidence:", err);
        setError(err instanceof Error ? err.message : "Failed to load evidence");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load(investigationId);
    return () => {
      cancelled = true;
    };
  }, [investigationId, nonce]);

  return { evidenceById, loading, error, reload };
}
