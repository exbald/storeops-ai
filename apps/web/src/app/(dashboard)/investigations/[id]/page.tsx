"use client";

import React, { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient, VersionConflictError } from "../../../../lib/api-client";
import { formatFreshness } from "../../../../lib/formatters";
import type { Investigation, Action, Verification, Job, JobEvent, Media, Schemas } from "@storeops/contracts";
import { Button } from "../../../../components/ui/button";
import { Badge } from "../../../../components/ui/badge";
import { Modal } from "../../../../components/ui/modal";
import { Select } from "../../../../components/ui/select";

export default function InvestigationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const investigationId = params.id as string;

  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [verifications, setVerifications] = useState<Verification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [verificationsError, setVerificationsError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Accept / Dismiss plan modal states
  const [isDismissOpen, setIsDismissOpen] = useState(false);
  const [dismissReason, setDismissReason] = useState<string>("SUPERSEDED");
  const [dismissNotes, setDismissNotes] = useState("");
  const [isSubmittingPlan, setIsSubmittingPlan] = useState(false);

  // Verify modal state
  const [isVerifyOpen, setIsVerifyOpen] = useState(false);
  const [afterMedia, setAfterMedia] = useState<Media[]>([]);
  const [isUploadingAfter, setIsUploadingAfter] = useState(false);
  const [isSubmittingVerify, setIsSubmittingVerify] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // Active Verification Job polling
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [jobEvents, setJobEvents] = useState<JobEvent[]>([]);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    setVerificationsError(null);
    try {
      const invData = await apiClient.getInvestigation(investigationId);
      setInvestigation(invData);

      try {
        const verifsRes = await apiClient.listVerifications(investigationId);
        setVerifications(verifsRes.items);
      } catch (verifErr: unknown) {
        console.error("Failed to load verifications:", verifErr);
        setVerificationsError(verifErr instanceof Error ? verifErr.message : "Failed to load verifications");
      }
    } catch (err: unknown) {
      console.error("Failed to load investigation:", err);
      setError(err instanceof Error ? err.message : "Failed to load investigation");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (investigationId) {
      loadData();
    }
  }, [investigationId]);

  // Polling for active verification job
  useEffect(() => {
    if (!activeJob) return;
    let isPolling = true;

    const poll = async () => {
      try {
        const job = await apiClient.getJob(activeJob.id);
        setActiveJob(job);

        const eventsRes = await apiClient.getJobEvents(activeJob.id);
        setJobEvents(eventsRes.items);

        if (job.status === "SUCCEEDED" || job.status === "FAILED") {
          await loadData();
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
  }, [activeJob?.id]);

  const handleAcceptPlan = async () => {
    if (!investigation) return;
    setIsSubmittingPlan(true);
    setActionError(null);
    try {
      const updated = await apiClient.acceptInvestigation(investigation.id, {
        expected_version: investigation.version,
      });
      setInvestigation(updated);
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setActionError("Investigation was modified concurrently. Refreshing state...");
        await loadData();
      } else {
        setActionError(err instanceof Error ? err.message : "Failed to accept plan");
      }
    } finally {
      setIsSubmittingPlan(false);
    }
  };

  const handleDismissPlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!investigation) return;
    setIsSubmittingPlan(true);
    setActionError(null);
    try {
      const reasonText = dismissNotes.trim()
        ? `${dismissReason}: ${dismissNotes.trim()}`
        : dismissReason;
      const updated = await apiClient.dismissInvestigation(investigation.id, {
        expected_version: investigation.version,
        reason: reasonText,
      });
      setInvestigation(updated);
      setIsDismissOpen(false);
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setActionError("Investigation was modified concurrently. Refreshing state...");
        await loadData();
      } else {
        setActionError(err instanceof Error ? err.message : "Failed to dismiss investigation");
      }
    } finally {
      setIsSubmittingPlan(false);
    }
  };

  const handleToggleActionStatus = async (action: Action) => {
    if (!investigation) return;
    const newStatus: "OPEN" | "CLAIMED_DONE" =
      action.status === "CLAIMED_DONE" ? "OPEN" : "CLAIMED_DONE";

    setActionError(null);
    try {
      const updated = await apiClient.updateAction(investigation.id, action.id, {
        expected_version: investigation.version,
        status: newStatus,
      });
      setInvestigation(updated);
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setActionError("Investigation was modified concurrently. Refreshing state...");
        await loadData();
      } else {
        setActionError(err instanceof Error ? err.message : "Failed to update action status");
      }
    }
  };

  const handleAfterFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !investigation) return;

    setIsUploadingAfter(true);
    setVerifyError(null);
    try {
      const arrayBuffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest("SHA-256", arrayBuffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      const sha256 = hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");

      let mimeType: "image/jpeg" | "image/png" | "application/pdf" | "text/csv" = "image/jpeg";
      if (file.type === "image/png") mimeType = "image/png";
      else if (file.type === "application/pdf") mimeType = "application/pdf";
      else if (file.type === "text/csv") mimeType = "text/csv";

      const initResp = await apiClient.initMedia({
        kind: "VISIT_AFTER",
        filename: file.name,
        mime_type: mimeType,
        byte_size: file.size,
        sha256,
        store_id: investigation.store_id,
        visit_id: investigation.visit_id,
        product_id: null,
        zone_id: "shelf-main",
        zone_kind: "SHELF",
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

      const completed = await apiClient.completeMedia(initResp.media.id, {
        expected_version: 1,
      });

      setAfterMedia((prev) => [completed, ...prev]);
    } catch (err: unknown) {
      console.error("After photo upload error:", err);
      setVerifyError(err instanceof Error ? err.message : "Failed to upload after photo");
    } finally {
      setIsUploadingAfter(false);
      e.target.value = "";
    }
  };

  const handleTriggerVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!investigation) return;

    if (afterMedia.length === 0) {
      setVerifyError("Please upload at least one after-action shelf photo for verification.");
      return;
    }

    setIsSubmittingVerify(true);
    setVerifyError(null);

    try {
      const job = await apiClient.verifyInvestigation(investigation.id, {
        expected_version: investigation.version,
        after_media_ids: afterMedia.map((m) => m.id),
      });

      setActiveJob(job);
      setIsVerifyOpen(false);
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setVerifyError("Investigation was modified concurrently. Refreshing state...");
        await loadData();
      } else {
        setVerifyError(err instanceof Error ? err.message : "Failed to trigger verification");
      }
    } finally {
      setIsSubmittingVerify(false);
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        Loading investigation details...
      </div>
    );
  }

  if (error || !investigation) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-600 font-medium mb-4">{error || "Investigation not found"}</p>
        <Link href="/stores">
          <Button variant="outline">Back to Stores</Button>
        </Link>
      </div>
    );
  }

  const allActionsDone =
    investigation.actions.length > 0 &&
    investigation.actions.every((a) => a.status === "CLAIMED_DONE");

  const stateVariant =
    investigation.state === "RESOLVED"
      ? "success"
      : investigation.state === "DISMISSED"
      ? "neutral"
      : investigation.state === "ACCEPTED"
      ? "info"
      : "warning";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">
              Investigation #{investigation.id.slice(0, 8)}
            </h1>
            <Badge variant={stateVariant}>{investigation.state}</Badge>
            {investigation.policy_stale && (
              <Badge variant="warning">Policy Superseded</Badge>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Plan Revision: {investigation.plan_revision} • OCC Version: {investigation.version} • Created: {formatFreshness(investigation.created_at)}
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link href={`/visits/${investigation.visit_id}`}>
            <Button variant="outline">Return to Visit</Button>
          </Link>

          {investigation.state === "PROPOSED" && (
            <>
              <Button
                variant="outline"
                onClick={() => setIsDismissOpen(true)}
                disabled={isSubmittingPlan}
              >
                Dismiss
              </Button>
              <Button onClick={handleAcceptPlan} disabled={isSubmittingPlan}>
                {isSubmittingPlan ? "Accepting..." : "Accept Plan"}
              </Button>
            </>
          )}

          {investigation.state === "ACCEPTED" && (
            <Button
              onClick={() => setIsVerifyOpen(true)}
              disabled={!allActionsDone}
              title={!allActionsDone ? "Complete all action items before verifying" : ""}
            >
              Verify Execution →
            </Button>
          )}
        </div>
      </div>

      {actionError && (
        <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
          {actionError}
        </div>
      )}

      {/* Active Verification Job Processing Card */}
      {activeJob && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-5 space-y-3">
          <div className="flex justify-between items-center">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-blue-900 text-sm">
                Execution Verification Processing ({activeJob.status})
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
        </div>
      )}

      {/* Diagnosis & Hypothesis Card */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">
          AI Merchandising Diagnosis
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gray-50 p-4 rounded border border-gray-100">
            <span className="text-xs font-semibold text-gray-500 uppercase">Hypothesis</span>
            <div className="text-lg font-bold text-gray-900 mt-1">
              {investigation.diagnosis?.hypothesis || "EXECUTION"}
            </div>
            <span className="text-xs text-gray-500">
              Support: {investigation.diagnosis?.support || "SUPPORTED"}
            </span>
          </div>

          <div className="md:col-span-2 bg-gray-50 p-4 rounded border border-gray-100">
            <span className="text-xs font-semibold text-gray-500 uppercase">Summary Findings</span>
            <p className="text-sm text-gray-800 mt-1">
              {investigation.diagnosis?.summary || "No diagnostic summary available."}
            </p>
          </div>
        </div>

        {/* Claims and Observations */}
        {investigation.diagnosis?.claims && investigation.diagnosis.claims.length > 0 && (
          <div className="pt-2">
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
              Evidentiary Claims
            </h3>
            <ul className="space-y-2">
              {investigation.diagnosis.claims.map((claim) => (
                <li key={claim.id} className="text-sm bg-gray-50 p-3 rounded border border-gray-100 flex justify-between items-start">
                  <div>
                    <span className="font-semibold text-gray-800">{claim.kind}: </span>
                    <span className="text-gray-700">{claim.text}</span>
                  </div>
                  {claim.evidence_ids.length > 0 && (
                    <span className="text-xs font-mono text-blue-600 bg-blue-50 px-2 py-0.5 rounded">
                      {claim.evidence_ids.length} visual citation(s)
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Corrective Action Checklist */}
      <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Corrective Action Plan</h2>
            <p className="text-xs text-gray-500">
              Complete each required merchandising action on the shelf before verifying execution.
            </p>
          </div>
          <span className="text-xs font-semibold text-gray-600">
            {investigation.actions.filter((a) => a.status === "CLAIMED_DONE").length} / {investigation.actions.length} Completed
          </span>
        </div>

        <div className="divide-y divide-gray-100">
          {investigation.actions.map((act) => {
            const isDone = act.status === "CLAIMED_DONE";
            const canToggle = investigation.state === "ACCEPTED";

            return (
              <div key={act.id} className="py-4 flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-mono font-bold bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                      {act.kind}
                    </span>
                    <Badge variant={isDone ? "success" : "warning"}>
                      {act.status}
                    </Badge>
                  </div>
                  <p className="text-sm font-medium text-gray-900 mt-1">
                    {act.instruction}
                  </p>
                  <p className="text-xs text-gray-500">
                    Required Zones: {act.required_zone_ids.join(", ") || "All"}
                  </p>
                </div>

                <div>
                  <Button
                    size="sm"
                    variant={isDone ? "outline" : "primary"}
                    disabled={!canToggle}
                    onClick={() => handleToggleActionStatus(act)}
                  >
                    {isDone ? "Mark Incomplete" : "✓ Claim Done"}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Verification History & Reports */}
      {verificationsError && (
        <div className="bg-red-50 p-4 rounded-lg border border-red-200 text-sm text-red-700 flex justify-between items-center">
          <div>
            <span className="font-semibold">Failed to load verifications:</span> {verificationsError}
          </div>
          <Button variant="outline" size="sm" onClick={() => loadData()}>
            Retry
          </Button>
        </div>
      )}

      {verifications.length > 0 && (
        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-gray-900">Verification History</h2>
          <div className="divide-y divide-gray-100">
            {verifications.map((v) => (
              <div key={v.id} className="py-4 flex justify-between items-center">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold text-gray-900">
                      Verification #{v.id.slice(0, 8)}
                    </span>
                    <Badge variant={v.result === "PASS" ? "success" : v.result === "FAIL" ? "danger" : "warning"}>
                      {v.result}
                    </Badge>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Verified: {formatFreshness(v.created_at)} • {v.checks.length} compliance check(s)
                  </p>
                </div>
                {v.report_id && (
                  <Link href={`/reports/${v.report_id}`}>
                    <Button variant="outline" size="sm">
                      Inspect Report →
                    </Button>
                  </Link>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dismiss Modal */}
      <Modal
        isOpen={isDismissOpen}
        onClose={() => setIsDismissOpen(false)}
        title="Dismiss Investigation"
      >
        <form onSubmit={handleDismissPlan} className="space-y-4">
          <p className="text-sm text-gray-600">
            Provide a dismissal reason for auditing purposes. Dismissed investigations cannot be reopened.
          </p>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Dismissal Reason
            </label>
            <Select
              value={dismissReason}
              onChange={(e) => setDismissReason(e.target.value)}
              options={[
                { value: "SUPERSEDED", label: "Superseded by newer visit/policy" },
                { value: "INVALID_POLICY", label: "Invalid promotion or rule policy" },
                { value: "STORE_REFUSAL", label: "Store manager refusal / space unavailable" },
                { value: "STOCK_UNAVAILABLE", label: "Product stock physically unavailable" },
                { value: "OTHER", label: "Other operational reason" },
              ]}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Additional Notes (Optional)
            </label>
            <textarea
              rows={2}
              value={dismissNotes}
              onChange={(e) => setDismissNotes(e.target.value)}
              className="w-full rounded-md border border-gray-300 p-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="e.g. Endcap space reallocated by central office..."
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsDismissOpen(false)}
              disabled={isSubmittingPlan}
            >
              Cancel
            </Button>
            <Button type="submit" variant="danger" disabled={isSubmittingPlan}>
              {isSubmittingPlan ? "Dismissing..." : "Confirm Dismissal"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Verify Execution Modal */}
      <Modal
        isOpen={isVerifyOpen}
        onClose={() => setIsVerifyOpen(false)}
        title="Verify Merchandising Execution"
      >
        <form onSubmit={handleTriggerVerification} className="space-y-4">
          <p className="text-sm text-gray-600">
            Upload new after-action shelf photos showing the restored facings/merchandising. Gemini will evaluate the visual evidence against the required policy rules.
          </p>

          {verifyError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
              {verifyError}
            </div>
          )}

          <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 space-y-3">
            <div className="flex items-center gap-3">
              <label className="cursor-pointer">
                <input
                  type="file"
                  accept="image/jpeg,image/png"
                  className="hidden"
                  onChange={handleAfterFileUpload}
                  disabled={isUploadingAfter}
                />
                <Button type="button" variant="outline" size="sm" disabled={isUploadingAfter}>
                  {isUploadingAfter ? "Uploading..." : "📷 Upload After-Action Photo"}
                </Button>
              </label>
              <span className="text-xs text-gray-500">
                {afterMedia.length} after-photo(s) attached
              </span>
            </div>

            {afterMedia.length > 0 && (
              <div className="divide-y divide-gray-200 pt-2">
                {afterMedia.map((m) => (
                  <div key={m.id} className="py-1 text-xs text-gray-700 flex justify-between">
                    <span>{m.filename}</span>
                    <span className="text-green-600 font-bold">Ready</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsVerifyOpen(false)}
              disabled={isSubmittingVerify}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmittingVerify || afterMedia.length === 0}>
              {isSubmittingVerify ? "Submitting for Verification..." : "Run AI Verification"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
