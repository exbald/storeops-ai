import React from "react";
import type { Product, Rule } from "@storeops/contracts";

export const RULE_KIND_LABELS: Record<Rule["kind"], string> = {
  MIN_FACINGS: "Minimum facings",
  REQUIRED_PRODUCT: "Product must be on shelf",
  REQUIRED_DISPLAY: "Display must be set up",
};

export function productLabel(productId: string | null, products: Product[]): string {
  if (!productId) return "Any product (brand total)";
  const product = products.find((p) => p.id === productId);
  return product ? `${product.name} (${product.sku})` : `Unknown product ${productId}`;
}

/** Product IDs that the given rules reference, de-duplicated in first-seen order. */
export function referencedProductIds(rules: Rule[]): string[] {
  return rules.reduce<string[]>(
    (ids, r) => (r.product_id && !ids.includes(r.product_id) ? [...ids, r.product_id] : ids),
    []
  );
}

/** Where a rule came from: page and verbatim quote for agreement rules, reviewer note for manual ones. */
export function RuleCitation({ source }: { source: Rule["source"] }) {
  if (source.kind === "MANUAL") {
    return (
      <div className="rounded border-l-4 border-gray-400 bg-gray-50 px-3 py-2 text-xs text-gray-700">
        <span className="font-semibold">Added by reviewer:</span> {source.reviewer_note}
      </div>
    );
  }
  return (
    <figure
      className="rounded border-l-4 border-indigo-400 bg-indigo-50 px-3 py-2 text-xs text-indigo-900"
      data-testid="rule-citation"
    >
      <figcaption className="mb-1 font-semibold uppercase tracking-wide text-indigo-700">
        Agreement, page {source.page}
      </figcaption>
      <blockquote className="italic">&ldquo;{source.quote}&rdquo;</blockquote>
      {source.reviewer_note && <p className="mt-1 not-italic text-indigo-800">Note: {source.reviewer_note}</p>}
    </figure>
  );
}
