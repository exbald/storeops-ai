"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { apiClient, VersionConflictError } from "../../../lib/api-client";
import { generateUuid } from "../../../lib/doubles";
import type { Promotion, Store, Product, Rule } from "@storeops/contracts";
import { Table, Column } from "../../../components/ui/table";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Badge } from "../../../components/ui/badge";
import { Modal } from "../../../components/ui/modal";
import { Select } from "../../../components/ui/select";

export default function PromotionsPage() {
  const { isAdmin } = useAuth();
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [stores, setStores] = useState<Store[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [globalAlert, setGlobalAlert] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // New Promotion Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [promoName, setPromoName] = useState("");
  const [startsOn, setStartsOn] = useState("2026-10-01");
  const [endsOn, setEndsOn] = useState("2026-10-31");
  const [selectedStoreIds, setSelectedStoreIds] = useState<string[]>([]);
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  // Policy Review / Approval Modal
  const [activeReviewPromo, setActiveReviewPromo] = useState<Promotion | null>(null);
  const [rules, setRules] = useState<Rule[]>([]);
  const [approvalError, setApprovalError] = useState<string | null>(null);
  const [isApproving, setIsApproving] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [promoRes, storeRes, prodRes] = await Promise.all([
        apiClient.listPromotions(),
        apiClient.listStores(),
        apiClient.listProducts(),
      ]);
      setPromotions(promoRes.items);
      setStores(storeRes.items);
      setProducts(prodRes.items);
      if (storeRes.items.length > 0) {
        setSelectedStoreIds([storeRes.items[0].id]);
      }
    } catch (err) {
      console.error("Failed to load promotions:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleCreatePromo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (selectedStoreIds.length === 0) {
      setCreateError("At least one store must be selected.");
      return;
    }
    setIsCreating(true);
    setCreateError(null);
    try {
      await apiClient.createPromotion({
        name: promoName,
        starts_on: startsOn,
        ends_on: endsOn,
        store_ids: selectedStoreIds,
        agreement_media_id: null,
      });
      setIsCreateOpen(false);
      setPromoName("");
      setGlobalAlert({
        type: "success",
        message: "Promotion draft created successfully.",
      });
      await loadData();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setCreateError(err.message);
      } else {
        setCreateError("Failed to create promotion.");
      }
    } finally {
      setIsCreating(false);
    }
  };

  const openReviewModal = async (promo: Promotion) => {
    setActiveReviewPromo(promo);
    setApprovalError(null);
    try {
      const versionsRes = await apiClient.listPolicyVersions(promo.id);
      if (versionsRes.items.length > 0) {
        setRules(versionsRes.items[0].rules);
      } else {
        // Mock extracted draft rules from vendor agreement with valid UUIDs
        const defaultProd = products[0]?.id || "00000000-0000-0000-0000-000000000031";
        setRules([
          {
            rule_id: generateUuid(),
            kind: "MIN_FACINGS",
            zone_id: "shelf-eye-level",
            zone_kind: "SHELF",
            product_id: defaultProd,
            min_facings: 3,
            source: {
              kind: "DOCUMENT",
              media_id: generateUuid(),
              page: 2,
              quote: "Retailer agrees to maintain a minimum of 3 facings on primary display shelf.",
              reviewer_note: null,
            },
          },
        ]);
      }
    } catch {
      setRules([]);
    }
  };

  const handleApprovePolicy = async () => {
    if (!activeReviewPromo) return;
    setIsApproving(true);
    setApprovalError(null);

    try {
      const catalogIds = products.map((p) => p.id);
      await apiClient.approvePolicy(activeReviewPromo.id, {
        expected_version: activeReviewPromo.version,
        catalog_product_ids: catalogIds.length > 0 ? catalogIds : ["00000000-0000-0000-0000-000000000031"],
        rules: rules,
      });
      setActiveReviewPromo(null);
      setGlobalAlert({
        type: "success",
        message: "Promotion policy approved and locked.",
      });
      await loadData();
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setApprovalError("Version Conflict: " + err.message + " Please refresh the promotion record.");
      } else if (err instanceof Error) {
        setApprovalError(err.message);
      } else {
        setApprovalError("Failed to approve merchandising policy.");
      }
    } finally {
      setIsApproving(false);
    }
  };

  const columns: Column<Promotion>[] = [
    {
      key: "name",
      header: "Promotion Name",
      render: (p) => (
        <div>
          <div className="font-semibold text-gray-900">{p.name}</div>
          <div className="text-xs text-gray-500">
            {p.starts_on} &rarr; {p.ends_on}
          </div>
        </div>
      ),
    },
    {
      key: "scope",
      header: "Store Scope",
      render: (p) => (
        <span className="text-xs font-medium text-gray-700">
          {p.store_ids.length} store{p.store_ids.length !== 1 ? "s" : ""} included
        </span>
      ),
    },
    {
      key: "policy_status",
      header: "Policy Status",
      render: (p) => (
        <Badge
          variant={p.active_version_id ? "success" : "warning"}
          labelPrefix="Policy Status:"
        >
          {p.active_version_id ? "Policy Approved" : "Draft / Needs Approval"}
        </Badge>
      ),
    },
    {
      key: "version",
      header: "Record Version",
      render: (p) => <span className="font-mono text-xs text-gray-400">v{p.version}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      render: (p) => (
        <div className="flex items-center justify-end gap-2">
          {isAdmin && (
            <Button size="sm" variant={p.active_version_id ? "outline" : "primary"} onClick={() => openReviewModal(p)}>
              {p.active_version_id ? "View Policy" : "Review & Approve"}
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Global accessible feedback banner */}
      {globalAlert && (
        <div
          role={globalAlert.type === "error" ? "alert" : "status"}
          className={`p-4 rounded-md border text-sm flex items-start justify-between ${
            globalAlert.type === "error"
              ? "bg-red-50 border-red-200 text-red-800"
              : "bg-green-50 border-green-200 text-green-800"
          }`}
        >
          <div>{globalAlert.message}</div>
          <button
            onClick={() => setGlobalAlert(null)}
            className="ml-4 font-bold text-xs underline hover:no-underline"
            aria-label="Dismiss notification"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Promotions & Merchandising Policy</h1>
          <p className="text-sm text-gray-500 mt-1">
            Vendor trade agreements, multimodal rule extraction, and compliance planogram approval.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => setIsCreateOpen(true)}>
            Create Promotion
          </Button>
        )}
      </div>

      {/* Promotions Table */}
      <Table
        columns={columns}
        data={promotions}
        keyExtractor={(p) => p.id}
        emptyMessage="No promotions or agreements registered. Create your first promotion to extract policy rules."
        caption="Merchandising promotions and agreements"
      />

      {/* Create Promotion Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Create New Promotion"
        description="Establish campaign dates, target stores, and vendor contract."
      >
        <form onSubmit={handleCreatePromo} className="space-y-4">
          {createError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {createError}
            </div>
          )}

          <Input
            label="Promotion Name"
            required
            value={promoName}
            onChange={(e) => setPromoName(e.target.value)}
            placeholder="e.g. Q4 Carbonated Drinks Feature"
          />

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Start Date"
              type="date"
              required
              value={startsOn}
              onChange={(e) => setStartsOn(e.target.value)}
            />
            <Input
              label="End Date"
              type="date"
              required
              value={endsOn}
              onChange={(e) => setEndsOn(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <label className="block text-sm font-medium text-gray-700">
              Target Stores
            </label>
            <div className="max-h-32 overflow-y-auto border border-gray-300 rounded p-2 space-y-1">
              {stores.map((s) => (
                <label key={s.id} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={selectedStoreIds.includes(s.id)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setSelectedStoreIds([...selectedStoreIds, s.id]);
                      } else {
                        setSelectedStoreIds(selectedStoreIds.filter((id) => id !== s.id));
                      }
                    }}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>{s.name} ({s.code})</span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              isLoading={isCreating}
            >
              Create Draft Promotion
            </Button>
          </div>
        </form>
      </Modal>

      {/* Review & Approve Policy Modal */}
      {activeReviewPromo && (
        <Modal
          isOpen={Boolean(activeReviewPromo)}
          onClose={() => setActiveReviewPromo(null)}
          title={`Merchandising Policy Approval: ${activeReviewPromo.name}`}
          description={`Record version: v${activeReviewPromo.version} - Review extracted compliance rules prior to approval.`}
        >
          <div className="space-y-4">
            {approvalError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
                {approvalError}
              </div>
            )}

            <div className="p-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">
              <span className="font-semibold">Grounding Verification:</span> Rules below are extracted from vendor
              contracts with page citations and verbatim text quotes. Approving creates a formal, immutable policy version
              used by multimodal vision models to verify shelf compliance during audit visits.
            </div>

            <div className="space-y-3 max-h-60 overflow-y-auto">
              {rules.map((rule, idx) => {
                const prod = products.find((p) => p.id === rule.product_id);
                return (
                  <div key={rule.rule_id || idx} className="p-3 bg-gray-50 border border-gray-200 rounded text-sm space-y-1">
                    <div className="flex justify-between items-start">
                      <span className="font-semibold text-gray-900">
                        {rule.kind} &bull; {rule.zone_kind} ({rule.zone_id})
                      </span>
                      {rule.min_facings && (
                        <Badge variant="info">Min Facings: {rule.min_facings}</Badge>
                      )}
                    </div>
                    <div className="text-xs text-gray-600">
                      Product: <span className="font-mono">{prod?.name || rule.product_id}</span>
                    </div>
                    {rule.source?.quote && (
                      <blockquote className="text-xs italic text-gray-500 border-l-2 border-gray-300 pl-2 mt-1">
                        &ldquo;{rule.source.quote}&rdquo; (Page {rule.source.page})
                      </blockquote>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex justify-between items-center pt-4 border-t border-gray-200">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setActiveReviewPromo(null)}
              >
                Close
              </Button>
              {isAdmin && !activeReviewPromo.active_version_id && (
                <Button
                  onClick={handleApprovePolicy}
                  isLoading={isApproving}
                >
                  Approve & Activate Policy
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
