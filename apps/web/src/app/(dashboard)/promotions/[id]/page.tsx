"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { Job, JobEvent, Media, PolicyVersion, Product, Promotion, Rule, Store } from "@storeops/contracts";
import { useAuth } from "../../../../lib/auth-context";
import { apiClient, VersionConflictError } from "../../../../lib/api-client";
import { Badge } from "../../../../components/ui/badge";
import { AgreementCard } from "../../../../components/promotions/agreement-card";
import { uploadAgreementPdf } from "../../../../components/promotions/agreement-upload";
import { ExtractionPanel } from "../../../../components/promotions/extraction-panel";
import { pollJobUntilTerminal } from "../../../../components/promotions/job-poller";
import { ProposedRulesReview } from "../../../../components/promotions/proposed-rules-review";
import { ApprovedPolicy, PolicyVersionHistory } from "../../../../components/promotions/approved-policy";

const errorText = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback);

function conflictAware(err: unknown, fallback: string): string {
  if (err instanceof VersionConflictError) {
    return "This promotion changed since you opened it. Reload the page and try again.";
  }
  return errorText(err, fallback);
}

function extractDisabledReason(promotion: Promotion, media: Media | null, isAdmin: boolean): string | null {
  if (!isAdmin) return "Only admins can extract rules.";
  if (promotion.archived) return "This promotion is archived.";
  if (promotion.approved_policy) return "Rules are already approved for this promotion.";
  if (!promotion.agreement_media_id || !media) return "Upload the agreement PDF first.";
  if (media.status !== "READY") return "The agreement upload has not finished.";
  return null;
}

export default function PromotionDetailPage() {
  const params = useParams();
  const promotionId = (params?.id as string) || "";
  const { isAdmin } = useAuth();
  const mounted = useRef(true);

  const [promotion, setPromotion] = useState<Promotion | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [lookupError, setLookupError] = useState<string | null>(null);
  const [agreement, setAgreement] = useState<Media | null>(null);
  const [agreementError, setAgreementError] = useState<string | null>(null);
  const [versions, setVersions] = useState<PolicyVersion[]>([]);
  const [versionsError, setVersionsError] = useState<string | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [extractError, setExtractError] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const loadAgreement = useCallback(async (mediaId: string | null) => {
    setAgreementError(null);
    if (!mediaId) {
      setAgreement(null);
      return;
    }
    try {
      setAgreement(await apiClient.getMedia(mediaId));
    } catch (err) {
      setAgreement(null);
      setAgreementError(errorText(err, "Failed to load agreement"));
    }
  }, []);

  const loadVersions = useCallback(async () => {
    try {
      const res = await apiClient.listPolicyVersions(promotionId);
      setVersions(res.items);
      setVersionsError(null);
    } catch (err) {
      setVersionsError(errorText(err, "Failed to load versions"));
    }
  }, [promotionId]);

  const loadAll = useCallback(async () => {
    if (!promotionId) return;
    let promo: Promotion;
    try {
      promo = await apiClient.getPromotion(promotionId);
    } catch (err) {
      setLoadError(errorText(err, "Failed to load promotion"));
      return;
    }
    setPromotion(promo);
    setLoadError(null);
    const [storeRes, productRes] = await Promise.allSettled([apiClient.listStores(), apiClient.listProducts()]);
    if (storeRes.status === "fulfilled") setStores(storeRes.value.items);
    if (productRes.status === "fulfilled") setProducts(productRes.value.items);
    const failed = [storeRes, productRes].find((r): r is PromiseRejectedResult => r.status === "rejected");
    setLookupError(failed ? errorText(failed.reason, "Failed to load stores or products") : null);
    await Promise.all([loadAgreement(promo.agreement_media_id), loadVersions()]);
  }, [promotionId, loadAgreement, loadVersions]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const handleUpload = async (file: File) => {
    if (!promotion) return;
    setIsUploading(true);
    setUploadError(null);
    try {
      const media = await uploadAgreementPdf(file);
      const updated = await apiClient.updatePromotion(promotion.id, {
        expected_version: promotion.version,
        agreement_media_id: media.id,
      });
      setPromotion(updated);
      setAgreement(media);
      setAgreementError(null);
    } catch (err) {
      setUploadError(conflictAware(err, "Failed to upload the agreement"));
    } finally {
      setIsUploading(false);
    }
  };

  const handleExtract = async () => {
    if (!promotion) return;
    setIsStarting(true);
    setExtractError(null);
    setEvents([]);
    try {
      const started = await apiClient.extractPolicy(promotion.id, { expected_version: promotion.version });
      setJob(started);
      setIsStarting(false);
      const finished = await pollJobUntilTerminal(started.id, {
        isCancelled: () => !mounted.current,
        onUpdate: (j, ev) => {
          setJob(j);
          setEvents(ev);
        },
      });
      if (finished.status === "FAILED") {
        setExtractError(`Extraction failed: ${finished.error?.message ?? "the job reported no reason"}`);
      }
      setPromotion(await apiClient.getPromotion(promotion.id));
    } catch (err) {
      if (mounted.current) setExtractError(conflictAware(err, "Failed to extract rules"));
    } finally {
      if (mounted.current) setIsStarting(false);
    }
  };

  const handleApprove = async (rules: Rule[], catalogProductIds: string[]) => {
    if (!promotion) return;
    setIsApproving(true);
    setApproveError(null);
    try {
      await apiClient.approvePolicy(promotion.id, {
        expected_version: promotion.version,
        rules,
        catalog_product_ids: catalogProductIds,
      });
      setPromotion(await apiClient.getPromotion(promotion.id));
      await loadVersions();
    } catch (err) {
      setApproveError(conflictAware(err, "Failed to approve the rules"));
    } finally {
      setIsApproving(false);
    }
  };

  if (loadError) {
    return (
      <div className="space-y-4">
        <Link href="/promotions" className="text-sm text-blue-600 underline">
          &larr; All promotions
        </Link>
        <div role="alert" className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load promotion: {loadError}
        </div>
      </div>
    );
  }
  if (!promotion) {
    return <p className="text-sm text-gray-500">Loading promotion...</p>;
  }

  const storeNames = promotion.store_ids.map((id) => stores.find((s) => s.id === id)?.name ?? id);
  const disabledReason = extractDisabledReason(promotion, agreement, isAdmin);
  const approved = promotion.approved_policy;

  return (
    <div className="space-y-6">
      <Link href="/promotions" className="text-sm text-blue-600 underline">
        &larr; All promotions
      </Link>

      <header className="space-y-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-bold text-gray-900">{promotion.name}</h1>
          <Badge variant={approved ? "success" : "warning"} labelPrefix="Policy status:">
            {approved ? `Approved v${approved.version}` : "Draft"}
          </Badge>
          {promotion.archived && <Badge variant="neutral">Archived</Badge>}
        </div>
        <p className="text-sm text-gray-600">
          {promotion.starts_on} &rarr; {promotion.ends_on} &middot; Stores: {storeNames.join(", ")}
        </p>
      </header>

      {lookupError && (
        <div role="alert" className="rounded border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Some names could not be loaded: {lookupError}
        </div>
      )}

      <AgreementCard
        media={agreement}
        mediaError={agreementError}
        canEdit={isAdmin && !promotion.archived && !approved}
        isUploading={isUploading}
        uploadError={uploadError}
        onUpload={handleUpload}
      />

      {!approved && (
        <>
          <ExtractionPanel
            canExtract={disabledReason === null}
            disabledReason={disabledReason}
            hasProposals={promotion.extracted_rules.length > 0}
            isStarting={isStarting}
            job={job}
            events={events}
            error={extractError}
            onExtract={handleExtract}
          />
          <ProposedRulesReview
            key={`${promotion.draft_revision}-${promotion.agreement_media_id ?? "none"}`}
            rules={promotion.extracted_rules}
            gaps={promotion.extraction_gaps}
            products={products}
            agreementMediaId={promotion.agreement_media_id}
            canApprove={isAdmin && !promotion.archived}
            isApproving={isApproving}
            error={approveError}
            onApprove={handleApprove}
          />
        </>
      )}

      {approved && <ApprovedPolicy policy={approved} products={products} />}

      <PolicyVersionHistory versions={versions} error={versionsError} />
    </div>
  );
}
