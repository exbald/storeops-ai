import test from "node:test";
import assert from "node:assert/strict";
import type { Promotion } from "@storeops/contracts";

import { investigablePromotions } from "../src/lib/investigable-promotions";

const STORE = "11111111-0000-0000-0000-000000000001";
const OTHER = "11111111-0000-0000-0000-000000000002";

function promo(id: string, overrides: Partial<Promotion>): Promotion {
  return { id, archived: false, approved_policy: {} as Promotion["approved_policy"], store_ids: [STORE], ...overrides } as Promotion;
}

test("investigablePromotions keeps only approved, active promotions for the visit's store", () => {
  const items = [
    promo("ok", {}),
    promo("archived", { archived: true }),
    promo("draft", { approved_policy: null }),
    promo("other-store", { store_ids: [OTHER] }),
  ];
  assert.deepEqual(investigablePromotions(items, STORE).map((p) => p.id), ["ok"]);
});
