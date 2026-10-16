"use client";

import React from "react";
import Link from "next/link";
import type { Rule, Verification } from "@storeops/contracts";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { formatFreshness } from "../../lib/formatters";
import { describeRule } from "../../lib/investigation-labels";
import type { EvidenceItem } from "../../lib/use-investigation-evidence";
import { EvidenceThumbnails } from "./evidence-thumbnails";

export interface VerificationResultsProps {
  verifications: Verification[];
  rulesById: Record<string, Rule>;
  evidenceById: Record<string, EvidenceItem>;
  evidenceLoading: boolean;
}

const RESULT_TEXT: Record<string, string> = {
  PASS: "Fixed: every rule passed",
  FAIL: "Not fixed: at least one rule failed",
  PARTIAL: "Partly fixed",
  INCONCLUSIVE: "Could not tell from the photos",
};

function resultVariant(result: string | null): "success" | "danger" | "warning" {
  if (result === "PASS") return "success";
  if (result === "FAIL") return "danger";
  return "warning";
}

function CheckRow({
  check,
  rule,
  evidenceById,
  evidenceLoading,
}: {
  check: Verification["checks"][number];
  rule: Rule | undefined;
  evidenceById: Record<string, EvidenceItem>;
  evidenceLoading: boolean;
}) {
  const passed = check.result === "PASS";
  const failed = check.result === "FAIL";
  return (
    <li
      className={`p-3 rounded border flex flex-col sm:flex-row sm:items-start gap-3 ${
        passed ? "bg-green-50 border-green-200" : failed ? "bg-red-50 border-red-200" : "bg-amber-50 border-amber-200"
      }`}
    >
      <span
        className={`shrink-0 inline-flex items-center justify-center w-14 py-1 rounded text-xs font-bold ${
          passed ? "bg-green-600 text-white" : failed ? "bg-red-600 text-white" : "bg-amber-500 text-white"
        }`}
      >
        {passed ? "PASS" : failed ? "FAIL" : "UNSURE"}
      </span>
      <div className="flex-1 space-y-2 min-w-0">
        <p className="text-sm font-semibold text-gray-900">
          {rule ? describeRule(rule) : `Rule ${check.rule_id.slice(0, 8)}`}
        </p>
        <p className="text-sm text-gray-700">{check.explanation}</p>
        <EvidenceThumbnails evidenceIds={check.evidence_ids} evidenceById={evidenceById} loading={evidenceLoading} />
      </div>
    </li>
  );
}

export function VerificationResults({ verifications, rulesById, evidenceById, evidenceLoading }: VerificationResultsProps) {
  if (verifications.length === 0) return null;
  const ordered = [...verifications].sort((a, b) => b.created_at.localeCompare(a.created_at));

  return (
    <section className="bg-white p-5 rounded-lg border border-gray-200 shadow-sm space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">3. Verification results</h2>
        <p className="text-xs text-gray-500">Each after-photo is checked against every rule in the approved agreement.</p>
      </div>
      <div className="space-y-6">
        {ordered.map((v, i) => (
          <div key={v.id} className={i > 0 ? "pt-6 border-t border-gray-100 space-y-3" : "space-y-3"}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={resultVariant(v.result)} labelPrefix="Verification result:">
                  {v.result ?? "PENDING"}
                </Badge>
                <span className="text-sm font-semibold text-gray-900">
                  {v.result ? RESULT_TEXT[v.result] : "Verification in progress"}
                </span>
                {i === 0 && ordered.length > 1 && <span className="text-xs text-gray-500">(latest)</span>}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-gray-500">Checked {formatFreshness(v.created_at)}</span>
                {v.report_id && (
                  <Link href={`/reports/${v.report_id}`}>
                    <Button variant="outline" size="sm">
                      View report
                    </Button>
                  </Link>
                )}
              </div>
            </div>
            {v.checks.length > 0 && (
              <ul className="space-y-2">
                {v.checks.map((check) => (
                  <CheckRow
                    key={`${v.id}-${check.rule_id}`}
                    check={check}
                    rule={rulesById[check.rule_id]}
                    evidenceById={evidenceById}
                    evidenceLoading={evidenceLoading}
                  />
                ))}
              </ul>
            )}
            {v.requested_retakes.length > 0 && (
              <div className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded p-3">
                <span className="font-semibold">Retake requested:</span> {v.requested_retakes.join(" ")}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
