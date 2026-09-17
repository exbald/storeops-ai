"use client";

import React, { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { apiClient } from "../../../../lib/api-client";
import { formatFreshness } from "../../../../lib/formatters";
import type { Report, Verification, Investigation, Visit } from "@storeops/contracts";
import { Button } from "../../../../components/ui/button";
import { Badge } from "../../../../components/ui/badge";

export default function ReportDetailPage() {
  const params = useParams();
  const router = useRouter();
  const reportId = params.id as string;

  const [report, setReport] = useState<Report | null>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [investigation, setInvestigation] = useState<Investigation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const reportData = await apiClient.getReport(reportId);
      setReport(reportData);

      const [verifData, invData] = await Promise.all([
        apiClient.getVerification(reportData.verification_id).catch(() => null),
        apiClient.getInvestigation(reportData.investigation_id).catch(() => null),
      ]);

      setVerification(verifData);
      setInvestigation(invData);
    } catch (err: unknown) {
      console.error("Failed to load report:", err);
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (reportId) {
      loadData();
    }
  }, [reportId]);

  const handlePrint = () => {
    if (typeof window !== "undefined") {
      window.print();
    }
  };

  if (loading) {
    return (
      <div className="py-12 text-center text-gray-500">
        Loading verification report...
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="py-12 text-center">
        <p className="text-red-600 font-medium mb-4">{error || "Report not found"}</p>
        <Link href="/stores">
          <Button variant="outline">Back to Stores</Button>
        </Link>
      </div>
    );
  }

  const isVerified = report.outcome === "PASS";
  const outcomeVariant =
    report.outcome === "PASS"
      ? "success"
      : report.outcome === "FAIL"
      ? "danger"
      : "warning";

  return (
    <div className="space-y-6 max-w-4xl mx-auto print:p-0">
      {/* Header and Print Controls */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-gray-200 pb-5 print:border-none">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">
              Merchandising Verification Report
            </h1>
            <Badge variant={outcomeVariant}>{report.outcome}</Badge>
            {/* The report says “Execution verified” only after PASS */}
            {isVerified && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-green-100 text-green-800 border border-green-200">
                ✓ Execution verified
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Report ID: <span className="font-mono text-xs">{report.id}</span> • Generated: {formatFreshness(report.created_at)}
          </p>
        </div>

        <div className="flex gap-3 print:hidden">
          <Link href={`/investigations/${report.investigation_id}`}>
            <Button variant="outline">Back to Investigation</Button>
          </Link>
          <Button onClick={handlePrint} variant="outline">
            🖨 Print / Save PDF
          </Button>
        </div>
      </div>

      {/* Report Summary Card */}
      <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm space-y-4 print:shadow-none print:border-gray-300">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">
          Verification Summary
        </h2>
        <p className="text-base text-gray-800 leading-relaxed font-medium">
          {report.summary}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 border-t border-gray-100">
          <div>
            <span className="text-xs text-gray-500 uppercase font-semibold">Overall Outcome</span>
            <div className="text-lg font-bold text-gray-900 mt-0.5">{report.outcome}</div>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase font-semibold">Rules Checked</span>
            <div className="text-lg font-bold text-gray-900 mt-0.5">{report.checks.length}</div>
          </div>
          <div>
            <span className="text-xs text-gray-500 uppercase font-semibold">Evidence Citing Media</span>
            <div className="text-lg font-bold text-gray-900 mt-0.5">{report.evidence_ids.length} photo(s)</div>
          </div>
        </div>
      </div>

      {/* Per-Rule Compliance Checks */}
      <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm space-y-4 print:shadow-none print:border-gray-300">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wider">
          Individual Rule Compliance Checks
        </h2>

        <div className="divide-y divide-gray-100">
          {report.checks.map((chk, idx) => (
            <div key={idx} className="py-4 space-y-2">
              <div className="flex justify-between items-center">
                <span className="font-mono text-xs font-semibold text-gray-700 bg-gray-100 px-2 py-0.5 rounded">
                  Rule: {chk.rule_id}
                </span>
                <Badge
                  variant={
                    chk.result === "PASS"
                      ? "success"
                      : chk.result === "FAIL"
                      ? "danger"
                      : "warning"
                  }
                >
                  {chk.result}
                </Badge>
              </div>

              <p className="text-sm text-gray-800">
                {chk.explanation}
              </p>

              {chk.evidence_ids.length > 0 && (
                <div className="flex items-center gap-2 pt-1">
                  <span className="text-xs text-gray-500">Grounded Evidence:</span>
                  {chk.evidence_ids.map((id) => (
                    <span key={id} className="font-mono text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded">
                      {id.slice(0, 8)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Audit Context */}
      <div className="bg-gray-50 p-4 rounded-lg border border-gray-200 text-xs text-gray-500 space-y-1 print:border-gray-300">
        <div><strong>Visit:</strong> {report.visit_id}</div>
        <div><strong>Investigation:</strong> {report.investigation_id}</div>
        <div><strong>Verification:</strong> {report.verification_id}</div>
        <div className="pt-2 text-[10px] text-gray-400">
          Grounded StoreOps Audit Report. Bounding boxes and optical verification performed by Gemini Multimodal Vision. Causal sales-recovery assertions excluded per specification.
        </div>
      </div>
    </div>
  );
}
