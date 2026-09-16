"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useAuth } from "../../../lib/auth-context";
import { apiClient, VersionConflictError } from "../../../lib/api-client";
import { formatOpportunityProxy } from "../../../lib/formatters";
import type { Store, Location } from "@storeops/contracts";
import { Table, Column } from "../../../components/ui/table";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Select } from "../../../components/ui/select";
import { Badge } from "../../../components/ui/badge";
import { Modal } from "../../../components/ui/modal";

export default function StoresPage() {
  const { isAdmin } = useAuth();
  const [stores, setStores] = useState<Store[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterActive, setFilterActive] = useState<string>("all");

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStore, setEditingStore] = useState<Store | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [conflictWarning, setConflictWarning] = useState<string | null>(null);
  const [globalAlert, setGlobalAlert] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Form Fields
  const [formCode, setFormCode] = useState("");
  const [formName, setFormName] = useState("");
  const [formRetailer, setFormRetailer] = useState("FairPrice");
  const [formRegion, setFormRegion] = useState("Central");
  const [formFormat, setFormFormat] = useState("SUPERMARKET");
  const [formTimezone, setFormTimezone] = useState("Asia/Singapore");
  const [formLocationId, setFormLocationId] = useState<string>("");

  const loadData = async () => {
    setLoading(true);
    setConflictWarning(null);
    try {
      const [storeRes, locRes] = await Promise.all([
        apiClient.listStores(),
        apiClient.listLocations(),
      ]);
      setStores(storeRes.items);
      setLocations(locRes.items);
    } catch (err) {
      console.error("Failed to load stores:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const openCreateModal = () => {
    setEditingStore(null);
    setFormCode("");
    setFormName("");
    setFormRetailer("FairPrice");
    setFormRegion("Central");
    setFormFormat("SUPERMARKET");
    setFormTimezone("Asia/Singapore");
    setFormLocationId(locations[0]?.id || "");
    setErrorMessage(null);
    setConflictWarning(null);
    setIsModalOpen(true);
  };

  const openEditModal = (store: Store) => {
    setEditingStore(store);
    setFormCode(store.code);
    setFormName(store.name);
    setFormRetailer(store.retailer);
    setFormRegion(store.region);
    setFormFormat(store.format);
    setFormTimezone(store.timezone);
    setFormLocationId(store.distributor_location_id || "");
    setErrorMessage(null);
    setConflictWarning(null);
    setIsModalOpen(true);
  };

  const handleSaveStore = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setErrorMessage(null);
    setConflictWarning(null);

    try {
      if (editingStore) {
        await apiClient.updateStore(editingStore.id, {
          expected_version: editingStore.version,
          name: formName,
        });
      } else {
        await apiClient.createStore({
          code: formCode,
          name: formName,
          retailer: formRetailer,
          region: formRegion,
          format: formFormat,
          timezone: formTimezone,
          distributor_location_id: formLocationId || null,
        });
      }
      setIsModalOpen(false);
      await loadData();
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setConflictWarning(err.message);
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleArchiveToggle = async (store: Store) => {
    if (!isAdmin) return;
    try {
      await apiClient.updateStore(store.id, {
        expected_version: store.version,
        active: !store.active,
      });
      setGlobalAlert({
        type: "success",
        message: `Store ${store.code} ${store.active ? "archived" : "restored"} successfully.`,
      });
      await loadData();
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setConflictWarning(err.message);
        await loadData();
      } else {
        setGlobalAlert({
          type: "error",
          message: "Failed to update store status: " + (err instanceof Error ? err.message : "Unknown error"),
        });
      }
    }
  };

  const filteredStores = useMemo(() => {
    return stores.filter((s) => {
      const matchesSearch =
        s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.retailer.toLowerCase().includes(searchQuery.toLowerCase());

      if (filterActive === "active") return matchesSearch && s.active;
      if (filterActive === "archived") return matchesSearch && !s.active;
      return matchesSearch;
    });
  }, [stores, searchQuery, filterActive]);

  const columns: Column<Store>[] = [
    {
      key: "code",
      header: "Store Code",
      render: (s) => <span className="font-mono text-xs font-semibold">{s.code}</span>,
    },
    {
      key: "name",
      header: "Store Name",
      render: (s) => (
        <div>
          <div className="font-medium text-gray-900">{s.name}</div>
          <div className="text-xs text-gray-500">{s.region} &bull; {s.format}</div>
        </div>
      ),
    },
    {
      key: "retailer",
      header: "Retailer",
    },
    {
      key: "opportunity",
      header: "Opportunity Proxy",
      render: () => (
        <span className="text-sm font-medium text-amber-700">
          {/* Sourced from specs/04-ui.md: "A null opportunity proxy is 'Insufficient comparison data', not SGD 0.00." */}
          {formatOpportunityProxy(null)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (s) => (
        <Badge variant={s.active ? "success" : "neutral"} labelPrefix="Store Status:">
          {s.active ? "Active" : "Archived"}
        </Badge>
      ),
    },
    {
      key: "version",
      header: "Version",
      render: (s) => <span className="text-xs text-gray-400 font-mono">v{s.version}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      render: (s) => (
        <div className="flex items-center justify-end gap-2">
          {isAdmin && (
            <>
              <Button variant="ghost" size="sm" onClick={() => openEditModal(s)}>
                Edit
              </Button>
              <Button
                variant={s.active ? "ghost" : "outline"}
                size="sm"
                onClick={() => handleArchiveToggle(s)}
              >
                {s.active ? "Archive" : "Restore"}
              </Button>
            </>
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
          <h1 className="text-2xl font-bold text-gray-900">Retail Stores</h1>
          <p className="text-sm text-gray-500 mt-1">
            Store directory, format classifications, and comparative peer gap baselines.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={openCreateModal}>
            Add New Store
          </Button>
        )}
      </div>

      {/* Global Conflict Warning Banner */}
      {conflictWarning && (
        <div className="p-4 bg-amber-50 border border-amber-300 rounded-md text-amber-900 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Version Conflict:</span>
            <span>{conflictWarning}</span>
          </div>
          <Button variant="secondary" size="sm" onClick={loadData}>
            Refresh Store List
          </Button>
        </div>
      )}

      {/* Search & Filter Controls */}
      <div className="flex flex-col sm:flex-row gap-4 bg-white p-4 rounded-lg border border-gray-200">
        <div className="flex-1">
          <Input
            label="Search Stores"
            placeholder="Search by store name, code, or retailer..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="w-full sm:w-48">
          <Select
            label="Filter by Status"
            value={filterActive}
            onChange={(e) => setFilterActive(e.target.value)}
            options={[
              { value: "all", label: "All Stores" },
              { value: "active", label: "Active Only" },
              { value: "archived", label: "Archived Only" },
            ]}
          />
        </div>
      </div>

      {/* Stores Table */}
      <Table
        columns={columns}
        data={filteredStores}
        keyExtractor={(s) => s.id}
        emptyMessage={
          searchQuery
            ? "No stores match your search criteria."
            : "No stores found. Create your first store to get started."
        }
        caption="List of retail stores in workspace"
      />

      {/* Create / Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingStore ? `Edit Store: ${editingStore.name}` : "Create New Store"}
        description="Configure store metadata and linked distributor location."
      >
        <form onSubmit={handleSaveStore} className="space-y-4">
          {conflictWarning && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {conflictWarning}
            </div>
          )}
          {errorMessage && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {errorMessage}
            </div>
          )}

          <Input
            label="Store Code"
            required
            disabled={Boolean(editingStore)}
            value={formCode}
            onChange={(e) => setFormCode(e.target.value)}
            placeholder="e.g. STR-003"
            helperText={editingStore ? "Store codes are immutable." : "Alphanumeric unique identifier."}
          />

          <Input
            label="Store Name"
            required
            value={formName}
            onChange={(e) => setFormName(e.target.value)}
            placeholder="e.g. Orchard Road Flagship"
          />

          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Retailer"
              required
              disabled={Boolean(editingStore)}
              value={formRetailer}
              onChange={(e) => setFormRetailer(e.target.value)}
            />
            <Input
              label="Region"
              required
              disabled={Boolean(editingStore)}
              value={formRegion}
              onChange={(e) => setFormRegion(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Select
              label="Format"
              disabled={Boolean(editingStore)}
              value={formFormat}
              onChange={(e) => setFormFormat(e.target.value)}
              options={[
                { value: "SUPERMARKET", label: "Supermarket" },
                { value: "HYPERMARKET", label: "Hypermarket" },
                { value: "CONVENIENCE", label: "Convenience" },
                { value: "MINIMART", label: "Minimart" },
              ]}
            />
            <Input
              label="Timezone"
              required
              disabled={Boolean(editingStore)}
              value={formTimezone}
              onChange={(e) => setFormTimezone(e.target.value)}
            />
          </div>

          {!editingStore && locations.length > 0 && (
            <Select
              label="Distributor Location"
              value={formLocationId}
              onChange={(e) => setFormLocationId(e.target.value)}
              options={[
                { value: "", label: "No linked distributor location" },
                ...locations.map((loc) => ({
                  value: loc.id,
                  label: `${loc.name} (${loc.code})`,
                })),
              ]}
            />
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              isLoading={isSaving}
            >
              {editingStore ? "Update Store" : "Create Store"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
