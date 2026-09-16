/**
 * In-memory test doubles for management screens (Task T05 / AC-38).
 *
 * IMPORTANT CONTRACT STATEMENT:
 * This module provides isolated, contract-shaped test doubles.
 * IS_TEST_DOUBLE = true.
 * Do not claim connected backend acceptance from these test doubles.
 * In accordance with AGENTS.md and specs/04-ui.md, real backend integration
 * replaces these doubles during Wave 4 (Task T08).
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

export const DEFAULT_WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

export const MOCK_MEMBERSHIPS: Membership[] = [
  {
    workspace_id: DEFAULT_WORKSPACE_ID,
    role: "ADMIN",
    workspace_name: "Apex Retail Singapore",
  },
  {
    workspace_id: "99999999-9999-9999-9999-999999999999",
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
    id: "loc-00000000-0000-0000-0000-000000000001",
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
    id: "str-00000000-0000-0000-0000-000000000001",
    workspace_id: DEFAULT_WORKSPACE_ID,
    code: "STR-001",
    name: "Downtown Central Hypermarket",
    retailer: "FairPrice",
    region: "Central",
    format: "HYPERMARKET",
    timezone: "Asia/Singapore",
    distributor_location_id: "loc-00000000-0000-0000-0000-000000000001",
    active: true,
    version: 1,
    created_at: "2026-09-01T08:00:00Z",
    updated_at: "2026-09-01T08:00:00Z",
  },
  {
    id: "str-00000000-0000-0000-0000-000000000002",
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
    id: "prd-00000000-0000-0000-0000-000000000001",
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
    id: "prd-00000000-0000-0000-0000-000000000002",
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
    id: "imp-00000000-0000-0000-0000-000000000001",
    workspace_id: DEFAULT_WORKSPACE_ID,
    kind: "SALES_DAILY",
    media_id: "med-00000000-0000-0000-0000-000000000001",
    status: "COMMITTED",
    row_count: 500,
    error_count: 0,
    errors: [],
    batch_id: "bat-00000000-0000-0000-0000-000000000001",
    committed_at: "2026-09-10T12:00:00Z",
    source_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    version: 2,
    created_at: "2026-09-10T11:55:00Z",
    updated_at: "2026-09-10T12:00:00Z",
  },
];

export const MOCK_RULES: Rule[] = [
  {
    rule_id: "rul-00000000-0000-0000-0000-000000000001",
    kind: "MIN_FACINGS",
    zone_id: "shelf-main",
    zone_kind: "SHELF",
    product_id: "prd-00000000-0000-0000-0000-000000000001",
    min_facings: 3,
    source: {
      kind: "DOCUMENT",
      media_id: "med-00000000-0000-0000-0000-000000000099",
      page: 2,
      quote: "Ensure minimum 3 front facings on eye-level shelf.",
      reviewer_note: null,
    },
  },
  {
    rule_id: "rul-00000000-0000-0000-0000-000000000002",
    kind: "REQUIRED_PRODUCT",
    zone_id: "shelf-main",
    zone_kind: "SHELF",
    product_id: "prd-00000000-0000-0000-0000-000000000002",
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
    id: "prm-00000000-0000-0000-0000-000000000001",
    workspace_id: DEFAULT_WORKSPACE_ID,
    name: "Q3 Beverage Endcap Feature",
    starts_on: "2026-09-01",
    ends_on: "2026-09-30",
    store_ids: ["str-00000000-0000-0000-0000-000000000001"],
    agreement_media_id: "med-00000000-0000-0000-0000-000000000099",
    active_version_id: "pol-00000000-0000-0000-0000-000000000001",
    archived: false,
    version: 1,
    created_at: "2026-08-25T10:00:00Z",
    updated_at: "2026-08-25T10:00:00Z",
  },
];

export const MOCK_POLICY_VERSIONS: PolicyVersion[] = [
  {
    id: "pol-00000000-0000-0000-0000-000000000001",
    workspace_id: DEFAULT_WORKSPACE_ID,
    promotion_id: "prm-00000000-0000-0000-0000-000000000001",
    version_number: 1,
    status: "APPROVED",
    approved_by: "usr-admin-001",
    approved_at: "2026-08-26T14:30:00Z",
    rules: MOCK_RULES,
    catalog_product_ids: [
      "prd-00000000-0000-0000-0000-000000000001",
      "prd-00000000-0000-0000-0000-000000000002",
    ],
    version: 1,
    created_at: "2026-08-26T14:30:00Z",
    updated_at: "2026-08-26T14:30:00Z",
  },
];
