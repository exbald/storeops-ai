"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "../../../../lib/api-client";
import {
  formatSales,
  formatStock,
  formatOpportunityProxy,
  formatFreshness,
} from "../../../../lib/formatters";
import type { Store, Visit, Schemas } from "@storeops/contracts";
import { Button } from "../../../../components/ui/button";
import { Badge } from "../../../../components/ui/badge";
import { Modal } from "../../../../components/ui/modal";
import { Table, Column } from "../../../../components/ui/table";

type StoreHealth = Schemas["StoreHealth"];

export default function StoreDetailPage() {
  const params = useParams();
  const router = useRouter();
  const storeId = params.id as string;

  const [store, setStore] = useState<Store | null>(null);
  const [health, setHealth] = useState<StoreHealth | null>(null);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Begin Visit modal
  const [isBeginVisitOpen, setIsBeginVisitOpen] = useState(false);
  const [visitNotes, setVisitNotes] = useState("");
  const [isCreatingVisit, setIsCreatingVisit] = useState(false);
  const [visitError, setVisitError] = useState<string | null>(null);

  const loadStoreData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [storeData, healthData, visitsData] = await Promise.all([
        apiClient.getStore(storeId),
        apiClient.getStoreHealth(storeId).catch(() => null),
        apiClient.listVisits({ store_id: storeId }).catch(() => ({ items: [] })),
      ]);
      setStore(storeData);
      setHealth(healthData);
      setVisits(visitsData.items);
    } catch (err: unknown) {
      console.error("Failed to load store:", err);
      setError(err instanceof Error ? err.message : "Failed to load store details");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (storeId) {
      loadStoreData();
    }
  }, [storeId]);

  const handleBeginVisit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCreatingVisit(true);
    setVisitError(null);
    try {
      const newVisit = await apiClient.createVisit({
        store_id: storeId,
        notes: visitNotes.trim() || undefined,
      });
      setIsBeginVisitOpen(false);
      router.push(`/visits/${newVisit.id}`);
    } catch (err: unknown) {
      console.error("Failed to create visit:", err);
      setVisitError(err instanceof Error ? err.message : "Failed to begin visit");
    } finally {
      setIsCreatingVisit(false);
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        Loading store details...
      </div>
    );
  }

  if (error || !store) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-600 font-medium mb-4">{error || "Store not found"}</p>
        <Link href="/stores">
          <Button variant="outline">Back to Stores</Button>
        </Link>
      </div>
    );
  }

  const freshnessVariant =
    health?.freshness === "CURRENT"
      ? "success"
      : health?.freshness === "STALE"
      ? "warning"
      : "neutral";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{store.name}</h1>
            <Badge variant={store.active ? "success" : "neutral"}>
              {store.active ? "Active" : "Archived"}
            </Badge>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            <span className="font-mono">{store.code}</span> • {store.retailer} • {store.format} • {store.region} ({store.timezone})
          </p>
        </div>
        <div className="flex gap-3">
          <Link href="/stores">
            <Button variant="outline">Back to Stores</Button>
          </Link>
          <Button onClick={() => setIsBeginVisitOpen(true)}>
            Begin Visit
          </Button>
        </div>
      </div>

      {/* Health & Metrics Section */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Freshness */}
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Data Freshness
          </div>
          <div className="flex items-center gap-2 mt-2">
            <Badge variant={freshnessVariant}>
              {health?.freshness || "MISSING"}
            </Badge>
          </div>
          <div className="text-xs text-gray-400 mt-2">
            Freshness status from sales and stock sync
          </div>
        </div>

        {/* Opportunity Proxy */}
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Opportunity Amount
          </div>
          <div className="text-lg font-bold text-gray-900 mt-2">
            {formatOpportunityProxy(health?.metrics?.opportunity_amount, store.currency)}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            Peer gap estimated revenue impact
          </div>
        </div>

        {/* Store Stock */}
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Store Stock
          </div>
          <div className="text-lg font-bold text-gray-900 mt-2">
            {formatStock(health?.metrics?.store_stock_units)}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            Source: Backroom inventory
          </div>
        </div>

        {/* Distributor Stock */}
        <div className="bg-white p-4 rounded-lg border border-gray-200 shadow-sm">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">
            Distributor Stock
          </div>
          <div className="text-lg font-bold text-gray-900 mt-2">
            {formatStock(health?.metrics?.distributor_stock_units)}
          </div>
          <div className="text-xs text-gray-400 mt-1">
            Source: Distribution center
          </div>
        </div>
      </div>

      {/* Readiness & Sales Info */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-3">
            Readiness Checklist
          </h2>
          {health?.readiness && health.readiness.length > 0 ? (
            <ul className="space-y-2">
              {health.readiness.map((item, idx) => (
                <li key={idx} className="flex items-center gap-2 text-sm text-gray-700">
                  <span className="text-green-600 font-bold">✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-500">No readiness requirements pending.</p>
          )}
        </div>

        <div className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-3">
            Sales Performance
          </h2>
          <div className="text-2xl font-bold text-gray-900">
            {formatSales(health?.metrics?.sales_units)}
          </div>
          <p className="text-xs text-gray-400 mt-2">
            Weekly velocity comparison against peer cohort.
          </p>
        </div>
      </div>

      {/* Visit History Section */}
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-5 space-y-4">
        <div className="flex justify-between items-center">
          <h2 className="text-lg font-semibold text-gray-900">Visit History</h2>
          <span className="text-xs text-gray-500 font-medium">
            {visits.length} {visits.length === 1 ? "visit" : "visits"} recorded
          </span>
        </div>

        <Table
          data={visits}
          keyExtractor={(v) => v.id}
          emptyMessage="No visits recorded for this store yet."
        >
          <Column<Visit>
            header="Date / Created"
            render={(v) => (
              <span className="text-sm font-medium text-gray-900">
                {formatFreshness(v.created_at)}
              </span>
            )}
          />
          <Column<Visit>
            header="Status"
            render={(v) => (
              <Badge
                variant={
                  v.status === "OPEN"
                    ? "warning"
                    : v.status === "CLOSED"
                    ? "success"
                    : "neutral"
                }
              >
                {v.status}
              </Badge>
            )}
          />
          <Column<Visit>
            header="Notes"
            render={(v) => (
              <span className="text-sm text-gray-600 truncate max-w-xs block">
                {v.notes || "—"}
              </span>
            )}
          />
          <Column<Visit>
            header="Actions"
            render={(v) => (
              <Link href={`/visits/${v.id}`}>
                <Button variant="outline" size="sm">
                  View Visit
                </Button>
              </Link>
            )}
          />
        </Table>
      </div>

      {/* Begin Visit Modal */}
      <Modal
        isOpen={isBeginVisitOpen}
        onClose={() => setIsBeginVisitOpen(false)}
        title="Begin Store Visit"
      >
        <form onSubmit={handleBeginVisit} className="space-y-4">
          <p className="text-sm text-gray-600">
            Start a new audit visit for <strong>{store.name}</strong> ({store.code}). You can capture shelf photos, analyze merchandising compliance, and track corrective actions.
          </p>

          {visitError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-600">
              {visitError}
            </div>
          )}

          <div>
            <label htmlFor="visit-notes" className="block text-sm font-medium text-gray-700 mb-1">
              Visit Purpose / Initial Notes (Optional)
            </label>
            <textarea
              id="visit-notes"
              rows={3}
              value={visitNotes}
              onChange={(e) => setVisitNotes(e.target.value)}
              placeholder="e.g., Routine endcap audit, Q3 beverage promotion check..."
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsBeginVisitOpen(false)}
              disabled={isCreatingVisit}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isCreatingVisit}>
              {isCreatingVisit ? "Starting Visit..." : "Start Visit"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
