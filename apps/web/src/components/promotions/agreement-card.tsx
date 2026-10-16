"use client";

import React, { useState } from "react";
import type { Media } from "@storeops/contracts";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { AgreementFilePicker } from "./agreement-file-picker";

export interface AgreementCardProps {
  media: Media | null;
  mediaError: string | null;
  canEdit: boolean;
  isUploading: boolean;
  uploadError: string | null;
  onUpload: (file: File) => void;
}

function statusVariant(status: Media["status"]) {
  if (status === "READY") return "success" as const;
  if (status === "REJECTED") return "danger" as const;
  return "warning" as const;
}

export function AgreementCard({ media, mediaError, canEdit, isUploading, uploadError, onUpload }: AgreementCardProps) {
  const [isReplacing, setIsReplacing] = useState(false);
  const [pickError, setPickError] = useState<string | null>(null);
  const showPicker = canEdit && (!media || isReplacing);

  const handleSelect = (file: File) => {
    setPickError(null);
    setIsReplacing(false);
    onUpload(file);
  };

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm" aria-labelledby="agreement-heading">
      <h2 id="agreement-heading" className="text-lg font-semibold text-gray-900">
        Vendor agreement
      </h2>
      <p className="mt-1 text-sm text-gray-500">The signed PDF that Gemini reads to propose shelf rules.</p>

      {mediaError && (
        <div role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Could not load the agreement file: {mediaError}
        </div>
      )}

      {media && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <span className="font-medium text-gray-900">{media.filename}</span>
          <Badge variant={statusVariant(media.status)} labelPrefix="Agreement status:">
            {media.status === "READY" ? "Ready" : media.status === "REJECTED" ? "Rejected" : "Uploading"}
          </Badge>
          {media.download_url && (
            <a
              href={media.download_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm font-medium text-blue-600 underline hover:text-blue-800"
            >
              View PDF
            </a>
          )}
          {canEdit && !isReplacing && (
            <Button size="sm" variant="outline" onClick={() => setIsReplacing(true)} disabled={isUploading}>
              Replace
            </Button>
          )}
        </div>
      )}

      {!media && !mediaError && !canEdit && (
        <p className="mt-4 text-sm text-gray-600">No agreement uploaded yet. An admin needs to add one.</p>
      )}

      {showPicker && (
        <div className="mt-4 space-y-2">
          <AgreementFilePicker
            label={media ? "Replacement PDF" : "Upload agreement PDF"}
            disabled={isUploading}
            onSelect={handleSelect}
            onError={setPickError}
          />
          {isReplacing && (
            <Button size="sm" variant="ghost" onClick={() => setIsReplacing(false)}>
              Cancel
            </Button>
          )}
        </div>
      )}

      {isUploading && (
        <p role="status" className="mt-3 text-sm text-gray-600">
          Uploading agreement...
        </p>
      )}
      {(uploadError || pickError) && (
        <div role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {uploadError || pickError}
        </div>
      )}
    </section>
  );
}
