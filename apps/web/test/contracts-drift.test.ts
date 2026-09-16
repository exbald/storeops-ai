import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { StoreOpsClient, VersionConflictError, ApiRequestError } from "../src/lib/api-client.ts";
import {
  generateUuid,
  MOCK_WORKSPACE,
  MOCK_LOCATIONS,
  MOCK_STORES,
  MOCK_PRODUCTS,
  MOCK_IMPORTS,
  MOCK_POLICY_VERSIONS,
  MOCK_PROMOTIONS,
  MOCK_MEMBERSHIPS,
} from "../src/lib/doubles.ts";

const possiblePaths = [
  path.resolve(process.cwd(), "contracts/openapi.json"),
  path.resolve(process.cwd(), "../../contracts/openapi.json"),
  path.resolve(import.meta.dirname, "../../../contracts/openapi.json"),
];
const OPENAPI_PATH = possiblePaths.find((p) => fs.existsSync(p)) || possiblePaths[0];
const openapi = JSON.parse(fs.readFileSync(OPENAPI_PATH, "utf-8"));

const RFC4122_UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

test("OpenAPI contract contains exact paths and methods used by StoreOpsClient", () => {
  const paths = openapi.paths;

  // 1. /me
  assert.ok(paths["/me"]?.get, "GET /me must exist in openapi.json");

  // 2. /workspace
  assert.ok(paths["/workspace"]?.get, "GET /workspace must exist");

  // 3. /stores
  assert.ok(paths["/stores"]?.get, "GET /stores must exist");
  assert.ok(paths["/stores"]?.post, "POST /stores must exist");
  assert.ok(paths["/stores/{store_id}"]?.patch, "PATCH /stores/{store_id} must exist");

  // 4. /products
  assert.ok(paths["/products"]?.get, "GET /products must exist");
  assert.ok(paths["/products"]?.post, "POST /products must exist");
  assert.ok(paths["/products/{product_id}"]?.patch, "PATCH /products/{product_id} must exist");

  // 5. /locations
  assert.ok(paths["/locations"]?.get, "GET /locations must exist");
  assert.ok(paths["/locations"]?.post, "POST /locations must exist");

  // 6. /imports
  assert.ok(paths["/imports"]?.get, "GET /imports must exist");
  assert.ok(paths["/imports"]?.post, "POST /imports must exist");
  assert.ok(paths["/imports/{import_id}/commit"]?.post, "POST /imports/{import_id}/commit must exist");

  // 7. /promotions
  assert.ok(paths["/promotions"]?.get, "GET /promotions must exist");
  assert.ok(paths["/promotions"]?.post, "POST /promotions must exist");

  // 8. Policy approve and versions endpoints
  assert.ok(
    paths["/promotions/{promotion_id}/approve"]?.post,
    "POST /promotions/{promotion_id}/approve must exist (not /approve-policy)"
  );
  assert.ok(
    paths["/promotions/{promotion_id}/versions"]?.get,
    "GET /promotions/{promotion_id}/versions must exist (not /policy-versions)"
  );
});

test("OpenAPI schema requirements match client types", () => {
  const schemas = openapi.components.schemas;

  // PromotionCreate requires agreement_media_id (nullable)
  const promoCreate = schemas["PromotionCreate"];
  assert.ok(promoCreate.required.includes("agreement_media_id"), "agreement_media_id must be in PromotionCreate.required");
  assert.ok(promoCreate.required.includes("name"));
  assert.ok(promoCreate.required.includes("starts_on"));
  assert.ok(promoCreate.required.includes("ends_on"));
  assert.ok(promoCreate.required.includes("store_ids"));

  // ProductUpdate requires expected_version
  const productUpdate = schemas["ProductUpdate"];
  assert.ok(productUpdate.required.includes("expected_version"), "ProductUpdate must require expected_version");
});

test("StoreOpsClient methods use valid RFC 4122 UUIDs for all identifiers", async () => {
  const client = new StoreOpsClient({ useDoubles: true });

  const store = await client.createStore({
    code: "STR-UUID-TEST",
    name: "UUID Store",
    retailer: "FairPrice",
    region: "Central",
    format: "CONVENIENCE",
    timezone: "Asia/Singapore",
  });
  assert.match(store.id, RFC4122_UUID_REGEX, "Store ID must be RFC 4122 UUID");

  const product = await client.createProduct({
    sku: "TEST-UUID-SKU",
    name: "UUID Product",
    case_units: 12,
  });
  assert.match(product.id, RFC4122_UUID_REGEX, "Product ID must be RFC 4122 UUID");

  const promo = await client.createPromotion({
    name: "UUID Promo",
    starts_on: "2026-10-01",
    ends_on: "2026-10-31",
    store_ids: [store.id],
    agreement_media_id: null,
  });
  assert.match(promo.id, RFC4122_UUID_REGEX, "Promotion ID must be RFC 4122 UUID");

  const imp = await client.createImport({
    kind: "SALES",
    media_id: generateUuid(),
  });
  assert.match(imp.id, RFC4122_UUID_REGEX, "Import ID must be RFC 4122 UUID");

  const loc = await client.createLocation({
    code: "WH-UUID",
    name: "Warehouse UUID",
    type: "DISTRIBUTOR",
  });
  assert.match(loc.id, RFC4122_UUID_REGEX, "Location ID must be RFC 4122 UUID");
});

test("StoreOpsClient updateProduct correctly updates version and detects 409 conflict", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const prods = await client.listProducts();
  const target = prods.items[0];

  // Successful update
  const updated = await client.updateProduct(target.id, {
    expected_version: target.version,
    name: "Updated Product Name",
    case_units: 48,
  });
  assert.equal(updated.name, "Updated Product Name");
  assert.equal(updated.case_units, 48);
  assert.equal(updated.version, target.version + 1);

  // Version conflict on stale expected_version
  await assert.rejects(
    async () => {
      await client.updateProduct(target.id, {
        expected_version: target.version, // stale
        name: "Conflicted Name",
      });
    },
    (err: unknown) => {
      assert.ok(err instanceof VersionConflictError);
      assert.equal(err.status, 409);
      assert.equal(err.code, "VERSION_CONFLICT");
      return true;
    }
  );
});

test("StoreOpsClient approvePolicy and listPolicyVersions adhere to contracts", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const promos = await client.listPromotions();
  const target = promos.items[0];

  const approved = await client.approvePolicy(target.id, {
    expected_version: target.version,
    catalog_product_ids: ["00000000-0000-0000-0000-000000000031"],
    rules: [
      {
        rule_id: generateUuid(),
        kind: "MIN_FACINGS",
        zone_id: "shelf-top",
        zone_kind: "SHELF",
        product_id: "00000000-0000-0000-0000-000000000031",
        min_facings: 2,
        source: {
          kind: "DOCUMENT",
          media_id: generateUuid(),
          page: 1,
          quote: "Min 2 facings",
          reviewer_note: null,
        },
      },
    ],
  });

  assert.ok(approved.id !== null);
  assert.match(approved.id, RFC4122_UUID_REGEX);
  assert.equal(approved.promotion_id, target.id);
  assert.ok(approved.version >= 1);
  assert.match(approved.content_sha256, /^[0-9a-f]{64}$/);

  const versions = await client.listPolicyVersions(target.id);
  assert.ok(versions.items.length >= 1);
  assert.equal(versions.items[0].rules.length, 1);
});

test("StoreOpsClient fail-closed semantics when live mode is configured without backend URL", async () => {
  const client = new StoreOpsClient({ useDoubles: false, baseUrl: "" });
  await assert.rejects(
    async () => {
      await client.listStores();
    },
    (err: unknown) => {
      assert.ok(err instanceof ApiRequestError);
      assert.equal(err.status, 503);
      assert.equal(err.code, "UNCONFIGURED_BACKEND");
      return true;
    }
  );
});

test("StoreOpsClient wire format: sends Authorization, X-Workspace-Id, and maps 409 VERSION_CONFLICT", async () => {
  const originalFetch = globalThis.fetch;
  let interceptedUrl = "";
  let interceptedHeaders: Record<string, string> = {};
  let interceptedMethod = "";
  let interceptedBody = "";

  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    interceptedUrl = String(input);
    interceptedMethod = init?.method || "GET";
    interceptedHeaders = (init?.headers as Record<string, string>) || {};
    interceptedBody = (init?.body as string) || "";

    // Simulate backend 409 Version Conflict response
    return new Response(
      JSON.stringify({
        code: "VERSION_CONFLICT",
        message: "Resource has been modified concurrently.",
      }),
      {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }
    );
  };

  try {
    const client = new StoreOpsClient({
      useDoubles: false,
      baseUrl: "https://api.storeops.test",
      getAuthToken: async () => "mock-bearer-token-12345",
      getWorkspaceId: () => "00000000-0000-0000-0000-000000000001",
    });

    await assert.rejects(
      async () => {
        await client.updateProduct("00000000-0000-0000-0000-000000000031", {
          expected_version: 1,
          name: "Conflict Item",
        });
      },
      (err: unknown) => {
        assert.ok(err instanceof VersionConflictError);
        assert.equal(err.status, 409);
        assert.equal(err.code, "VERSION_CONFLICT");
        return true;
      }
    );

    assert.equal(interceptedUrl, "https://api.storeops.test/products/00000000-0000-0000-0000-000000000031");
    assert.equal(interceptedMethod, "PATCH");
    assert.equal(interceptedHeaders["Authorization"], "Bearer mock-bearer-token-12345");
    assert.equal(interceptedHeaders["X-Workspace-Id"], "00000000-0000-0000-0000-000000000001");
    assert.equal(interceptedHeaders["Content-Type"], "application/json");

    const parsedBody = JSON.parse(interceptedBody);
    assert.equal(parsedBody.expected_version, 1);
    assert.equal(parsedBody.name, "Conflict Item");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("StoreOpsClient wire format: sends Idempotency-Key header on mutating POST requests", async () => {
  const originalFetch = globalThis.fetch;
  let interceptedHeaders: Record<string, string> = {};
  let interceptedMethod = "";

  globalThis.fetch = async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    interceptedMethod = init?.method || "GET";
    interceptedHeaders = (init?.headers as Record<string, string>) || {};

    return new Response(
      JSON.stringify({
        id: "00000000-0000-0000-0000-000000000099",
        code: "STR-WIRE",
        name: "Wire Store",
        retailer: "FairPrice",
        region: "North",
        format: "CONVENIENCE",
        timezone: "Asia/Singapore",
        distributor_location_id: null,
        active: true,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }),
      { status: 201, headers: { "Content-Type": "application/json" } }
    );
  };

  try {
    const client = new StoreOpsClient({
      useDoubles: false,
      baseUrl: "https://api.storeops.test",
      getAuthToken: async () => "mock-bearer-token",
      getWorkspaceId: () => "00000000-0000-0000-0000-000000000001",
    });

    await client.createStore({
      code: "STR-WIRE",
      name: "Wire Store",
      retailer: "FairPrice",
      region: "North",
      format: "CONVENIENCE",
      timezone: "Asia/Singapore",
    });

    assert.equal(interceptedMethod, "POST");
    assert.ok(interceptedHeaders["Idempotency-Key"], "Idempotency-Key must be sent on POST");
    assert.match(interceptedHeaders["Idempotency-Key"], RFC4122_UUID_REGEX, "Idempotency-Key must be a valid UUID");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("StoreOpsClient listStores conforms to OpenAPI query parameters (no search param)", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";

  globalThis.fetch = async (input: RequestInfo | URL): Promise<Response> => {
    requestedUrl = String(input);
    return new Response(JSON.stringify({ items: [], next_cursor: null }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const client = new StoreOpsClient({
      useDoubles: false,
      baseUrl: "https://api.storeops.test",
      getAuthToken: async () => "mock-token",
    });

    await client.listStores({ active: true });
    assert.equal(requestedUrl, "https://api.storeops.test/stores?active=true");
    assert.ok(!requestedUrl.includes("search="), "GET /stores must not include search query parameter per openapi");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("StoreOpsClient updateStore double does not leak expected_version onto Store entity", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const stores = await client.listStores();
  const target = stores.items[0];

  const updated = await client.updateStore(target.id, {
    expected_version: target.version,
    name: "Updated Name Clean",
  });

  assert.equal(updated.name, "Updated Name Clean");
  assert.equal("expected_version" in updated, false, "Store entity must not have expected_version field");
});

test("All mock doubles in doubles.ts conform strictly to OpenAPI schemas (no extra or missing fields)", () => {
  const schemas = openapi.components.schemas;

  function validateObject(obj: Record<string, unknown>, schemaName: string) {
    const schema = schemas[schemaName];
    assert.ok(schema, `Schema ${schemaName} exists in openapi.json`);

    // Check required fields
    for (const req of schema.required || []) {
      assert.ok(req in obj, `${schemaName} must have required property '${req}'`);
      assert.notEqual(obj[req], undefined, `${schemaName}.${req} must not be undefined`);
    }

    // Check additionalProperties: false
    if (schema.additionalProperties === false) {
      const allowed = new Set(Object.keys(schema.properties || {}));
      for (const key of Object.keys(obj)) {
        assert.ok(
          allowed.has(key),
          `${schemaName} has disallowed extra property '${key}'. Allowed: ${[...allowed].join(", ")}`
        );
      }
    }
  }

  // 1. Workspace
  validateObject(MOCK_WORKSPACE as unknown as Record<string, unknown>, "Workspace");

  // 2. Locations
  for (const loc of MOCK_LOCATIONS) {
    validateObject(loc as unknown as Record<string, unknown>, "Location");
  }

  // 3. Stores
  for (const store of MOCK_STORES) {
    validateObject(store as unknown as Record<string, unknown>, "Store");
  }

  // 4. Products
  for (const prod of MOCK_PRODUCTS) {
    validateObject(prod as unknown as Record<string, unknown>, "Product");
  }

  // 5. Imports
  for (const imp of MOCK_IMPORTS) {
    validateObject(imp as unknown as Record<string, unknown>, "Import");
    for (const err of imp.errors) {
      validateObject(err as unknown as Record<string, unknown>, "ImportError");
    }
  }

  // 6. Policy Versions
  for (const pv of MOCK_POLICY_VERSIONS) {
    validateObject(pv as unknown as Record<string, unknown>, "PolicyVersion");
  }

  // 7. Promotions
  for (const promo of MOCK_PROMOTIONS) {
    validateObject(promo as unknown as Record<string, unknown>, "Promotion");
    if (promo.approved_policy) {
      validateObject(promo.approved_policy as unknown as Record<string, unknown>, "PolicyVersion");
    }
  }

  // 8. Memberships
  for (const mem of MOCK_MEMBERSHIPS) {
    validateObject(mem as unknown as Record<string, unknown>, "Membership");
  }
});
