import React from "react";
import type { PolicyVersion, Product } from "@storeops/contracts";
import { RULE_KIND_LABELS, RuleCitation, productLabel } from "./rule-display";

export function ApprovedPolicy({ policy, products }: { policy: PolicyVersion; products: Product[] }) {
  return (
    <section
      className="rounded-lg border border-green-200 bg-white p-5 shadow-sm"
      aria-labelledby="approved-heading"
      data-testid="approved-policy"
    >
      <h2 id="approved-heading" className="text-lg font-semibold text-gray-900">
        Approved policy v{policy.version}
      </h2>
      <p className="mt-1 text-sm text-gray-500">
        Approved {new Date(policy.approved_at).toLocaleString()} &middot; {policy.rules.length} rule
        {policy.rules.length === 1 ? "" : "s"} &middot; {policy.catalog_product_ids.length} product
        {policy.catalog_product_ids.length === 1 ? "" : "s"} covered. Audits check shelves against these rules.
      </p>
      <ul className="mt-4 space-y-3">
        {policy.rules.map((rule) => (
          <li key={rule.rule_id} className="rounded border border-gray-200 p-3">
            <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
              <span className="font-semibold text-gray-900">{RULE_KIND_LABELS[rule.kind]}</span>
              <span className="text-gray-600">
                Zone {rule.zone_id} ({rule.zone_kind.toLowerCase()})
              </span>
              <span className="text-gray-600">{productLabel(rule.product_id, products)}</span>
              {rule.min_facings !== null && <span className="text-gray-600">Min facings: {rule.min_facings}</span>}
            </div>
            <div className="mt-2">
              <RuleCitation source={rule.source} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function PolicyVersionHistory({ versions, error }: { versions: PolicyVersion[]; error: string | null }) {
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm" aria-labelledby="history-heading">
      <h2 id="history-heading" className="text-lg font-semibold text-gray-900">
        Version history
      </h2>
      {error && (
        <div role="alert" className="mt-3 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Could not load version history: {error}
        </div>
      )}
      {!error && versions.length === 0 && <p className="mt-2 text-sm text-gray-600">No approved versions yet.</p>}
      {versions.length > 0 && (
        <ol className="mt-3 divide-y divide-gray-100 text-sm" data-testid="policy-versions">
          {[...versions]
            .sort((a, b) => b.version - a.version)
            .map((v) => (
              <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span className="font-medium text-gray-900">v{v.version}</span>
                <span className="text-gray-600">
                  {v.rules.length} rule{v.rules.length === 1 ? "" : "s"}
                </span>
                <span className="text-gray-500">{new Date(v.approved_at).toLocaleString()}</span>
                <span className="font-mono text-xs text-gray-400" title={v.content_sha256}>
                  {v.content_sha256.slice(0, 12)}
                </span>
              </li>
            ))}
        </ol>
      )}
    </section>
  );
}
