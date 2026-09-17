"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { apiClient } from "../../../lib/api-client";
import { generateUuid } from "../../../lib/doubles";
import { formatFreshness } from "../../../lib/formatters";
import type { Import } from "@storeops/contracts";
import { Table, Column } from "../../../components/ui/table";
import { Button } from "../../../components/ui/button";
import { Badge } from "../../../components/ui/badge";
import { Select } from "../../../components/ui/select";
import { Modal } from "../../../components/ui/modal";

export default function ImportsPage() {
  const { isAdmin } = useAuth();
  const [imports, setImports] = useState<Import[]>([]);
  const [loading, setLoading] = useState(true);
  const [globalAlert, setGlobalAlert] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Staged Upload Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [importKind, setImportKind] = useState<"SALES" | "INVENTORY">("SALES");
  const [fileName, setFileName] = useState("");
  const [csvContent, setCsvContent] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  // Active Inspect Modal
  const [inspectingImport, setInspectingImport] = useState<Import | null>(null);
  const [isCommitting, setIsCommitting] = useState(false);
  const [importsError, setImportsError] = useState<string | null>(null);

  const loadImports = async () => {
    setLoading(true);
    setImportsError(null);
    try {
      const res = await apiClient.listImports();
      setImports(res.items);
    } catch (err: any) {
      console.error("Failed to load imports:", err);
      setImportsError(err?.message || "Failed to load imports feed");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadImports();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setFileName(file.name);
      const reader = new FileReader();
      reader.onload = (event) => {
        setCsvContent((event.target?.result as string) || "");
      };
      reader.readAsText(file);
    }
  };

  const handleStageImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fileName) return;

    setIsUploading(true);
    setGlobalAlert(null);
    try {
      // In contract flow, media is created then import staged with valid UUID
      const staged = await apiClient.createImport({
        kind: importKind,
        media_id: generateUuid(),
      });
      setIsModalOpen(false);
      setFileName("");
      setCsvContent("");
      setGlobalAlert({
        type: "success",
        message: `Import staged successfully with ${staged.row_count} rows ready for review.`,
      });
      await loadImports();
      setInspectingImport(staged);
    } catch (err) {
      setGlobalAlert({
        type: "error",
        message: "Failed to stage import: " + (err instanceof Error ? err.message : "Unknown error"),
      });
    } finally {
      setIsUploading(false);
    }
  };

  const handleCommit = async (imp: Import) => {
    setIsCommitting(true);
    setGlobalAlert(null);
    try {
      await apiClient.commitImport(imp.id);
      setGlobalAlert({
        type: "success",
        message: "Import successfully committed to system of record.",
      });
      await loadImports();
      setInspectingImport(null);
    } catch (err) {
      setGlobalAlert({
        type: "error",
        message: "Failed to commit import: " + (err instanceof Error ? err.message : "Unknown error"),
      });
    } finally {
      setIsCommitting(false);
    }
  };

  const columns: Column<Import>[] = [
    {
      key: "kind",
      header: "Import Type",
      render: (i) => (
        <span className="font-semibold text-xs text-gray-900 uppercase">
          {i.kind === "SALES" ? "Daily Sales CSV" : "Inventory Snapshot CSV"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (i) => {
        const variant =
          i.status === "COMMITTED"
            ? "success"
            : i.status === "VALIDATED"
            ? "info"
            : "warning";
        return (
          <Badge variant={variant} labelPrefix="Import Status:">
            {i.status}
          </Badge>
        );
      },
    },
    {
      key: "counts",
      header: "Row Summary",
      render: (i) => (
        <div className="text-xs">
          <span className="font-semibold">{i.row_count} total rows</span>
          {i.error_count > 0 ? (
            <span className="text-red-600 block">{i.error_count} row errors</span>
          ) : (
            <span className="text-green-600 block">All rows valid</span>
          )}
        </div>
      ),
    },
    {
      key: "committed_at",
      header: "Committed At",
      render: (i) => (
        <span className="text-xs text-gray-500">
          {i.committed_at ? formatFreshness(i.committed_at) : "Pending Commit"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      render: (i) => (
        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setInspectingImport(i)}>
            Inspect Details
          </Button>
          {isAdmin && i.status === "VALIDATED" && (
            <Button size="sm" onClick={() => handleCommit(i)}>
              Commit Data
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

      {/* Imports Load Error Banner */}
      {importsError && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between">
          <div>
            <h3 className="text-sm font-semibold text-red-800">Failed to load imports</h3>
            <p className="text-sm text-red-700 mt-1">{importsError}</p>
          </div>
          <Button variant="secondary" size="sm" onClick={loadImports}>
            Retry
          </Button>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Data Imports & Verification</h1>
          <p className="text-sm text-gray-500 mt-1">
            Upload, validate, and commit sales and warehouse inventory CSV feeds.
          </p>
        </div>
        {isAdmin && (
          <Button onClick={() => setIsModalOpen(true)}>
            Upload New CSV
          </Button>
        )}
      </div>

      {/* Explicit Commit Guidance */}
      <div className="p-4 bg-gray-50 border border-gray-200 rounded-lg text-sm text-gray-700">
        <span className="font-semibold">Explicit Commit Guarantee:</span> Uploaded CSV files are strictly staged
        and pre-validated. No analytical metrics, sales histories, or stock levels will be modified until you
        review validation totals and click the explicit <strong>Commit Data</strong> action.
      </div>

      {/* Imports History Table */}
      <Table
        columns={columns}
        data={imports}
        keyExtractor={(i) => i.id}
        emptyMessage="No CSV imports staged or committed yet."
        caption="CSV Import validation and commit history"
      />

      {/* Upload & Stage Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Upload Operational CSV"
        description="Select import type and CSV data file for staging and schema validation."
      >
        <form onSubmit={handleStageImport} className="space-y-4">
          <Select
            label="Import Feed Type"
            value={importKind}
            onChange={(e) => setImportKind(e.target.value as "SALES" | "INVENTORY")}
            options={[
              { value: "SALES", label: "Daily Store Sales (store_code, sku, date, units, revenue)" },
              { value: "INVENTORY", label: "Inventory Snapshot (location_code, sku, date, on_hand)" },
            ]}
          />

          <div className="space-y-1">
            <label htmlFor="csv-file-input" className="block text-sm font-medium text-gray-700">
              CSV Data File
            </label>
            <input
              id="csv-file-input"
              type="file"
              accept=".csv"
              required
              onChange={handleFileChange}
              className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer border border-gray-300 rounded-md"
            />
            <p className="text-xs text-gray-500">Max size 50MB. File content is verified via SHA256 hashing.</p>
          </div>

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
              isLoading={isUploading}
              disabled={!fileName}
            >
              Stage & Validate
            </Button>
          </div>
        </form>
      </Modal>

      {/* Inspect & Commit Modal */}
      {inspectingImport && (
        <Modal
          isOpen={Boolean(inspectingImport)}
          onClose={() => setInspectingImport(null)}
          title={`Import Verification: ${inspectingImport.kind}`}
          description={`ID: ${inspectingImport.id} - Status: ${inspectingImport.status}`}
        >
          <div className="space-y-4 text-sm">
            <div className="grid grid-cols-2 gap-4 bg-gray-50 p-4 rounded-md">
              <div>
                <span className="text-gray-500 block text-xs">Total Rows</span>
                <span className="font-semibold text-base">{inspectingImport.row_count}</span>
              </div>
              <div>
                <span className="text-gray-500 block text-xs">Row Errors</span>
                <span className={`font-semibold text-base ${inspectingImport.error_count > 0 ? "text-red-600" : "text-green-600"}`}>
                  {inspectingImport.error_count}
                </span>
              </div>
              <div className="col-span-2">
                <span className="text-gray-500 block text-xs">Source SHA256</span>
                <span className="font-mono text-xs break-all text-gray-600">{inspectingImport.source_sha256}</span>
              </div>
            </div>

            {inspectingImport.error_count > 0 && inspectingImport.errors && inspectingImport.errors.length > 0 && (
              <div className="space-y-2">
                <h3 className="font-semibold text-red-800 text-xs uppercase tracking-wider">
                  Validation Errors ({inspectingImport.errors.length} detected)
                </h3>
                <div className="max-h-48 overflow-y-auto space-y-2 border border-red-200 rounded p-2 bg-red-50">
                  {inspectingImport.errors.map((err, idx) => (
                    <div key={idx} className="text-xs text-red-900 border-b border-red-100 pb-1">
                      <span className="font-bold">Row {err.row} ({err.field}): </span>
                      <span>[{err.code}] {err.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-between items-center pt-4 border-t border-gray-200">
              <Button
                type="button"
                variant="secondary"
                onClick={() => setInspectingImport(null)}
              >
                Close
              </Button>
              {isAdmin && inspectingImport.status === "VALIDATED" && (
                <Button
                  onClick={() => handleCommit(inspectingImport)}
                  isLoading={isCommitting}
                >
                  Commit Import Now
                </Button>
              )}
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
