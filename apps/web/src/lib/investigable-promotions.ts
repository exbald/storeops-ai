import type { Promotion } from "@storeops/contracts";

/** Promotions an investigation can run against: approved, not archived, and covering the visit's store. */
export function investigablePromotions(promotions: Promotion[], storeId: string): Promotion[] {
  return promotions.filter(
    (p) => !p.archived && p.approved_policy != null && p.store_ids.includes(storeId)
  );
}
