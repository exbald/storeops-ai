/**
 * Agreement PDF upload flow (initMedia -> PUT bytes -> completeMedia).
 * Agreement media is workspace-level: store, visit, product, zone and capture time are null.
 */

import type { Media } from "@storeops/contracts";
import { apiClient } from "../../lib/api-client";

export const AGREEMENT_MIME = "application/pdf";
export const MAX_AGREEMENT_BYTES = 10 * 1024 * 1024;
export const SAMPLE_AGREEMENT_PATH = "/samples/aquapure_agreement.pdf";
export const SAMPLE_AGREEMENT_FILENAME = "aquapure_agreement.pdf";

/** Returns an error message for an unusable file, or null when the file can be uploaded. */
export function validateAgreementFile(file: File): string | null {
  const looksLikePdf = file.type === AGREEMENT_MIME || file.name.toLowerCase().endsWith(".pdf");
  if (!looksLikePdf) return "The agreement must be a PDF file.";
  if (file.size === 0) return "The selected PDF is empty.";
  if (file.size > MAX_AGREEMENT_BYTES) return "The agreement PDF must be 10 MB or smaller.";
  return null;
}

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Uploads a PDF as AGREEMENT media and returns the completed media record. Throws on any failure. */
export async function uploadAgreementPdf(file: File): Promise<Media> {
  const invalid = validateAgreementFile(file);
  if (invalid) throw new Error(invalid);

  const buffer = await file.arrayBuffer();
  const sha256 = await sha256Hex(buffer);

  const init = await apiClient.initMedia({
    kind: "AGREEMENT",
    filename: file.name,
    mime_type: AGREEMENT_MIME,
    byte_size: file.size,
    sha256,
    store_id: null,
    visit_id: null,
    product_id: null,
    zone_id: null,
    zone_kind: null,
    captured_at: null,
  });

  // Test doubles hand out a placeholder upload URL; only the live API receives bytes.
  if (!apiClient.useDoubles) {
    const res = await fetch(init.upload_url, {
      method: init.method || "PUT",
      headers: { "Content-Type": AGREEMENT_MIME, ...init.headers },
      body: buffer,
    });
    if (!res.ok) {
      throw new Error(`Agreement upload failed with status ${res.status}: ${res.statusText}`);
    }
  }

  const completed = await apiClient.completeMedia(init.media.id, {
    expected_version: init.media.version,
  });
  if (completed.status !== "READY") {
    const reason = completed.rejection ? `: ${completed.rejection.message}` : "";
    throw new Error(`The agreement was not accepted (status ${completed.status})${reason}`);
  }
  return completed;
}

/** Loads the bundled sample agreement so people can try extraction without their own file. */
export async function loadSampleAgreement(): Promise<File> {
  const res = await fetch(SAMPLE_AGREEMENT_PATH);
  if (!res.ok) throw new Error(`Could not load the sample agreement (status ${res.status}).`);
  const blob = await res.blob();
  return new File([blob], SAMPLE_AGREEMENT_FILENAME, { type: AGREEMENT_MIME });
}
