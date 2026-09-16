/**
 * In-memory test doubles for management screens (Task T05 / AC-38).
 *
 * IMPORTANT CONTRACT STATEMENT:
 * This module provides isolated, contract-shaped test doubles.
 * IS_TEST_DOUBLE = true.
 * Do not claim connected backend acceptance from these test doubles.
 * In accordance with AGENTS.md and specs/04-ui.md, real backend integration
 * replaces these doubles during Wave 4 (Task T08).
 *
 * All identifiers adhere strictly to RFC 4122 format: uuid.
 */

import type {
  Store,
  Product,
  Location,
  Import,
  Promotion,
  PolicyVersion,
  Workspace,
  Membership,
  Rule,
} from "@storeops/contracts";

export const IS_TEST_DOUBLE = true;
export const IS_MOCK = true;

export const DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001";
export const SECONDARY_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002";

export function generateUuid(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return "00000000-0000-4000-8000-" + Math.random().toString(16).substring(2, 14).padStart(12, "0");
}

export const MOCK_MEMBERSHIPS: Membership[] = [
  {
    workspace_id: DEFAULT_WORKSPACE_ID,
    role: "ADMIN",
    workspace_name: "Apex Retail Singapore",
  },
  {
    workspace_id: SECONDARY_WORKSPACE_ID,
    role: "REP",
    workspace_name: "Secondary Store Network",
  },
];

export const MOCK_WORKSPACE: Workspace = {
  id: DEFAULT_WORKSPACE_ID,
  name: "Apex Retail Singapore",
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
};

export const MOCK_LOCATIONS: Location[] = [
  {
    id: "00000000-0000-0000-0000-000000000010",
    workspace_id: DEFAULT_WORKSPACE_ID,
    code: "DIST-WEST",
    name: "Tuas Distribution Hub",
    timezone: "Asia/Singapore",
    version: 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
  },
];

export const MOCK_STORES: Store[] = [
  {
    id: "00000000-0000-0000-0000-000000000021",
    workspace_id: DEFAULT_WORKSPACE_ID,
    code: "STR-001",
    name: "Downtown Central Hypermarket",
    retailer: "FairPrice",
    region: "Central",
    format: "HYPERMARKET",
    timezone: "Asia/Singapore",
    distributor_location_id: "00000000-0000-0000-0000-000000000010",
    active: true,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000022",
    workspace_id: DEFAULT_WORKSPACE_ID,
    code: "STR-002",
    name: "Bedok Mall Express",
    retailer: "ColdStorage",
    region: "East",
    format: "CONVENIENCE",
    timezone: "Asia/Singapore",
    distributor_location_id: null,
    active: true,
    version: 1,
    created_at: "2026-09-02T09:00:00Z",
    updated_at: "2026-09-02T09:00:00Z",
  },
];

export const MOCK_PRODUCTS: Product[] = [
  {
    id: "00000000-0000-0000-0000-000000000031",
    workspace_id: DEFAULT_WORKSPACE_ID,
    sku: "BEV-COKE-500",
    name: "Coca-Cola Original 500ml",
    case_units: 24,
    reference_media_ids: [],
    active: true,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000032",
    workspace_id: DEFAULT_WORKSPACE_ID,
    sku: "BEV-SPRITE-330",
    name: "Sprite Lemon-Lime 330ml Can",
    case_units: 24,
    reference_media_ids: [],
    active: true,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
  },
];

export const MOCK_IMPORTS: Import[] = [
  {
    id: "00000000-0000-0000-0000-000000000041",
    workspace_id: DEFAULT_WORKSPACE_ID,
    kind: "SALES_DAILY",
    media_id: "00000000-0000-0000-0000-000000000042",
    status: "COMMITTED",
    row_count: 500,
    error_count: 0,
    errors: [],
    batch_id: "00000000-0000-0000-0000-000000000043",
    committed_at: "2026-09-10T12:00:00Z",
    source_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    version: 2,
    created_at: "2026-09-10T11:55:00Z",
    updated_at: "2026-09-10T12:00:00Z",
  },
];

export const MOCK_RULES: Rule[] = [
  {
    rule_id: "00000000-0000-0000-0000-000000000051",
    kind: "MIN_FACINGS",
    zone_id: "shelf-main",
    zone_kind: "SHELF",
    product_id: "00000000-0000-0000-0000-000000000031",
    min_facings: 3,
    source: {
      kind: "DOCUMENT",
      media_id: "00000000-0000-0000-0000-000000000099",
      page: 2,
      quote: "Ensure minimum 3 front facings on eye-level shelf.",
      reviewer_note: null,
    },
  },
  {
    rule_id: "00000000-0000-0000-0000-000000000052",
    kind: "REQUIRED_PRODUCT",
    zone_id: "shelf-main",
    zone_kind: "SHELF",
    product_id: "00000000-0000-0000-0000-000000000032",
    min_facings: null,
    source: {
      kind: "MANUAL",
      media_id: null,
      page: null,
      quote: null,
      reviewer_note: "Mandatory regional distribution requirement.",
    },
  },
];

export const MOCK_PROMOTIONS: Promotion[] = [
  {
    id: "00000000-0000-0000-0000-000000000061",
    workspace_id: DEFAULT_WORKSPACE_ID,
    name: "Q3 Beverage Endcap Feature",
    starts_on: "2026-09-01",
    ends_on: "2026-09-30",
    store_ids: ["00000000-0000-0000-0000-000000000021"],
    agreement_media_id: "00000000-0000-0000-0000-000000000099",
    active_version_id: "00000000-0000-0000-0000-000000000071",
    archived: false,
    version: 1,
    created_at: "2026-08-25T10:00:00Z",
    updated_at: "2026-08-25T10:00:00Z",
  },
];

export const MOCK_POLICY_VERSIONS: PolicyVersion[] = [
  {
    id: "00000000-0000-0000-0000-000000000071",
    workspace_id: DEFAULT_WORKSPACE_ID,
    promotion_id: "00000000-0000-0000-0000-000000000061",
    version_number: 1,
    status: "APPROVED",
    approved_by: "00000000-0000-0000-0000-000000000009",
    approved_at: "2026-08-26T14:30:00Z",
    rules: MOCK_RULES,
    catalog_product_ids: [
      "00000000-0000-0000-0000-000000000031",
      "00000000-0000-0000-0000-000000000032",
    ],
    version: 1,
    created_at: "2026-08-26T14:30:00Z",
    updated_at: "2026-08-26T14:30:00Z",
  },
];
