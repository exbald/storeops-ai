/**
 * Shared shelf-photo upload flow (init -> PUT bytes -> complete) used by the
 * visit and investigation screens, plus loaders for the bundled sample photos.
 *
 * Every step throws on failure; callers surface the error to the user.
 */

import type { Media } from "@storeops/contracts";
import { apiClient } from "./api-client";

export type PhotoKind = "VISIT_BEFORE" | "VISIT_AFTER";
export type ZoneKind = "SHELF" | "DISPLAY";
type UploadMime = "image/jpeg" | "image/png" | "application/pdf" | "text/csv";

export interface PhotoUploadTarget {
  kind: PhotoKind;
  storeId: string;
  visitId: string;
  zoneId: string;
  zoneKind: ZoneKind;
}

export interface SamplePhoto {
  path: string;
  filename: string;
}

export const SAMPLE_PHOTOS = {
  before: { path: "/samples/shelf_before.jpg", filename: "shelf_before.jpg" },
  afterFixed: { path: "/samples/shelf_after.jpg", filename: "shelf_after.jpg" },
  afterNotFixed: { path: "/samples/shelf_after_fail.jpg", filename: "shelf_after_fail.jpg" },
} as const satisfies Record<string, SamplePhoto>;

export async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function resolveMimeType(fileType: string): UploadMime {
  if (fileType === "image/png") return "image/png";
  if (fileType === "application/pdf") return "application/pdf";
  if (fileType === "text/csv") return "text/csv";
  return "image/jpeg";
}

/**
 * Uploads one photo bound to the given visit/store/zone. captured_at is stamped
 * at call time because the API rejects after-photos older than 30 minutes.
 */
export async function uploadVisitPhoto(file: File, target: PhotoUploadTarget): Promise<Media> {
  const mimeType = resolveMimeType(file.type);
  const sha256 = await sha256Hex(await file.arrayBuffer());

  const initResp = await apiClient.initMedia({
    kind: target.kind,
    filename: file.name,
    mime_type: mimeType,
    byte_size: file.size,
    sha256,
    store_id: target.storeId,
    visit_id: target.visitId,
    product_id: null,
    zone_id: target.zoneId,
    zone_kind: target.zoneKind,
    captured_at: new Date().toISOString(),
  });

  if (initResp.upload_url && !apiClient.useDoubles) {
    const uploadRes = await fetch(initResp.upload_url, {
      method: "PUT",
      headers: { "Content-Type": mimeType },
      body: file,
    });
    if (!uploadRes.ok) {
      throw new Error(`Media upload failed with status ${uploadRes.status}: ${uploadRes.statusText}`);
    }
  }

  return apiClient.completeMedia(initResp.media.id, { expected_version: 1 });
}

/** Fetches a bundled sample photo from /public and wraps it as a File. */
export async function loadSampleFile(sample: SamplePhoto): Promise<File> {
  const res = await fetch(sample.path);
  if (!res.ok) {
    throw new Error(`Could not load the sample photo ${sample.filename} (HTTP ${res.status}).`);
  }
  const blob = await res.blob();
  return new File([blob], sample.filename, { type: "image/jpeg" });
}

export async function uploadSamplePhoto(sample: SamplePhoto, target: PhotoUploadTarget): Promise<Media> {
  const file = await loadSampleFile(sample);
  return uploadVisitPhoto(file, target);
}
