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
 * All shapes conform strictly to contracts/openapi.json schemas.
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
    workspace_name: "Apex Retail Singapore",
    role: "ADMIN",
  },
  {
    workspace_id: SECONDARY_WORKSPACE_ID,
    workspace_name: "Secondary Store Network",
    role: "REP",
  },
];

export const MOCK_WORKSPACE: Workspace = {
  id: DEFAULT_WORKSPACE_ID,
  workspace_id: DEFAULT_WORKSPACE_ID,
  version: 1,
  created_at: "2026-09-01T00:00:00Z",
  updated_at: "2026-09-01T00:00:00Z",
  name: "Apex Retail Singapore",
  brand_name: "Apex Retail",
  currency: "SGD",
};

export const MOCK_LOCATIONS: Location[] = [
  {
    id: "00000000-0000-0000-0000-000000000010",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    code: "DIST-WEST",
    name: "Tuas Distribution Hub",
    type: "DISTRIBUTOR",
    store_id: null,
    active: true,
  },
  {
    id: "00000000-0000-0000-0000-000000000011",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
    code: "BR-STR001",
    name: "Downtown Central Backroom",
    type: "BACKROOM",
    store_id: "00000000-0000-0000-0000-000000000021",
    active: true,
  },
  {
    id: "00000000-0000-0000-0000-000000000012",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-02T09:00:00Z",
    updated_at: "2026-09-02T09:00:00Z",
    code: "BR-STR002",
    name: "Bedok Mall Backroom",
    type: "BACKROOM",
    store_id: "00000000-0000-0000-0000-000000000022",
    active: true,
  },
];

export const MOCK_STORES: Store[] = [
  {
    id: "00000000-0000-0000-0000-000000000021",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
    code: "STR-001",
    name: "Downtown Central Hypermarket",
    retailer: "FairPrice",
    region: "Central",
    format: "HYPERMARKET",
    timezone: "Asia/Singapore",
    distributor_location_id: "00000000-0000-0000-0000-000000000010",
    currency: "SGD",
    backroom_location_id: "00000000-0000-0000-0000-000000000011",
    active: true,
  },
  {
    id: "00000000-0000-0000-0000-000000000022",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-02T09:00:00Z",
    updated_at: "2026-09-02T09:00:00Z",
    code: "STR-002",
    name: "Bedok Mall Express",
    retailer: "ColdStorage",
    region: "East",
    format: "CONVENIENCE",
    timezone: "Asia/Singapore",
    distributor_location_id: null,
    currency: "SGD",
    backroom_location_id: "00000000-0000-0000-0000-000000000012",
    active: true,
  },
];

export const MOCK_PRODUCTS: Product[] = [
  {
    id: "00000000-0000-0000-0000-000000000031",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
    sku: "BEV-COKE-500",
    name: "Coca-Cola Original 500ml",
    case_units: 24,
    reference_media_ids: [],
    active: true,
  },
  {
    id: "00000000-0000-0000-0000-000000000032",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
    sku: "BEV-SPRITE-330",
    name: "Sprite Lemon-Lime 330ml Can",
    case_units: 24,
    reference_media_ids: [],
    active: true,
  },
];

export const MOCK_IMPORTS: Import[] = [
  {
    id: "00000000-0000-0000-0000-000000000041",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 2,
    created_at: "2026-09-10T11:55:00Z",
    updated_at: "2026-09-10T12:00:00Z",
    kind: "SALES",
    media_id: "00000000-0000-0000-0000-000000000042",
    status: "COMMITTED",
    row_count: 500,
    error_count: 0,
    errors: [],
    batch_id: "00000000-0000-0000-0000-000000000043",
    committed_at: "2026-09-10T12:00:00Z",
    source_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
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

export const MOCK_POLICY_VERSIONS: PolicyVersion[] = [
  {
    id: "00000000-0000-0000-0000-000000000071",
    promotion_id: "00000000-0000-0000-0000-000000000061",
    version: 1,
    rules: MOCK_RULES,
    catalog_product_ids: [
      "00000000-0000-0000-0000-000000000031",
      "00000000-0000-0000-0000-000000000032",
    ],
    store_ids: ["00000000-0000-0000-0000-000000000021"],
    starts_on: "2026-09-01",
    ends_on: "2026-09-30",
    approved_at: "2026-08-26T14:30:00Z",
    approved_by: "00000000-0000-0000-0000-000000000009",
    content_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  },
];

export const MOCK_PROMOTIONS: Promotion[] = [
  {
    id: "00000000-0000-0000-0000-000000000061",
    workspace_id: DEFAULT_WORKSPACE_ID,
    version: 1,
    created_at: "2026-08-25T10:00:00Z",
    updated_at: "2026-08-25T10:00:00Z",
    name: "Q3 Beverage Endcap Feature",
    starts_on: "2026-09-01",
    ends_on: "2026-09-30",
    store_ids: ["00000000-0000-0000-0000-000000000021"],
    agreement_media_id: "00000000-0000-0000-0000-000000000099",
    archived: false,
    draft_revision: 1,
    extracted_rules: MOCK_RULES,
    extraction_gaps: [],
    approved_policy: MOCK_POLICY_VERSIONS[0],
  },
];
