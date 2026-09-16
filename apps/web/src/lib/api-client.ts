/**
 * Contract-compliant API client for StoreOps web application.
 * Sourced directly from @storeops/contracts.
 *
 * Implements:
 * - Tenant isolation headers: X-Workspace-Id
 * - Auth headers: Authorization: Bearer <token>
 * - Concurrency conflict detection: HTTP 409 VERSION_CONFLICT
 * - Full type-safety against OpenAPI schemas
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
  private getAuthToken: () => Promise<string | null>;
  private getWorkspaceId: () => string | null;
  private useDoubles: boolean;

  // In-memory state for isolated test double operation
  private doubleStores: Store[] = [...MOCK_STORES];
  private doubleProducts: Product[] = [...MOCK_PRODUCTS];
  private doubleLocations: Location[] = [...MOCK_LOCATIONS];
  private doubleImports: Import[] = [...MOCK_IMPORTS];
  private doublePromotions: Promotion[] = [...MOCK_PROMOTIONS];
  private doublePolicyVersions: PolicyVersion[] = [...MOCK_POLICY_VERSIONS];

  constructor(config: ApiClientConfig = {}) {
    this.baseUrl = config.baseUrl || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    this.getAuthToken = config.getAuthToken || (async () => "mock-token-admin");
    this.getWorkspaceId = config.getWorkspaceId || (() => DEFAULT_WORKSPACE_ID);
    this.useDoubles = config.useDoubles ?? (process.env.NEXT_PUBLIC_USE_DOUBLES === "true" || !process.env.NEXT_PUBLIC_API_URL);
  }

  private async fetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await this.getAuthToken();
    const workspaceId = this.getWorkspaceId();

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    if (workspaceId && !path.startsWith("/me")) {
      headers["X-Workspace-Id"] = workspaceId;
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
        user_id: "usr-admin-001",
        email: "admin@storeops.local",
        memberships: MOCK_MEMBERSHIPS,
      };
    }
    return this.fetch<{ user_id: string; email: string; memberships: Membership[] }>("/me");
  }

  async getWorkspace(id: string): Promise<Workspace> {
    if (this.useDoubles) {
      return { ...MOCK_WORKSPACE, id };
    }
    return this.fetch<Workspace>(`/workspaces/${id}`);
  }

  // --- Stores ---
  async listStores(params?: { active?: boolean; search?: string }): Promise<{ items: Store[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      let items = [...this.doubleStores];
      if (params?.active !== undefined) {
        items = items.filter((s) => s.active === params.active);
      }
      if (params?.search) {
        const q = params.search.toLowerCase();
        items = items.filter((s) => s.name.toLowerCase().includes(q) || s.code.toLowerCase().includes(q));
      }
      return { items, next_cursor: null };
    }
    const query = new URLSearchParams();
    if (params?.active !== undefined) query.set("active", String(params.active));
    if (params?.search) query.set("search", params.search);
    return this.fetch<{ items: Store[]; next_cursor: string | null }>(`/stores?${query.toString()}`);
  }

  async createStore(data: {
    code: string;
    name: string;
    retailer: string;
    region: string;
    format: string;
    timezone: string;
    distributor_location_id?: string | null;
  }): Promise<Store> {
    if (this.useDoubles) {
      const newStore: Store = {
        id: `str-${Date.now()}`,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        code: data.code,
        name: data.name,
        retailer: data.retailer,
        region: data.region,
        format: data.format,
        timezone: data.timezone,
        distributor_location_id: data.distributor_location_id || null,
        active: true,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      this.doubleStores.unshift(newStore);
      return newStore;
    }
    return this.fetch<Store>("/stores", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateStore(id: string, data: { expected_version: number; name?: string; active?: boolean }): Promise<Store> {
    if (this.useDoubles) {
      const idx = this.doubleStores.findIndex((s) => s.id === id);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Store not found");
      const current = this.doubleStores[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Store has been modified concurrently. Expected version mismatch.");
      }
      const updated: Store = {
        ...current,
        ...data,
        version: current.version + 1,
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
    return this.fetch<{ items: Product[]; next_cursor: string | null }>(`/products?${query.toString()}`);
  }

  async createProduct(data: { sku: string; name: string; case_units: number }): Promise<Product> {
    if (this.useDoubles) {
      const newProduct: Product = {
        id: `prd-${Date.now()}`,
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

  async listLocations(): Promise<{ items: Location[] }> {
    if (this.useDoubles) {
      return { items: [...this.doubleLocations] };
    }
    return this.fetch<{ items: Location[] }>("/locations");
  }

  async createLocation(data: { code: string; name: string; timezone: string }): Promise<Location> {
    if (this.useDoubles) {
      const newLoc: Location = {
        id: `loc-${Date.now()}`,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        code: data.code,
        name: data.name,
        timezone: data.timezone,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
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

  async createImport(data: { kind: "SALES_DAILY" | "INVENTORY_SNAPSHOT"; media_id: string }): Promise<Import> {
    if (this.useDoubles) {
      const newImport: Import = {
        id: `imp-${Date.now()}`,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        kind: data.kind,
        media_id: data.media_id,
        status: "VALIDATED",
        row_count: 100,
        error_count: 0,
        errors: [],
        batch_id: null,
        committed_at: null,
        source_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
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
        batch_id: `bat-${Date.now()}`,
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

  async createPromotion(data: {
    name: string;
    starts_on: string;
    ends_on: string;
    store_ids: string[];
    agreement_media_id?: string | null;
  }): Promise<Promotion> {
    if (this.useDoubles) {
      const newPromo: Promotion = {
        id: `prm-${Date.now()}`,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        name: data.name,
        starts_on: data.starts_on,
        ends_on: data.ends_on,
        store_ids: data.store_ids,
        agreement_media_id: data.agreement_media_id || null,
        active_version_id: null,
        archived: false,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      this.doublePromotions.unshift(newPromo);
      return newPromo;
    }
    return this.fetch<Promotion>("/promotions", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async approvePolicy(promotionId: string, data: {
    expected_version: number;
    catalog_product_ids: string[];
    rules: Rule[];
  }): Promise<PolicyVersion> {
    if (this.useDoubles) {
      const promo = this.doublePromotions.find((p) => p.id === promotionId);
      if (!promo) throw new ApiRequestError(404, "NOT_FOUND", "Promotion not found");
      if (promo.version !== data.expected_version) {
        throw new VersionConflictError("Promotion has been modified concurrently. Expected version mismatch.");
      }

      const newVersion: PolicyVersion = {
        id: `pol-${Date.now()}`,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        promotion_id: promotionId,
        version_number: (this.doublePolicyVersions.filter((v) => v.promotion_id === promotionId).length || 0) + 1,
        status: "APPROVED",
        approved_by: "usr-admin-001",
        approved_at: new Date().toISOString(),
        rules: data.rules,
        catalog_product_ids: data.catalog_product_ids,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      this.doublePolicyVersions.unshift(newVersion);
      promo.active_version_id = newVersion.id;
      promo.version += 1;
      return newVersion;
    }
    return this.fetch<PolicyVersion>(`/promotions/${promotionId}/approve-policy`, {
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
    return this.fetch<{ items: PolicyVersion[] }>(`/promotions/${promotionId}/policy-versions`);
  }
}

export const apiClient = new StoreOpsClient();
