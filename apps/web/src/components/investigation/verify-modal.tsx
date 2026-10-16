"use client";

import React, { useEffect, useState } from "react";
import type { Investigation, Job, Media } from "@storeops/contracts";
import { apiClient, VersionConflictError } from "../../lib/api-client";
import {
  SAMPLE_PHOTOS,
  uploadSamplePhoto,
  uploadVisitPhoto,
  type PhotoUploadTarget,
  type SamplePhoto,
} from "../../lib/media-upload";
import { Modal } from "../ui/modal";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

export interface VerifyModalProps {
  isOpen: boolean;
  onClose: () => void;
  investigation: Investigation;
  onSubmitted: (job: Job) => void;
  onConflict: () => Promise<void>;
}

/** Default zone for after-photos: the first zone the action plan names. */
export function defaultAfterZone(investigation: Investigation): string {
  const zone = investigation.actions.flatMap((a) => a.required_zone_ids)[0];
  return zone || "shelf-main";
}

export function VerifyModal({ isOpen, onClose, investigation, onSubmitted, onConflict }: VerifyModalProps) {
  const [zoneId, setZoneId] = useState(() => defaultAfterZone(investigation));
  const [afterMedia, setAfterMedia] = useState<Media[]>([]);
  const [uploadingLabel, setUploadingLabel] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setZoneId(defaultAfterZone(investigation));
  }, [investigation.id]);

  const target = (): PhotoUploadTarget => {
    if (investigation.workspace_id) apiClient.setWorkspaceId(investigation.workspace_id);
    return {
      kind: "VISIT_AFTER",
      storeId: investigation.store_id,
      visitId: investigation.visit_id,
      zoneId: zoneId.trim() || defaultAfterZone(investigation),
      zoneKind: "SHELF",
    };
  };

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadingLabel("Uploading…");
    setError(null);
    try {
      const media = await uploadVisitPhoto(file, target());
      setAfterMedia((prev) => [media, ...prev]);
    } catch (err: unknown) {
      console.error("After photo upload error:", err);
      setError(err instanceof Error ? err.message : "Failed to upload after photo");
    } finally {
      setUploadingLabel(null);
      e.target.value = "";
    }
  };

  // A sample replaces the current selection so the verification checks exactly that photo.
  const handleSample = async (sample: SamplePhoto, label: string) => {
    setUploadingLabel(label);
    setError(null);
    try {
      const media = await uploadSamplePhoto(sample, target());
      setAfterMedia([media]);
    } catch (err: unknown) {
      console.error("Sample after photo upload error:", err);
      setError(err instanceof Error ? err.message : "Failed to upload sample photo");
    } finally {
      setUploadingLabel(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (afterMedia.length === 0) {
      setError("Add at least one after photo of the shelf first.");
      return;
    }
    if (investigation.workspace_id) apiClient.setWorkspaceId(investigation.workspace_id);
    setIsSubmitting(true);
    setError(null);
    try {
      const job = await apiClient.verifyInvestigation(investigation.id, {
        expected_version: investigation.version,
        after_media_ids: afterMedia.map((m) => m.id),
      });
      setAfterMedia([]);
      onSubmitted(job);
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setError("This investigation changed while you were working. Refreshing…");
        await onConflict();
      } else {
        setError(err instanceof Error ? err.message : "Failed to start verification");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const busy = uploadingLabel !== null;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Verify the fix">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-gray-600">
          Add a new photo of the shelf taken after the fix. StoreOps checks it against every rule in the approved
          agreement. Photos must be taken in the last 30 minutes and differ from the before photo.
        </p>

        {error && (
          <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
            {error}
          </div>
        )}

        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200 space-y-2">
          <p className="text-xs font-semibold text-blue-900 uppercase tracking-wider">No shelf nearby? Use a sample</p>
          <div className="flex flex-col sm:flex-row gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => handleSample(SAMPLE_PHOTOS.afterNotFixed, "Uploading sample…")}
            >
              Use sample photo: still not fixed
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() => handleSample(SAMPLE_PHOTOS.afterFixed, "Uploading sample…")}
            >
              Use sample photo: fixed
            </Button>
          </div>
        </div>

        <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
            <div className="w-full sm:w-44">
              <label className="sr-only" htmlFor="after-zone-id">
                Shelf zone
              </label>
              <Input
                id="after-zone-id"
                type="text"
                value={zoneId}
                onChange={(e) => setZoneId(e.target.value)}
                placeholder="Zone (e.g. ZONE-BEV-01)"
              />
            </div>
            <label className="cursor-pointer">
              <input type="file" accept="image/jpeg,image/png" className="hidden" onChange={handleFile} disabled={busy} />
              <span className="inline-flex items-center px-2.5 py-1.5 text-xs font-medium rounded-md border border-gray-300 bg-white text-gray-700 hover:bg-gray-50">
                Upload my own photo
              </span>
            </label>
          </div>

          {uploadingLabel && <p className="text-xs text-gray-600 animate-pulse">{uploadingLabel}</p>}

          {afterMedia.length > 0 && (
            <ul className="divide-y divide-gray-200 pt-1" aria-label="Selected after photos">
              {afterMedia.map((m) => (
                <li key={m.id} className="py-1 text-xs text-gray-700 flex justify-between">
                  <span>{m.filename}</span>
                  <span className="text-green-600 font-bold">Selected</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
          <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button type="submit" disabled={isSubmitting || busy || afterMedia.length === 0}>
            {isSubmitting ? "Starting verification…" : "Run AI verification"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
