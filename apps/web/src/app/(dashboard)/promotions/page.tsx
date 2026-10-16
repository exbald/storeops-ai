"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../lib/auth-context";
import { apiClient } from "../../../lib/api-client";
import type { Promotion, Store } from "@storeops/contracts";
import { Table, Column } from "../../../components/ui/table";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Badge } from "../../../components/ui/badge";
import { Modal } from "../../../components/ui/modal";
import { AgreementFilePicker } from "../../../components/promotions/agreement-file-picker";
import { uploadAgreementPdf } from "../../../components/promotions/agreement-upload";

const errorText = (err: unknown, fallback: string) => (err instanceof Error ? err.message : fallback);

export default function PromotionsPage() {
  const { isAdmin } = useAuth();
  const router = useRouter();
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [promotionsError, setPromotionsError] = useState<string | null>(null);
  const [stores, setStores] = useState<Store[]>([]);
  const [storesError, setStoresError] = useState<string | null>(null);
  const [storesLoaded, setStoresLoaded] = useState(false);

  // Create form
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [promoName, setPromoName] = useState("");
  const [startsOn, setStartsOn] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [selectedStoreIds, setSelectedStoreIds] = useState<string[]>([]);
  const [agreementFile, setAgreementFile] = useState<File | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createStep, setCreateStep] = useState<string | null>(null);

  const loadPromotions = useCallback(async () => {
    try {
      const res = await apiClient.listPromotions();
      setPromotions(res.items);
      setPromotionsError(null);
    } catch (err) {
      setPromotionsError(errorText(err, "Failed to load promotions"));
    }
  }, []);

  const loadStores = useCallback(async () => {
    try {
      const res = await apiClient.listStores();
      const active = res.items.filter((s) => s.active);
      setStores(active);
      setStoresError(null);
      setSelectedStoreIds((prev) => (prev.length > 0 || active.length === 0 ? prev : [active[0].id]));
    } catch (err) {
      setStoresError(errorText(err, "Failed to load stores"));
    } finally {
      setStoresLoaded(true);
    }
  }, []);

  useEffect(() => {
    loadPromotions();
    loadStores();
  }, [loadPromotions, loadStores]);

  const openCreate = () => {
    setCreateError(null);
    setIsCreateOpen(true);
    if (stores.length === 0) loadStores();
  };

  const toggleStore = (storeId: string, on: boolean) =>
    setSelectedStoreIds((prev) => (on ? [...prev, storeId] : prev.filter((id) => id !== storeId)));

  const handleCreatePromo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!promoName.trim()) return setCreateError("Enter a promotion name.");
    if (!startsOn || !endsOn) return setCreateError("Enter start and end dates.");
    if (startsOn > endsOn) return setCreateError("The start date must be on or before the end date.");
    if (selectedStoreIds.length === 0) return setCreateError("Select at least one store.");

    setCreateError(null);
    try {
      let agreementMediaId: string | null = null;
      if (agreementFile) {
        setCreateStep("Uploading agreement...");
        agreementMediaId = (await uploadAgreementPdf(agreementFile)).id;
      }
      setCreateStep("Creating promotion...");
      const created = await apiClient.createPromotion({
        name: promoName.trim(),
        starts_on: startsOn,
        ends_on: endsOn,
        store_ids: selectedStoreIds,
        agreement_media_id: agreementMediaId,
      });
      setIsCreateOpen(false);
      router.push(`/promotions/${created.id}`);
    } catch (err) {
      setCreateError(errorText(err, "Failed to create promotion."));
    } finally {
      setCreateStep(null);
    }
  };

  const columns: Column<Promotion>[] = [
    {
      key: "name",
      header: "Promotion",
      render: (p) => (
        <div>
          <Link href={`/promotions/${p.id}`} className="font-semibold text-blue-700 hover:underline">
            {p.name}
          </Link>
          <div className="text-xs text-gray-500">
            {p.starts_on} &rarr; {p.ends_on}
          </div>
        </div>
      ),
    },
    {
      key: "scope",
      header: "Stores",
      render: (p) => (
        <span className="text-xs font-medium text-gray-700">
          {p.store_ids.length} store{p.store_ids.length !== 1 ? "s" : ""}
        </span>
      ),
    },
    {
      key: "agreement",
      header: "Agreement",
      render: (p) => (
        <span className="text-xs text-gray-700">{p.agreement_media_id ? "Uploaded" : "Not uploaded"}</span>
      ),
    },
    {
      key: "policy_status",
      header: "Policy",
      render: (p) => (
        <Badge variant={p.approved_policy ? "success" : "warning"} labelPrefix="Policy status:">
          {p.approved_policy
            ? `Approved v${p.approved_policy.version}`
            : p.extracted_rules.length > 0
              ? "Draft, rules to review"
              : "Draft"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      render: (p) => (
        <Link
          href={`/promotions/${p.id}`}
          className="inline-flex items-center rounded-md border border-gray-300 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
        >
          {p.approved_policy ? "View policy" : "Review rules"}
        </Link>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Promotions</h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload a vendor agreement, let Gemini propose shelf rules, then approve the ones that apply.
          </p>
        </div>
        {isAdmin && <Button onClick={openCreate}>Create promotion</Button>}
      </div>

      {promotionsError && (
        <div role="alert" className="rounded border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Failed to load promotions: {promotionsError}
        </div>
      )}

      <Table
        columns={columns}
        data={promotions}
        keyExtractor={(p) => p.id}
        emptyMessage="No promotions yet. Create one and attach its vendor agreement."
        caption="Promotions and their policy status"
      />

      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create promotion"
        description="Set the dates and stores, and attach the vendor agreement if you have it."
      >
        <form onSubmit={handleCreatePromo} className="space-y-4" aria-label="Create promotion">
          {createError && (
            <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {createError}
            </div>
          )}

          <Input
            label="Promotion name"
            name="promotion-name"
            required
            value={promoName}
            onChange={(e) => setPromoName(e.target.value)}
            placeholder="e.g. AquaPure endcap, November"
          />

          <div className="grid grid-cols-2 gap-4">
            <Input label="Start date" name="starts-on" type="date" required value={startsOn} onChange={(e) => setStartsOn(e.target.value)} />
            <Input label="End date" name="ends-on" type="date" required value={endsOn} onChange={(e) => setEndsOn(e.target.value)} />
          </div>

          <fieldset className="space-y-1">
            <legend className="block text-sm font-medium text-gray-700">Target stores</legend>
            <div className="max-h-32 space-y-1 overflow-y-auto rounded border border-gray-300 p-2" data-testid="store-options">
              {storesError && (
                <p className="text-xs text-red-700">
                  Could not load stores: {storesError}{" "}
                  <button type="button" className="underline" onClick={loadStores}>
                    Retry
                  </button>
                </p>
              )}
              {!storesError && !storesLoaded && <p className="text-xs text-gray-500">Loading stores...</p>}
              {!storesError && storesLoaded && stores.length === 0 && (
                <p className="text-xs text-gray-600">
                  No active stores. <Link href="/stores" className="underline">Add a store</Link> first.
                </p>
              )}
              {stores.map((s) => (
                <label key={s.id} className="flex cursor-pointer items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={selectedStoreIds.includes(s.id)}
                    onChange={(e) => toggleStore(s.id, e.target.checked)}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>
                    {s.name} ({s.code})
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <AgreementFilePicker
            label="Agreement PDF (optional)"
            selectedName={agreementFile?.name ?? null}
            disabled={Boolean(createStep)}
            onSelect={(file) => {
              setCreateError(null);
              setAgreementFile(file);
            }}
            onError={setCreateError}
          />

          <div className="flex items-center justify-end gap-3 border-t border-gray-200 pt-4">
            {createStep && (
              <span role="status" className="mr-auto text-xs text-gray-600">
                {createStep}
              </span>
            )}
            <Button type="button" variant="secondary" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" isLoading={Boolean(createStep)}>
              Create promotion
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
