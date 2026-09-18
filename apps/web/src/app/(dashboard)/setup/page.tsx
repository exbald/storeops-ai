"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "../../../lib/auth-context";
import { apiClient } from "../../../lib/api-client";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";

interface ChecklistItem {
  id: string;
  title: string;
  description: string;
  href: string;
  actionText: string;
  count: number | null;
  isComplete: boolean;
}

export default function SetupPage() {
  const { activeWorkspaceName } = useAuth();
  const [loading, setLoading] = useState(true);
  const [storeCount, setStoreCount] = useState<number>(0);
  const [productCount, setProductCount] = useState<number>(0);
  const [importCount, setImportCount] = useState<number>(0);
  const [policyCount, setPolicyCount] = useState<number>(0);

  useEffect(() => {
    async function fetchCounts() {
      setLoading(true);
      try {
        const [storesRes, productsRes, importsRes, promosRes] = await Promise.all([
          apiClient.listStores(),
          apiClient.listProducts(),
          apiClient.listImports(),
          apiClient.listPromotions(),
        ]);
        setStoreCount(storesRes.items.length);
        setProductCount(productsRes.items.length);
        const committedImports = importsRes.items.filter((i) => i.status === "COMMITTED");
        setImportCount(committedImports.length);
        const approvedPromos = promosRes.items.filter((p) => p.approved_policy !== null);
        setPolicyCount(approvedPromos.length);
      } catch (err) {
        console.error("Failed to load workspace setup counts:", err);
      } finally {
        setLoading(false);
      }
    }
    fetchCounts();
  }, []);

  const checklist: ChecklistItem[] = [
    {
      id: "stores",
      title: "1. Store Network Configuration",
      description: "Define retail stores, regions, formats, and linked distributor warehouse locations.",
      href: "/stores",
      actionText: "Manage Stores",
      count: storeCount,
      isComplete: storeCount > 0,
    },
    {
      id: "catalog",
      title: "2. Product Catalog & Case Sizes",
      description: "Register SKUs, master case units, and optional reference media for multimodal matching.",
      href: "/catalog",
      actionText: "Manage Catalog",
      count: productCount,
      isComplete: productCount > 0,
    },
    {
      id: "imports",
      title: "3. Sales & Inventory Imports",
      description: "Upload and validate daily store sales and distributor stock CSVs for baseline metrics.",
      href: "/imports",
      actionText: "Upload CSVs",
      count: importCount,
      isComplete: importCount > 0,
    },
    {
      id: "promotions",
      title: "4. Vendor Agreement & Merchandising Policy",
      description: "Extract planogram and facing requirements from vendor agreements and record admin approval.",
      href: "/promotions",
      actionText: "Review Policies",
      count: policyCount,
      isComplete: policyCount > 0,
    },
  ];

  const completedCount = checklist.filter((item) => item.isComplete).length;
  const isFullySetup = completedCount === checklist.length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Workspace Setup Checklist</h1>
          <p className="text-sm text-gray-500 mt-1">
            Persisted onboarding requirements for <span className="font-semibold">{activeWorkspaceName}</span>
          </p>
        </div>
        <div>
          <Badge
            variant={isFullySetup ? "success" : "warning"}
            labelPrefix="Readiness Status:"
            className="text-sm px-3 py-1"
          >
            {isFullySetup ? "Workspace Ready for Field Visits" : `Setup In Progress (${completedCount}/4 Completed)`}
          </Badge>
        </div>
      </div>

      {/* Empty Workspace Guidance */}
      {!isFullySetup && (
        <div className="rounded-lg bg-blue-50 border border-blue-200 p-4">
          <h2 className="text-sm font-semibold text-blue-900 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-600" width="20" height="20" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            Empty Workspace Setup Guidance
          </h2>
          <p className="mt-1 text-sm text-blue-800">
            This workspace contains no preloaded sample data. Follow the 4-step checklist below to configure your
            real store network, product catalog, sales baselines, and merchandising agreements. Field reps cannot
            conduct compliance visits until required prerequisites are established.
          </p>
        </div>
      )}

      {/* Checklist Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {checklist.map((item) => (
          <div
            key={item.id}
            className={`p-6 rounded-lg border transition-all ${
              item.isComplete
                ? "bg-white border-green-200 shadow-sm"
                : "bg-white border-gray-200 shadow-sm"
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="space-y-1">
                <h3 className="text-base font-semibold text-gray-900">{item.title}</h3>
                <p className="text-sm text-gray-500">{item.description}</p>
              </div>
              <Badge variant={item.isComplete ? "success" : "neutral"} labelPrefix="Step Status:">
                {item.isComplete ? "Configured" : "Action Needed"}
              </Badge>
            </div>

            <div className="mt-6 flex items-center justify-between border-t border-gray-100 pt-4">
              <div className="text-sm">
                <span className="text-gray-500">Persisted Records: </span>
                <span className="font-semibold text-gray-900">
                  {loading ? "..." : item.count}
                </span>
              </div>
              <Link href={item.href}>
                <Button variant={item.isComplete ? "outline" : "primary"} size="sm">
                  {item.actionText}
                </Button>
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
