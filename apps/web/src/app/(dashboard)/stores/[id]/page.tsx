"use client";

import React, { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "../../../../lib/api-client";
import {
  formatStock,
  formatOpportunityProxy,
  formatFreshness,
} from "../../../../lib/formatters";
import type { Store, Visit, Schemas } from "@storeops/contracts";
import { Button } from "../../../../components/ui/button";
import { Badge, type BadgeVariant } from "../../../../components/ui/badge";
import { Modal } from "../../../../components/ui/modal";
import { Table, type Column } from "../../../../components/ui/table";

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
  const [healthError, setHealthError] = useState<string | null>(null);
  const [visitsError, setVisitsError] = useState<string | null>(null);

  // Begin Visit modal
  const [isBeginVisitOpen, setIsBeginVisitOpen] = useState(false);
  const [visitNotes, setVisitNotes] = useState("");
  const [isCreatingVisit, setIsCreatingVisit] = useState(false);
  const [visitError, setVisitError] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    try {
      const healthData = await apiClient.getStoreHealth(storeId);
      setHealth(healthData);
      setHealthError(null);
    } catch (err: unknown) {
      console.error("Failed to load store health:", err);
      setHealthError(err instanceof Error ? err.message : "Failed to load store health metrics");
      setHealth(null);
    }
  }, [storeId]);

  const loadVisits = useCallback(async () => {
    try {
      const visitsData = await apiClient.listVisits({ store_id: storeId });
      setVisits(visitsData.items);
      setVisitsError(null);
    } catch (err: unknown) {
      console.error("Failed to load visits:", err);
      setVisitsError(err instanceof Error ? err.message : "Failed to load visits");
      setVisits([]);
    }
  }, [storeId]);

  const loadStoreData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const storeData = await apiClient.getStore(storeId);
      setStore(storeData);
      await Promise.all([loadHealth(), loadVisits()]);
    } catch (err: unknown) {
      console.error("Failed to load store details:", err);
      setError(err instanceof Error ? err.message : "Failed to load store details");
    } finally {
      setLoading(false);
    }
  }, [storeId, loadHealth, loadVisits]);

  useEffect(() => {
    if (storeId) {
      loadStoreData();
    }
  }, [storeId, loadStoreData]);

  const handleBeginVisit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsCreatingVisit(true);
    setVisitError(null);
    try {
      const newVisit = await apiClient.createVisit({
        store_id: storeId,
        notes: visitNotes.trim() || "Routine store audit visit",
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

  const visitColumns: Column<Visit>[] = [
    {
      key: "created_at",
      header: "Date / Created",
      render: (v) => (
        <span className="text-sm font-medium text-gray-900">
          {formatFreshness(v.created_at)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (v) => (
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
      ),
    },
    {
      key: "notes",
      header: "Notes",
      render: (v) => (
        <span className="text-sm text-gray-600 truncate max-w-xs block">
          {v.notes || "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      render: (v) => (
        <Link href={`/visits/${v.id}`}>
          <Button variant="outline" size="sm">
            View Visit
          </Button>
        </Link>
      ),
    },
  ];

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        Loading store details...
      </div>
    );
  }

  if (error || !store) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
        <h3 className="text-lg font-medium text-red-800">Store Not Found</h3>
        <p className="mt-2 text-sm text-red-600">{error || "Could not retrieve store information."}</p>
        <Link href="/catalog" className="mt-4 inline-block">
          <Button variant="outline">Back to Catalog</Button>
        </Link>
      </div>
    );
  }

  const freshnessVariant: BadgeVariant =
    health?.freshness === "CURRENT"
      ? "success"
      : health?.freshness === "STALE"
      ? "warning"
      : "neutral";

  const opportunityAmountNum = health?.metrics?.opportunity_proxy
    ? parseFloat(health.metrics.opportunity_proxy)
    : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-gray-200 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-gray-900">{store.name}</h1>
            <Badge variant={store.active ? "success" : "neutral"}>
              {store.active ? "Active" : "Inactive"}
            </Badge>
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Store Code: <span className="font-mono font-medium">{store.code}</span> • {store.retailer} • {store.region} • Format: {store.format}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Link href="/catalog">
            <Button variant="outline">Catalog</Button>
          </Link>
          <Button onClick={() => setIsBeginVisitOpen(true)}>
            Begin Visit
          </Button>
        </div>
      </div>

      {/* Health Metrics Header Cards */}
      {healthError ? (
        <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex justify-between items-center">
          <div>
            <span className="font-semibold">Failed to load health metrics:</span> {healthError}
          </div>
          <Button variant="outline" size="sm" onClick={loadHealth}>Retry</Button>
        </div>
      ) : (
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
              {formatOpportunityProxy(opportunityAmountNum, store.currency)}
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
              {formatStock(null)}
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
              {formatStock(null)}
            </div>
            <div className="text-xs text-gray-400 mt-1">
              Source: Distribution center
            </div>
          </div>
        </div>
      )}

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
                  <span className="inline-block w-2 h-2 rounded-full bg-green-500" />
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
            {health?.metrics?.sales_delta ? `${health.metrics.sales_delta}%` : "No sales data"}
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

        {visitsError ? (
          <div className="p-4 bg-red-50 border border-red-200 text-red-700 rounded-md flex justify-between items-center">
            <div>
              <span className="font-semibold">Failed to load visits:</span> {visitsError}
            </div>
            <Button variant="outline" size="sm" onClick={loadVisits}>Retry</Button>
          </div>
        ) : (
          <Table<Visit>
            columns={visitColumns}
            data={visits}
            keyExtractor={(v) => v.id}
            emptyMessage="No visits recorded for this store yet."
          />
        )}
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
