"use client";

import React, { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiClient, VersionConflictError } from "../../../../lib/api-client";
import { formatFreshness } from "../../../../lib/formatters";
import type { Investigation, Action, Verification, Job, JobEvent, Rule } from "@storeops/contracts";
import { Button } from "../../../../components/ui/button";
import { Badge } from "../../../../components/ui/badge";
import { Modal } from "../../../../components/ui/modal";
import { Select } from "../../../../components/ui/select";
import { useInvestigationEvidence } from "../../../../lib/use-investigation-evidence";
import { EvidenceThumbnails } from "../../../../components/investigation/evidence-thumbnails";
import { VerificationResults } from "../../../../components/investigation/verification-results";
import { VerifyModal } from "../../../../components/investigation/verify-modal";
import {
  ACTION_KIND_LABELS,
  CLAIM_KIND_LABELS,
  HYPOTHESIS_LABELS,
  STATE_LABELS,
} from "../../../../lib/investigation-labels";

export default function InvestigationDetailPage() {
  const params = useParams();
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
  const [rulesById, setRulesById] = useState<Record<string, Rule>>({});
  const evidence = useInvestigationEvidence(investigationId || null);

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
        const versionsRes = await apiClient.listPolicyVersions(invData.promotion_id);
        const policy = versionsRes.items.find((v) => v.id === invData.policy_version_id);
        const nextRules: Record<string, Rule> = {};
        for (const rule of policy?.rules ?? []) nextRules[rule.rule_id] = rule;
        setRulesById(nextRules);
      } catch (rulesErr: unknown) {
        // Rule names are labels only; checks still render with their rule id.
        console.error("Failed to load policy rules:", rulesErr);
      }

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
          evidence.reload();
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
  // A failed check returns the case to NEEDS_WORK; the rep fixes the shelf and verifies again.
  const canVerify = investigation.state === "ACCEPTED" || investigation.state === "NEEDS_WORK";

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
            <Badge variant={stateVariant}>{STATE_LABELS[investigation.state] ?? investigation.state}</Badge>
            {investigation.policy_stale && (
              <Badge variant="warning">Policy Superseded</Badge>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Plan version {investigation.plan_revision} • Created {formatFreshness(investigation.created_at)}
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

          {canVerify && (
            <Button
              onClick={() => setIsVerifyOpen(true)}
              disabled={!allActionsDone}
              title={!allActionsDone ? "Complete all action items before verifying" : ""}
            >
              {investigation.state === "NEEDS_WORK" ? "Verify again" : "Verify the fix"}
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

      {evidence.error && (
        <div role="alert" className="bg-red-50 p-4 rounded-lg border border-red-200 text-sm text-red-700 flex justify-between items-center gap-3">
          <div>
            <span className="font-semibold">Failed to load evidence photos:</span> {evidence.error}
          </div>
          <Button variant="outline" size="sm" onClick={() => evidence.reload()}>
            Retry
          </Button>
        </div>
      )}

      {/* 1. Diagnosis */}
      <section className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
        <h2 className="text-lg font-semibold text-gray-900">1. What is going wrong</h2>

        {investigation.diagnosis ? (
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 p-4 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-lg font-bold text-indigo-950">
                {HYPOTHESIS_LABELS[investigation.diagnosis.hypothesis]?.title ?? investigation.diagnosis.hypothesis}
              </span>
              <Badge variant={investigation.diagnosis.support === "SUPPORTED" ? "success" : "warning"} labelPrefix="Evidence strength:">
                {investigation.diagnosis.support === "SUPPORTED" ? "Well supported" : "Limited evidence"}
              </Badge>
            </div>
            <p className="text-sm text-indigo-900">{investigation.diagnosis.summary}</p>
          </div>
        ) : (
          <p className="text-sm text-gray-500">No diagnosis yet.</p>
        )}

        {investigation.diagnosis && investigation.diagnosis.claims.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">
              Why StoreOps thinks so
            </h3>
            <ul className="space-y-3">
              {investigation.diagnosis.claims.map((claim) => (
                <li key={claim.id} className="text-sm bg-gray-50 p-3 rounded border border-gray-100 space-y-2">
                  <div>
                    <span className="inline-block text-xs font-semibold text-gray-700 bg-white border border-gray-200 rounded px-1.5 py-0.5 mr-2">
                      {CLAIM_KIND_LABELS[claim.kind] ?? claim.kind}
                    </span>
                    <span className="text-gray-800">{claim.text}</span>
                  </div>
                  <EvidenceThumbnails
                    evidenceIds={claim.evidence_ids}
                    evidenceById={evidence.evidenceById}
                    loading={evidence.loading}
                  />
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {/* 2. Corrective actions */}
      <section className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">2. What the rep should do</h2>
            <p className="text-xs text-gray-500">
              Complete each action on the shelf, then verify the fix with a new photo.
            </p>
          </div>
          <span className="text-xs font-semibold text-gray-600">
            {investigation.actions.filter((a) => a.status !== "OPEN").length} of {investigation.actions.length} done
          </span>
        </div>

        <ol className="space-y-3">
          {investigation.actions.map((act, idx) => {
            const isDone = act.status !== "OPEN";
            const canToggle = canVerify && act.status !== "VERIFIED";

            return (
              <li
                key={act.id}
                className={`p-4 rounded-lg border flex flex-col sm:flex-row sm:items-start justify-between gap-4 ${
                  isDone ? "border-green-200 bg-green-50/50" : "border-gray-200"
                }`}
              >
                <div className="flex gap-3 min-w-0">
                  <span
                    className={`shrink-0 w-7 h-7 rounded-full text-xs font-bold flex items-center justify-center ${
                      isDone ? "bg-green-600 text-white" : "bg-gray-200 text-gray-700"
                    }`}
                    aria-hidden="true"
                  >
                    {isDone ? "✓" : idx + 1}
                  </span>
                  <div className="space-y-2 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-semibold bg-gray-100 text-gray-700 px-2 py-0.5 rounded">
                        {ACTION_KIND_LABELS[act.kind] ?? act.kind}
                      </span>
                      <Badge variant={act.status === "VERIFIED" ? "success" : isDone ? "info" : "warning"}>
                        {act.status === "VERIFIED" ? "Verified" : isDone ? "Done" : "To do"}
                      </Badge>
                      {act.required_zone_ids.length > 0 && (
                        <span className="text-xs text-gray-500">Zone: {act.required_zone_ids.join(", ")}</span>
                      )}
                    </div>
                    <p className="text-sm font-medium text-gray-900">{act.instruction}</p>
                    <EvidenceThumbnails
                      evidenceIds={act.evidence_ids}
                      evidenceById={evidence.evidenceById}
                      loading={evidence.loading}
                    />
                  </div>
                </div>

                {canToggle && (
                  <div className="shrink-0">
                    <Button
                      size="sm"
                      variant={isDone ? "outline" : "primary"}
                      onClick={() => handleToggleActionStatus(act)}
                    >
                      {isDone ? "Mark Incomplete" : "Claim Done"}
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      </section>

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

      <VerificationResults
        verifications={verifications}
        rulesById={rulesById}
        evidenceById={evidence.evidenceById}
        evidenceLoading={evidence.loading}
      />

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

      <VerifyModal
        isOpen={isVerifyOpen}
        onClose={() => setIsVerifyOpen(false)}
        investigation={investigation}
        onSubmitted={(job) => {
          setActiveJob(job);
          setIsVerifyOpen(false);
        }}
        onConflict={loadData}
      />
    </div>
  );
}
