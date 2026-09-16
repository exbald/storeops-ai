/**
 * Contract-compliant API client for StoreOps web application.
 * Sourced directly from @storeops/contracts and contracts/openapi.json.
 *
 * Implements:
 * - Tenant isolation headers: X-Workspace-Id
 * - Auth headers: Authorization: Bearer <token>
 * - Concurrency conflict detection: HTTP 409 VERSION_CONFLICT -> VersionConflictError
 * - Full type-safety against OpenAPI schemas
 * - Fail-closed error semantics (no silent success fallback)
 * - Explicit test double mode with full UUID conformance
 */

import type {
  Store,
  StoreCreate,
  StoreUpdate,
  Product,
  ProductCreate,
  ProductUpdate,
  Location,
  LocationCreate,
  Import,
  ImportCreate,
  Promotion,
  PromotionCreate,
  PolicyVersion,
  ApprovePolicy,
  Workspace,
  Membership,
  Rule,
  ApiError,
} from "@storeops/contracts";

import {
  IS_TEST_DOUBLE,
  DEFAULT_WORKSPACE_ID,
  MOCK_MEMBERSHIPS,
  MOCK_WORKSPACE,
  MOCK_LOCATIONS,
  MOCK_STORES,
  MOCK_PRODUCTS,
  MOCK_IMPORTS,
  MOCK_PROMOTIONS,
  MOCK_POLICY_VERSIONS,
  generateUuid,
} from "./doubles.ts";

export class ApiRequestError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly details: Record<string, unknown> | null;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> | null = null) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export class VersionConflictError extends ApiRequestError {
  constructor(message = "Resource has been modified concurrently. Please refresh the page.", details: Record<string, unknown> | null = null) {
    super(409, "VERSION_CONFLICT", message, details);
    this.name = "VersionConflictError";
  }
}

export interface ApiClientConfig {
  baseUrl?: string;
  getAuthToken?: () => Promise<string | null>;
  getWorkspaceId?: () => string | null;
  useDoubles?: boolean;
}

export class StoreOpsClient {
  private baseUrl: string;
  private getAuthToken?: () => Promise<string | null>;
  private getWorkspaceId: () => string | null;
  public readonly useDoubles: boolean;

  // In-memory state for isolated test double operation (AC-38)
  private doubleStores: Store[] = [...MOCK_STORES];
  private doubleProducts: Product[] = [...MOCK_PRODUCTS];
  private doubleLocations: Location[] = [...MOCK_LOCATIONS];
  private doubleImports: Import[] = [...MOCK_IMPORTS];
  private doublePromotions: Promotion[] = [...MOCK_PROMOTIONS];
  private doublePolicyVersions: PolicyVersion[] = [...MOCK_POLICY_VERSIONS];

  constructor(config: ApiClientConfig = {}) {
    const explicitDoubles =
      config.useDoubles !== undefined
        ? config.useDoubles
        : typeof process !== "undefined" && process.env.NEXT_PUBLIC_USE_DOUBLES === "true";

    this.baseUrl =
      config.baseUrl ||
      (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_API_URL || "" : "");
    this.getAuthToken = config.getAuthToken;
    this.getWorkspaceId = config.getWorkspaceId || (() => DEFAULT_WORKSPACE_ID);

    // Fail closed: Doubles are only active when explicitly enabled (config.useDoubles=true or NEXT_PUBLIC_USE_DOUBLES=true).
    // An unset API URL without explicit doubles enabled throws UNCONFIGURED_BACKEND on request.
    this.useDoubles = explicitDoubles === true;
  }

  private async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    if (!this.baseUrl && !this.useDoubles) {
      throw new ApiRequestError(
        503,
        "UNCONFIGURED_BACKEND",
        "StoreOps API URL is unconfigured (NEXT_PUBLIC_API_URL is missing) and mock doubles are disabled. Real API connection required."
      );
    }

    const token = this.getAuthToken ? await this.getAuthToken() : null;
    const workspaceId = this.getWorkspaceId();

    if (!token && !path.startsWith("/health")) {
      throw new ApiRequestError(
        401,
        "UNAUTHENTICATED",
        "Authentication required: missing token."
      );
    }

    const method = (options.method || "GET").toUpperCase();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (workspaceId && !path.startsWith("/me") && !path.startsWith("/health")) {
      headers["X-Workspace-Id"] = workspaceId;
    }
    // Frozen contract requires Idempotency-Key on POST requests
    if (method === "POST" && !headers["Idempotency-Key"]) {
      headers["Idempotency-Key"] = generateUuid();
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errBody: ApiError = {
        code: "HTTP_ERROR",
        message: response.statusText,
        details: null,
      };
      try {
        errBody = await response.json();
      } catch {
        // Fall back to status text
      }

      if (response.status === 409 || errBody.code === "VERSION_CONFLICT") {
        throw new VersionConflictError(errBody.message, errBody.details as Record<string, unknown> | null);
      }

      throw new ApiRequestError(
        response.status,
        errBody.code || "UNKNOWN_ERROR",
        errBody.message || "Request failed",
        errBody.details as Record<string, unknown> | null
      );
    }

    if (response.status === 204) {
      return undefined as unknown as T;
    }

    return (await response.json()) as T;
  }

  // --- Auth & Workspaces ---
  async getMe(): Promise<{ user_id: string; email: string; memberships: Membership[] }> {
    if (this.useDoubles) {
      return {
        user_id: "00000000-0000-0000-0000-000000000009",
        email: "admin@storeops.local",
        memberships: MOCK_MEMBERSHIPS,
      };
    }
    return this.fetch<{ user_id: string; email: string; memberships: Membership[] }>("/me");
  }

  async getWorkspace(): Promise<Workspace> {
    if (this.useDoubles) {
      return MOCK_WORKSPACE;
    }
    return this.fetch<Workspace>("/workspace");
  }

  // --- Stores ---
  async listStores(params?: { active?: boolean }): Promise<{ items: Store[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      let items = [...this.doubleStores];
      if (params?.active !== undefined) {
        items = items.filter((s) => s.active === params.active);
      }
      return { items, next_cursor: null };
    }
    const query = new URLSearchParams();
    if (params?.active !== undefined) query.set("active", String(params.active));
    const qs = query.toString();
    return this.fetch<{ items: Store[]; next_cursor: string | null }>(`/stores${qs ? `?${qs}` : ""}`);
  }

  async createStore(data: StoreCreate): Promise<Store> {
    if (this.useDoubles) {
      const backroomId = generateUuid();
      const newStore: Store = {
        id: generateUuid(),
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        code: data.code,
        name: data.name,
        retailer: data.retailer,
        region: data.region,
        format: data.format,
        timezone: data.timezone,
        distributor_location_id: data.distributor_location_id || null,
        currency: "SGD",
        backroom_location_id: backroomId,
        active: true,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      const newBackroom: Location = {
        id: backroomId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: newStore.created_at,
        updated_at: newStore.updated_at,
        code: `BR-${data.code}`,
        name: `${data.name} Backroom`,
        type: "BACKROOM",
        store_id: newStore.id,
        active: true,
      };
      this.doubleLocations.unshift(newBackroom);
      this.doubleStores.unshift(newStore);
      return newStore;
    }
    return this.fetch<Store>("/stores", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateStore(id: string, data: StoreUpdate): Promise<Store> {
    if (this.useDoubles) {
      const idx = this.doubleStores.findIndex((s) => s.id === id);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Store not found");
      const current = this.doubleStores[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Store has been modified concurrently. Expected version mismatch.");
      }
      const updated: Store = {
        id: current.id,
        workspace_id: current.workspace_id,
        code: current.code,
        name: data.name !== undefined ? data.name : current.name,
        retailer: data.retailer !== undefined ? data.retailer : current.retailer,
        format: data.format !== undefined ? data.format : current.format,
        region: data.region !== undefined ? data.region : current.region,
        timezone: data.timezone !== undefined ? data.timezone : current.timezone,
        distributor_location_id:
          data.distributor_location_id !== undefined
            ? data.distributor_location_id
            : current.distributor_location_id,
        currency: current.currency,
        backroom_location_id: current.backroom_location_id,
        active: data.active !== undefined ? data.active : current.active,
        version: current.version + 1,
        created_at: current.created_at,
        updated_at: new Date().toISOString(),
      };
      this.doubleStores[idx] = updated;
      return updated;
    }
    return this.fetch<Store>(`/stores/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  // --- Products & Locations ---
  async listProducts(params?: { active?: boolean }): Promise<{ items: Product[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      let items = [...this.doubleProducts];
      if (params?.active !== undefined) {
        items = items.filter((p) => p.active === params.active);
      }
      return { items, next_cursor: null };
    }
    const query = new URLSearchParams();
    if (params?.active !== undefined) query.set("active", String(params.active));
    const qs = query.toString();
    return this.fetch<{ items: Product[]; next_cursor: string | null }>(`/products${qs ? `?${qs}` : ""}`);
  }

  async createProduct(data: ProductCreate): Promise<Product> {
    if (this.useDoubles) {
      const newProduct: Product = {
        id: generateUuid(),
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        sku: data.sku,
        name: data.name,
        case_units: data.case_units,
        reference_media_ids: [],
        active: true,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      this.doubleProducts.unshift(newProduct);
      return newProduct;
    }
    return this.fetch<Product>("/products", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateProduct(id: string, data: ProductUpdate): Promise<Product> {
    if (this.useDoubles) {
      const idx = this.doubleProducts.findIndex((p) => p.id === id);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Product not found");
      const current = this.doubleProducts[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Product has been modified concurrently. Expected version mismatch.");
      }
      const updated: Product = {
        ...current,
        ...(data.name !== undefined ? { name: data.name } : {}),
        ...(data.case_units !== undefined ? { case_units: data.case_units } : {}),
        ...(data.reference_media_ids !== undefined ? { reference_media_ids: data.reference_media_ids } : {}),
        ...(data.active !== undefined ? { active: data.active } : {}),
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleProducts[idx] = updated;
      return updated;
    }
    return this.fetch<Product>(`/products/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  async listLocations(): Promise<{ items: Location[] }> {
    if (this.useDoubles) {
      return { items: [...this.doubleLocations] };
    }
    return this.fetch<{ items: Location[] }>("/locations");
  }

  async createLocation(data: LocationCreate): Promise<Location> {
    if (this.useDoubles) {
      const newLoc: Location = {
        id: generateUuid(),
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        code: data.code,
        name: data.name,
        type: data.type || "DISTRIBUTOR",
        store_id: null,
        active: true,
      };
      this.doubleLocations.unshift(newLoc);
      return newLoc;
    }
    return this.fetch<Location>("/locations", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  // --- Imports ---
  async listImports(): Promise<{ items: Import[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      return { items: [...this.doubleImports], next_cursor: null };
    }
    return this.fetch<{ items: Import[]; next_cursor: string | null }>("/imports");
  }

  async createImport(data: ImportCreate): Promise<Import> {
    if (this.useDoubles) {
      const newImport: Import = {
        id: generateUuid(),
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        kind: data.kind,
        media_id: data.media_id,
        status: "VALIDATED",
        row_count: 100,
        error_count: 0,
        errors: [],
        batch_id: null,
        committed_at: null,
        source_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      };
      this.doubleImports.unshift(newImport);
      return newImport;
    }
    return this.fetch<Import>("/imports", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async commitImport(id: string): Promise<Import> {
    if (this.useDoubles) {
      const idx = this.doubleImports.findIndex((i) => i.id === id);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Import not found");
      const current = this.doubleImports[idx];
      const committed: Import = {
        ...current,
        status: "COMMITTED",
        committed_at: new Date().toISOString(),
        batch_id: generateUuid(),
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleImports[idx] = committed;
      return committed;
    }
    return this.fetch<Import>(`/imports/${id}/commit`, {
      method: "POST",
    });
  }

  // --- Promotions & Policies ---
  async listPromotions(): Promise<{ items: Promotion[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      return { items: [...this.doublePromotions], next_cursor: null };
    }
    return this.fetch<{ items: Promotion[]; next_cursor: string | null }>("/promotions");
  }

  async createPromotion(data: PromotionCreate): Promise<Promotion> {
    if (this.useDoubles) {
      const newPromo: Promotion = {
        id: generateUuid(),
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        name: data.name,
        starts_on: data.starts_on,
        ends_on: data.ends_on,
        store_ids: data.store_ids,
        agreement_media_id: data.agreement_media_id,
        archived: false,
        draft_revision: 1,
        extracted_rules: [],
        extraction_gaps: [],
        approved_policy: null,
      };
      this.doublePromotions.unshift(newPromo);
      return newPromo;
    }
    return this.fetch<Promotion>("/promotions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async approvePolicy(promotionId: string, data: ApprovePolicy): Promise<PolicyVersion> {
    if (this.useDoubles) {
      const promo = this.doublePromotions.find((p) => p.id === promotionId);
      if (!promo) throw new ApiRequestError(404, "NOT_FOUND", "Promotion not found");
      if (promo.version !== data.expected_version) {
        throw new VersionConflictError("Promotion has been modified concurrently. Expected version mismatch.");
      }

      const newVersion: PolicyVersion = {
        id: generateUuid(),
        promotion_id: promotionId,
        version: promo.approved_policy ? promo.approved_policy.version + 1 : 1,
        rules: data.rules,
        catalog_product_ids: data.catalog_product_ids,
        store_ids: promo.store_ids,
        starts_on: promo.starts_on,
        ends_on: promo.ends_on,
        approved_at: new Date().toISOString(),
        approved_by: "00000000-0000-0000-0000-000000000009",
        content_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
      };
      this.doublePolicyVersions.unshift(newVersion);
      promo.approved_policy = newVersion;
      promo.version += 1;
      promo.updated_at = new Date().toISOString();
      return newVersion;
    }
    // Fixed path per contracts/openapi.json: POST /promotions/{promotion_id}/approve
    return this.fetch<PolicyVersion>(`/promotions/${promotionId}/approve`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async listPolicyVersions(promotionId: string): Promise<{ items: PolicyVersion[] }> {
    if (this.useDoubles) {
      return {
        items: this.doublePolicyVersions.filter((v) => v.promotion_id === promotionId),
      };
    }
    // Fixed path per contracts/openapi.json: GET /promotions/{promotion_id}/versions
    return this.fetch<{ items: PolicyVersion[] }>(`/promotions/${promotionId}/versions`);
  }
}

export const apiClient = new StoreOpsClient();
