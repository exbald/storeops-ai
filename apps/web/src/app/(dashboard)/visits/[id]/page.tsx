"use client";

import React, { useEffect, useState, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiClient, VersionConflictError } from "../../../../lib/api-client";
import { formatFreshness } from "../../../../lib/formatters";
import type { Visit, Store, Promotion, Investigation, Job, JobEvent, Media } from "@storeops/contracts";
import { Button } from "../../../../components/ui/button";
import { Badge } from "../../../../components/ui/badge";
import { Input } from "../../../../components/ui/input";
import { Select } from "../../../../components/ui/select";
import { Modal } from "../../../../components/ui/modal";

export default function VisitDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const visitId = params.id as string;

  const [visit, setVisit] = useState<Visit | null>(null);
  const [store, setStore] = useState<Store | null>(null);
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Notes editing state
  const [notes, setNotes] = useState("");
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [isSavingNotes, setIsSavingNotes] = useState(false);
  const [notesError, setNotesError] = useState<string | null>(null);

  // Media upload state
  const [uploadedMedia, setUploadedMedia] = useState<Media[]>([]);
  const [selectedZoneKind, setSelectedZoneKind] = useState<"SHELF" | "DISPLAY">("SHELF");
  const [zoneId, setZoneId] = useState("shelf-main");
  const [mediaKind, setMediaKind] = useState<"VISIT_BEFORE" | "VISIT_AFTER">("VISIT_BEFORE");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // Investigation trigger modal
  const [isInvestigateOpen, setIsInvestigateOpen] = useState(false);
  const [selectedPromoId, setSelectedPromoId] = useState<string>("");
  const [isTriggeringInv, setIsTriggeringInv] = useState(false);
  const [invError, setInvError] = useState<string | null>(null);

  // Active Job polling state (supports reload recovery via query param or job trigger)
  const initialJobId = searchParams.get("job_id");
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [jobEvents, setJobEvents] = useState<JobEvent[]>([]);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Separate section errors (no silent fallbacks)
  const [storeError, setStoreError] = useState<string | null>(null);
  const [promotionsError, setPromotionsError] = useState<string | null>(null);
  const [investigationsError, setInvestigationsError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const visitData = await apiClient.getVisit(visitId);
      setVisit(visitData);
      setNotes(visitData.notes || "");

      try {
        const storeData = await apiClient.getStore(visitData.store_id);
        setStore(storeData);
        setStoreError(null);
      } catch (err: unknown) {
        console.error("Failed to load store:", err);
        setStoreError(err instanceof Error ? err.message : "Failed to load store details");
      }

      try {
        const promoRes = await apiClient.listPromotions();
        setPromotions(promoRes.items);
        setPromotionsError(null);
        if (promoRes.items.length > 0) {
          setSelectedPromoId(promoRes.items[0].id);
        }
      } catch (err: unknown) {
        console.error("Failed to load promotions:", err);
        setPromotionsError(err instanceof Error ? err.message : "Failed to load promotions");
      }

      try {
        const invRes = await apiClient.listInvestigations({ visit_id: visitId });
        setInvestigations(invRes.items);
        setInvestigationsError(null);
      } catch (err: unknown) {
        console.error("Failed to load investigations:", err);
        setInvestigationsError(err instanceof Error ? err.message : "Failed to load investigations");
      }
    } catch (err: unknown) {
      console.error("Failed to load visit details:", err);
      setError(err instanceof Error ? err.message : "Failed to load visit");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (visitId) {
      loadData();
    }
  }, [visitId]);

  // Handle active job polling with sequence tracking
  useEffect(() => {
    const jobIdToPoll = activeJob?.id || initialJobId;
    if (!jobIdToPoll) return;

    let isPolling = true;

    const poll = async () => {
      try {
        const job = await apiClient.getJob(jobIdToPoll);
        setActiveJob(job);

        const eventsRes = await apiClient.getJobEvents(jobIdToPoll);
        setJobEvents(eventsRes.items);

        if (job.status === "SUCCEEDED" || job.status === "FAILED") {
          // Terminal state reached, reload investigations
          const invRes = await apiClient.listInvestigations({ visit_id: visitId });
          setInvestigations(invRes.items);
          return;
        }

        if (isPolling) {
          pollTimerRef.current = setTimeout(poll, 2000);
        }
      } catch (pollErr) {
        console.error("Job poll error:", pollErr);
      }
    };

    poll();

    return () => {
      isPolling = false;
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current);
    };
  }, [activeJob?.id, initialJobId, visitId]);

  const handleSaveNotes = async () => {
    if (!visit) return;
    setIsSavingNotes(true);
    setNotesError(null);
    try {
      const updated = await apiClient.updateVisit(visit.id, {
        expected_version: visit.version,
        notes: notes.trim() || "Visit notes",
      });
      setVisit(updated);
      setIsEditingNotes(false);
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setNotesError("Version conflict: The visit notes were modified concurrently. Please refresh.");
      } else {
        setNotesError(err instanceof Error ? err.message : "Failed to update visit notes");
      }
    } finally {
      setIsSavingNotes(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !visit) return;
    if (visit.workspace_id) {
      apiClient.setWorkspaceId(visit.workspace_id);
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      const arrayBuffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const sha256 = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");

      let mimeType: "image/jpeg" | "image/png" | "application/pdf" | "text/csv" = "image/jpeg";
      if (file.type === "image/png") mimeType = "image/png";
      else if (file.type === "application/pdf") mimeType = "application/pdf";
      else if (file.type === "text/csv") mimeType = "text/csv";

      // 1. Init media
      const initResp = await apiClient.initMedia({
        kind: mediaKind,
        filename: file.name,
        mime_type: mimeType,
        byte_size: file.size,
        sha256,
        store_id: visit.store_id,
        visit_id: visit.id,
        product_id: null,
        zone_id: zoneId,
        zone_kind: selectedZoneKind,
        captured_at: new Date().toISOString(),
      });

      // 2. Upload file bytes to upload_url
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

      // 3. Complete media
      const completed = await apiClient.completeMedia(initResp.media.id, {
        expected_version: 1,
      });

      setUploadedMedia((prev) => [completed, ...prev]);
    } catch (err: unknown) {
      console.error("Upload error:", err);
      setUploadError(err instanceof Error ? err.message : "Failed to upload photo");
    } finally {
      setIsUploading(false);
      // Reset input
      e.target.value = "";
    }
  };

  const handleLoadSamplePhoto = async (
    samplePath = "/samples/shelf_before.jpg",
    filename = "shelf_before.jpg",
    kind: "VISIT_BEFORE" | "VISIT_AFTER" = "VISIT_BEFORE"
  ) => {
    if (!visit) return null;
    if (visit.workspace_id) {
      apiClient.setWorkspaceId(visit.workspace_id);
    }
    setIsUploading(true);
    setUploadError(null);
    try {
      const res = await fetch(samplePath);
      if (!res.ok) throw new Error("Failed to load sample shelf photo asset.");
      const blob = await res.blob();
      const file = new File([blob], filename, { type: "image/jpeg" });

      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const sha256 = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");

      const initResp = await apiClient.initMedia({
        kind,
        filename,
        mime_type: "image/jpeg",
        byte_size: file.size,
        sha256,
        store_id: visit.store_id,
        visit_id: visit.id,
        product_id: null,
        zone_id: zoneId || "ZONE-BEV-01",
        zone_kind: selectedZoneKind || "SHELF",
        captured_at: new Date().toISOString(),
      });

      if (initResp.upload_url && !apiClient.useDoubles) {
        const uploadRes = await fetch(initResp.upload_url, {
          method: "PUT",
          headers: { "Content-Type": "image/jpeg" },
          body: file,
        });
        if (!uploadRes.ok) {
          throw new Error(`Media upload failed with status ${uploadRes.status}: ${uploadRes.statusText}`);
        }
      }

      const completed = await apiClient.completeMedia(initResp.media.id, {
        expected_version: 1,
      });

      setUploadedMedia((prev) => [completed, ...prev]);
      return completed;
    } catch (err: unknown) {
      console.error("Sample upload error:", err);
      setUploadError(err instanceof Error ? err.message : "Failed to load sample photo");
      return null;
    } finally {
      setIsUploading(false);
    }
  };

  const handleTriggerInvestigation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!visit || !selectedPromoId) return;

    let mediaToSubmit = [...uploadedMedia];

    // If no media uploaded yet, automatically load the demo shelf photo for frictionless experience
    if (mediaToSubmit.length === 0) {
      setIsTriggeringInv(true);
      const sample = await handleLoadSamplePhoto();
      if (!sample) {
        setInvError("Please upload or attach at least one shelf photo before triggering investigation.");
        setIsTriggeringInv(false);
        return;
      }
      mediaToSubmit = [sample];
    }

    if (visit.workspace_id) {
      apiClient.setWorkspaceId(visit.workspace_id);
    }
    setIsTriggeringInv(true);
    setInvError(null);

    try {
      const job = await apiClient.createInvestigation({
        store_id: visit.store_id,
        visit_id: visit.id,
        promotion_id: selectedPromoId,
        media_ids: mediaToSubmit.map((m) => m.id),
      });

      setActiveJob(job);
      setIsInvestigateOpen(false);
      router.replace(`/visits/${visit.id}?job_id=${job.id}`);
    } catch (err: unknown) {
      console.error("Investigation error:", err);
      setInvError(err instanceof Error ? err.message : "Failed to trigger investigation");
    } finally {
      setIsTriggeringInv(false);
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        Loading visit details...
      </div>
    );
  }

  if (error || !visit) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-600 font-medium mb-4">{error || "Visit not found"}</p>
        <Link href="/stores">
          <Button variant="outline">Back to Stores</Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Visit Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">
              Visit at {store?.name || "Store"}
            </h1>
            <Badge
              variant={
                visit.status === "OPEN"
                  ? "warning"
                  : visit.status === "CLOSED"
                  ? "success"
                  : "neutral"
              }
            >
              {visit.status}
            </Badge>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Started: {formatFreshness(visit.visit_started_at || visit.created_at)} • Status: {visit.status}
          </p>
        </div>

        <div className="flex gap-3">
          {store && (
            <Link href={`/stores/${store.id}`}>
              <Button variant="outline">Store Detail</Button>
            </Link>
          )}
          {visit.status === "OPEN" && (
            <Button
              onClick={() => setIsInvestigateOpen(true)}
              className="bg-indigo-600 hover:bg-indigo-700 text-white font-medium flex items-center gap-2 shadow-sm"
            >
              <span>🤖</span>
              <span>Trigger AI Investigation</span>
            </Button>
          )}
        </div>
      </div>

      {/* Existing Active Investigation Callout Banner */}
      {investigations.length > 0 && (
        <div className="rounded-lg bg-gradient-to-r from-emerald-50 via-teal-50 to-blue-50 border border-emerald-200 p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⚡</span>
            <div>
              <h2 className="text-sm font-semibold text-emerald-950">
                AI Merchandising Investigation Active: #{investigations[0].id.slice(0, 8)} ({investigations[0].state})
              </h2>
              <p className="text-xs text-emerald-800 mt-0.5">
                Hypothesis: <strong>{investigations[0].diagnosis?.hypothesis}</strong> • {investigations[0].actions.length} action item(s) formulated by Gemini.
              </p>
            </div>
          </div>
          <Link href={`/investigations/${investigations[0].id}`}>
            <Button size="sm" className="bg-emerald-600 hover:bg-emerald-700 text-white font-medium shadow-sm">
              View AI Diagnosis & Action Plan →
            </Button>
          </Link>
        </div>
      )}

      {/* Store Error Banner */}
      {storeError && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex justify-between items-center">
          <div>
            <p className="font-semibold text-sm">Failed to load store information</p>
            <p className="text-xs mt-0.5">{storeError}</p>
          </div>
          <Button variant="outline" size="sm" onClick={loadData}>
            Retry
          </Button>
        </div>
      )}

      {/* Promotions Error Banner */}
      {promotionsError && (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex justify-between items-center">
          <div>
            <p className="font-semibold text-sm">Failed to load promotions</p>
            <p className="text-xs mt-0.5">{promotionsError}</p>
          </div>
          <Button variant="outline" size="sm" onClick={loadData}>
            Retry
          </Button>
        </div>
      )}

      {/* Notes Section with Concurrency Fencing */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-3">
        <div className="flex justify-between items-center">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">
            Visit Notes
          </h2>
          {!isEditingNotes && visit.status === "OPEN" && (
            <Button variant="outline" size="sm" onClick={() => setIsEditingNotes(true)}>
              Edit Notes
            </Button>
          )}
        </div>

        {notesError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
            {notesError}
          </div>
        )}

        {isEditingNotes ? (
          <div className="space-y-3">
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded-md border border-gray-300 p-2.5 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Record observations, stock check findings, store manager feedback..."
            />
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setNotes(visit.notes || "");
                  setIsEditingNotes(false);
                  setNotesError(null);
                }}
                disabled={isSavingNotes}
              >
                Cancel
              </Button>
              <Button size="sm" onClick={handleSaveNotes} disabled={isSavingNotes}>
                {isSavingNotes ? "Saving..." : "Save Notes"}
              </Button>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-700 whitespace-pre-wrap">
            {visit.notes || "No visit notes recorded."}
          </p>
        )}
      </div>

      {/* Active Investigation Job Processing Card */}
      {activeJob && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 space-y-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-blue-900 text-sm">
                Investigation Processing ({activeJob.status})
              </span>
              <Badge variant={activeJob.status === "SUCCEEDED" ? "success" : activeJob.status === "FAILED" ? "danger" : "warning"}>
                {activeJob.status}
              </Badge>
            </div>
            <span className="text-xs text-blue-700 font-mono">
              Job: {activeJob.id.slice(0, 8)}
            </span>
          </div>

          <div className="w-full bg-blue-200 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{
                width:
                  activeJob.status === "SUCCEEDED"
                    ? "100%"
                    : activeJob.status === "RUNNING"
                    ? "50%"
                    : "15%",
              }}
            />
          </div>

          {jobEvents.length > 0 && (
            <div className="bg-white rounded border border-blue-100 p-3 max-h-36 overflow-y-auto space-y-1">
              {jobEvents.map((ev) => (
                <div key={ev.sequence} className="text-xs text-gray-700 flex justify-between">
                  <span>{ev.summary}</span>
                  <span className="text-gray-400 text-[10px]">{formatFreshness(ev.at)}</span>
                </div>
              ))}
            </div>
          )}

          {activeJob.status === "SUCCEEDED" && activeJob.resource_id && (
            <div className="pt-2">
              <Link href={`/investigations/${activeJob.resource_id}`}>
                <Button size="sm">
                  View Resulting Investigation & Plan
                </Button>
              </Link>
            </div>
          )}
        </div>
      )}

      {/* Existing Investigations */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">Investigations</h2>
        {investigationsError ? (
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md">
            Failed to load investigations: {investigationsError}
          </div>
        ) : investigations.length === 0 ? (
          <p className="text-sm text-gray-500">
            No investigations triggered for this visit yet. Upload shelf photos above and click "Trigger Investigation".
          </p>
        ) : (
          <div className="divide-y divide-gray-100">
            {investigations.map((inv) => (
              <div key={inv.id} className="py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-900 text-sm">
                      Investigation #{inv.id.slice(0, 8)}
                    </span>
                    <Badge variant={inv.state === "RESOLVED" ? "success" : inv.state === "DISMISSED" ? "neutral" : "warning"}>
                      {inv.state}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Hypothesis: {inv.diagnosis?.hypothesis || "PENDING"} • {inv.actions.length} action item(s)
                  </p>
                  {inv.diagnosis?.summary && (
                    <p className="text-xs text-gray-700 mt-1 italic">
                      "{inv.diagnosis.summary}"
                    </p>
                  )}
                </div>
                <Link href={`/investigations/${inv.id}`}>
                  <Button variant="outline" size="sm">
                    Inspect Investigation
                  </Button>
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Media Evidence Upload Section */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Visit Media & Photos</h2>
            <p className="text-xs text-gray-500">
              Upload before-action photos for investigation or after-action photos for verification.
            </p>
          </div>
        </div>

        {uploadError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
            {uploadError}
          </div>
        )}

        {visit.status === "OPEN" && (
          <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                  Photo Type
                </label>
                <Select
                  value={mediaKind}
                  onChange={(e) =>
                    setMediaKind(e.target.value as "VISIT_BEFORE" | "VISIT_AFTER")
                  }
                  options={[
                    { value: "VISIT_BEFORE", label: "Before Photo (Pre-Audit / Issue)" },
                    { value: "VISIT_AFTER", label: "After Photo (Corrective Action)" },
                  ]}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                  Shelf Zone
                </label>
                <Select
                  value={selectedZoneKind}
                  onChange={(e) =>
                    setSelectedZoneKind(e.target.value as "SHELF" | "DISPLAY")
                  }
                  options={[
                    { value: "SHELF", label: "Shelf" },
                    { value: "DISPLAY", label: "Endcap / Display Feature" },
                  ]}
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-600 uppercase mb-1">
                  Zone Identifier
                </label>
                <Input
                  value={zoneId}
                  onChange={(e) => setZoneId(e.target.value)}
                  placeholder="e.g. shelf-main, aisle-3"
                />
              </div>
            </div>

            <div className="pt-2 flex flex-wrap items-center gap-3">
              <label className="cursor-pointer">
                <input
                  type="file"
                  accept="image/jpeg,image/png"
                  className="hidden"
                  onChange={handleFileUpload}
                  disabled={isUploading}
                />
                <Button type="button" variant="outline" size="sm" disabled={isUploading}>
                  {isUploading ? "Uploading..." : "Select & Upload Photo"}
                </Button>
              </label>

              <Button
                type="button"
                variant="primary"
                size="sm"
                disabled={isUploading}
                onClick={() => handleLoadSamplePhoto("/samples/shelf_before.jpg", "shelf_before.jpg", "VISIT_BEFORE")}
                className="bg-indigo-600 hover:bg-indigo-700 text-white flex items-center gap-1.5 shadow-sm text-xs font-medium"
              >
                📸 Load Sample Shelf Photo (1-Click Demo)
              </Button>

              <span className="text-xs text-gray-400">
                JPEG/PNG format, normalized bounding boxes & EXIF metadata stripped.
              </span>
            </div>
          </div>
        )}

        {/* Uploaded Media Gallery */}
        {uploadedMedia.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-2">
            {uploadedMedia.map((media) => (
              <div key={media.id} className="border border-gray-200 rounded p-3 text-xs space-y-1 bg-gray-50/50">
                <div className="font-semibold text-gray-800 truncate">{media.filename}</div>
                <div className="flex justify-between items-center">
                  <Badge variant={media.kind === "VISIT_BEFORE" ? "neutral" : "success"}>
                    {media.kind === "VISIT_BEFORE" ? "Before" : "After"}
                  </Badge>
                  <span className="text-gray-400 font-mono text-[10px]">{media.zone_id || "Zone"}</span>
                </div>
                <div className="text-[10px] text-gray-400 font-mono truncate">
                  ID: {media.id.slice(0, 8)}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="p-4 bg-gray-50 border border-dashed border-gray-200 rounded-md text-center space-y-2">
            <p className="text-sm text-gray-500">No media uploaded yet for this session.</p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isUploading}
              onClick={() => handleLoadSamplePhoto("/samples/shelf_before.jpg", "shelf_before.jpg", "VISIT_BEFORE")}
              className="text-indigo-600 border-indigo-200 hover:bg-indigo-50 text-xs"
            >
              📸 Load Demo Shelf Photo (shelf_before.jpg)
            </Button>
          </div>
        )}
      </div>

      {/* Trigger Investigation Modal */}
      <Modal
        isOpen={isInvestigateOpen}
        onClose={() => setIsInvestigateOpen(false)}
        title="Trigger AI Merchandising Investigation"
      >
        <form onSubmit={handleTriggerInvestigation} className="space-y-4">
          <p className="text-sm text-gray-600">
            Select an active promotion policy to analyze shelf compliance against the uploaded evidence photos.
          </p>

          {invError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
              {invError}
            </div>
          )}

          {promotionsError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
              Failed to load promotions: {promotionsError}. You must have an active promotion policy to run an investigation.
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Target Promotion Policy
            </label>
            <Select
              value={selectedPromoId}
              onChange={(e) => setSelectedPromoId(e.target.value)}
              options={promotions.map((p) => ({
                value: p.id,
                label: `${p.name} (${p.starts_on} to ${p.ends_on})`,
              }))}
            />
          </div>

          {uploadedMedia.length === 0 ? (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-900 flex items-center justify-between gap-2">
              <div>
                <span className="font-semibold">💡 No photos uploaded yet:</span>
                <p className="text-blue-700 mt-0.5">Clicking "Run Investigation" will automatically attach the demo shelf photo for you.</p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={isUploading}
                onClick={() => handleLoadSamplePhoto()}
                className="text-xs py-1 h-7 border-blue-300 bg-white hover:bg-blue-100 shrink-0"
              >
                {isUploading ? "Loading..." : "Attach Demo Photo"}
              </Button>
            </div>
          ) : (
            <div className="text-xs text-emerald-800 bg-emerald-50 border border-emerald-200 p-3 rounded flex items-center gap-2">
              <span className="text-base">📸</span>
              <span><strong>Visual Evidence:</strong> {uploadedMedia.length} photo(s) attached and ready for multimodal shelf analysis.</span>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsInvestigateOpen(false)}
              disabled={isTriggeringInv}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isTriggeringInv || promotions.length === 0}>
              {isTriggeringInv ? "Analyzing Shelf..." : "Run Investigation"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
