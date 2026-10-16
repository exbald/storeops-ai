"use client";

import React, { useMemo, useState } from "react";
import type { Product, Rule } from "@storeops/contracts";
import { Button } from "../ui/button";
import { RULE_KIND_LABELS, RuleCitation, productLabel, referencedProductIds } from "./rule-display";

const MAX_RULES = 30;
const MAX_CATALOG_PRODUCTS = 25;

export interface ProposedRulesReviewProps {
  rules: Rule[];
  gaps: string[];
  products: Product[];
  agreementMediaId: string | null;
  canApprove: boolean;
  isApproving: boolean;
  error: string | null;
  onApprove: (rules: Rule[], catalogProductIds: string[]) => void;
}

/** A DOCUMENT rule cited from an agreement that has since been replaced cannot be approved. */
function isStale(rule: Rule, agreementMediaId: string | null): boolean {
  return rule.source.kind === "DOCUMENT" && rule.source.media_id !== agreementMediaId;
}

export function ProposedRulesReview({
  rules,
  gaps,
  products,
  agreementMediaId,
  canApprove,
  isApproving,
  error,
  onApprove,
}: ProposedRulesReviewProps) {
  const [included, setIncluded] = useState<string[]>(() =>
    rules.filter((r) => !isStale(r, agreementMediaId)).map((r) => r.rule_id)
  );
  const [extraProductIds, setExtraProductIds] = useState<string[]>([]);

  const includedRules = useMemo(() => rules.filter((r) => included.includes(r.rule_id)), [rules, included]);
  const requiredProductIds = useMemo(() => referencedProductIds(includedRules), [includedRules]);
  const catalogProductIds = useMemo(
    () => [...requiredProductIds, ...extraProductIds.filter((id) => !requiredProductIds.includes(id))],
    [requiredProductIds, extraProductIds]
  );

  const toggleRule = (ruleId: string, on: boolean) =>
    setIncluded((prev) => (on ? [...prev, ruleId] : prev.filter((id) => id !== ruleId)));
  const toggleExtraProduct = (productId: string, on: boolean) =>
    setExtraProductIds((prev) => (on ? [...prev, productId] : prev.filter((id) => id !== productId)));

  const blocker =
    includedRules.length === 0
      ? "Include at least one rule to approve."
      : includedRules.length > MAX_RULES
        ? `A policy can hold at most ${MAX_RULES} rules.`
        : catalogProductIds.length === 0
          ? "Pick at least one catalog product this policy covers."
          : catalogProductIds.length > MAX_CATALOG_PRODUCTS
            ? `A policy can cover at most ${MAX_CATALOG_PRODUCTS} products.`
            : null;

  return (
    <div className="space-y-5">
      {gaps.length > 0 && (
        <section
          className="rounded-lg border border-amber-300 bg-amber-50 p-4"
          aria-labelledby="gaps-heading"
          data-testid="extraction-gaps"
        >
          <h3 id="gaps-heading" className="text-sm font-semibold text-amber-900">
            Needs your input ({gaps.length})
          </h3>
          <p className="mt-1 text-xs text-amber-800">
            Gemini found these in the agreement but could not turn them into a complete rule. They are not part of
            the policy unless you add them.
          </p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900">
            {gaps.map((gap, i) => (
              <li key={`${i}-${gap.slice(0, 24)}`}>{gap}</li>
            ))}
          </ul>
        </section>
      )}

      {rules.length === 0 ? (
        <p className="text-sm text-gray-600">No proposed rules yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <caption className="sr-only">Rules proposed from the agreement</caption>
            <thead className="bg-gray-50 text-left text-xs font-semibold uppercase text-gray-500">
              <tr>
                <th scope="col" className="px-3 py-2">Include</th>
                <th scope="col" className="px-3 py-2">Rule</th>
                <th scope="col" className="px-3 py-2">Zone</th>
                <th scope="col" className="px-3 py-2">Product</th>
                <th scope="col" className="px-3 py-2">Min facings</th>
                <th scope="col" className="px-3 py-2">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white align-top">
              {rules.map((rule) => {
                const stale = isStale(rule, agreementMediaId);
                return (
                  <tr key={rule.rule_id} data-testid="proposed-rule">
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Include ${RULE_KIND_LABELS[rule.kind]} rule for zone ${rule.zone_id}`}
                        checked={included.includes(rule.rule_id)}
                        disabled={!canApprove || stale}
                        onChange={(e) => toggleRule(rule.rule_id, e.target.checked)}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600"
                      />
                    </td>
                    <td className="px-3 py-3 font-medium text-gray-900">{RULE_KIND_LABELS[rule.kind]}</td>
                    <td className="px-3 py-3 text-gray-700">
                      {rule.zone_id} <span className="text-xs text-gray-500">({rule.zone_kind.toLowerCase()})</span>
                    </td>
                    <td className="px-3 py-3 text-gray-700">{productLabel(rule.product_id, products)}</td>
                    <td className="px-3 py-3 text-gray-700">{rule.min_facings ?? "—"}</td>
                    <td className="min-w-[16rem] px-3 py-3">
                      <RuleCitation source={rule.source} />
                      {stale && (
                        <p className="mt-1 text-xs text-red-700">
                          Cited from a replaced agreement. Extract again to review it.
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {rules.length > 0 && canApprove && (
        <section className="space-y-3" aria-labelledby="catalog-heading">
          <div>
            <h3 id="catalog-heading" className="text-sm font-semibold text-gray-900">
              Products this policy covers
            </h3>
            <p className="text-xs text-gray-500">
              Products named by the included rules are always covered. Add others if the agreement covers them.
            </p>
          </div>
          <div className="max-h-40 space-y-1 overflow-y-auto rounded border border-gray-200 p-2">
            {products.length === 0 && <p className="text-xs text-gray-500">No catalog products found.</p>}
            {products.map((p) => {
              const required = requiredProductIds.includes(p.id);
              return (
                <label key={p.id} className="flex items-center gap-2 text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={required || extraProductIds.includes(p.id)}
                    disabled={required || !p.active}
                    onChange={(e) => toggleExtraProduct(p.id, e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600"
                  />
                  <span>
                    {p.name} <span className="text-xs text-gray-500">({p.sku})</span>
                    {required && <span className="ml-1 text-xs text-gray-500">— used by a rule</span>}
                  </span>
                </label>
              );
            })}
          </div>

          {error && (
            <div role="alert" className="rounded border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              onClick={() => onApprove(includedRules, catalogProductIds)}
              disabled={Boolean(blocker)}
              isLoading={isApproving}
            >
              Approve rules ({includedRules.length})
            </Button>
            <span className="text-xs text-gray-500">{blocker ?? "Approving creates a locked policy version."}</span>
          </div>
        </section>
      )}
    </div>
  );
}
