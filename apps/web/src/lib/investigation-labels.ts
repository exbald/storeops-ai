/** Plain-language labels for investigation, action and rule enums. */

import type { Rule } from "@storeops/contracts";

export const HYPOTHESIS_LABELS: Record<string, { title: string; detail: string }> = {
  EXECUTION: {
    title: "Shelf execution problem",
    detail: "The product is available, but the shelf does not match the agreement.",
  },
  SUPPLY_CONSTRAINT: {
    title: "Supply problem",
    detail: "There is not enough stock reaching the store to meet the agreement.",
  },
  UNEXPLAINED_DECLINE: {
    title: "Unexplained sales decline",
    detail: "Sales dropped, but the shelf and stock data do not explain why.",
  },
  NO_ISSUE: {
    title: "No issue found",
    detail: "The shelf and the data are consistent with the agreement.",
  },
  INSUFFICIENT_EVIDENCE: {
    title: "Not enough evidence",
    detail: "More photos or data are needed before drawing a conclusion.",
  },
};

export const CLAIM_KIND_LABELS: Record<string, string> = {
  OBSERVATION: "Seen on shelf",
  POLICY: "Agreement says",
  METRIC: "Data shows",
  HYPOTHESIS: "Conclusion",
};

export const ACTION_KIND_LABELS: Record<string, string> = {
  REPLENISH: "Restock",
  RESTORE_FACINGS: "Restore facings",
  INSTALL_DISPLAY: "Install display",
  CHECK_STOCK: "Check stock",
  REQUEST_SUPPLY: "Request supply",
  RETAKE: "Retake photo",
};

export const STATE_LABELS: Record<string, string> = {
  QUEUED: "Queued",
  INVESTIGATING: "Investigating",
  PROPOSED: "Plan proposed",
  ACCEPTED: "Plan accepted",
  VERIFYING: "Verifying",
  NEEDS_WORK: "Needs more work",
  RESOLVED: "Resolved",
  NO_ACTION: "No action needed",
  INCOMPLETE: "Incomplete",
  DISMISSED: "Dismissed",
};

export function describeRule(rule: Rule): string {
  if (rule.kind === "MIN_FACINGS") {
    return `At least ${rule.min_facings ?? "?"} facings in ${rule.zone_id}`;
  }
  if (rule.kind === "REQUIRED_PRODUCT") {
    return `Product must be on shelf in ${rule.zone_id}`;
  }
  return `Promotional display required in ${rule.zone_id}`;
}
