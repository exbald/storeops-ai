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
  Product,
  Location,
  Import,
  Promotion,
  PolicyVersion,
  Workspace,
  Membership,
  Visit,
  Investigation,
  Verification,
  Report,
  Job,
  JobEvent,
  Media,
  Schemas,
} from "@storeops/contracts";

type StoreCreate = Schemas["StoreCreate"];
type StoreUpdate = Schemas["StoreUpdate"];
type ProductCreate = Schemas["ProductCreate"];
type ProductUpdate = Schemas["ProductUpdate"];
type LocationCreate = Schemas["LocationCreate"];
type ImportCreate = Schemas["ImportCreate"];
type PromotionCreate = Schemas["PromotionCreate"];
type ApprovePolicy = Schemas["ApprovePolicy"];

import {
  DEFAULT_WORKSPACE_ID,
  MOCK_MEMBERSHIPS,
  MOCK_WORKSPACE,
  MOCK_LOCATIONS,
  MOCK_STORES,
  MOCK_PRODUCTS,
  MOCK_IMPORTS,
  MOCK_PROMOTIONS,
  MOCK_POLICY_VERSIONS,
  MOCK_STORE_HEALTH,
  MOCK_VISITS,
  MOCK_INVESTIGATIONS,
  MOCK_VERIFICATIONS,
  MOCK_REPORTS,
  MOCK_JOBS,
  MOCK_JOB_EVENTS,
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
  private _useDoubles: boolean;
  private currentWorkspaceId: string | null = null;
  private currentAuthToken: string | null = null;

  public get useDoubles(): boolean {
    return this._useDoubles;
  }

  public setUseDoubles(useDoubles: boolean): void {
    this._useDoubles = useDoubles;
  }

  // In-memory state for isolated test double operation (AC-38)
  private doubleStores: Store[] = [...MOCK_STORES];
  private doubleProducts: Product[] = [...MOCK_PRODUCTS];
  private doubleLocations: Location[] = [...MOCK_LOCATIONS];
  private doubleImports: Import[] = [...MOCK_IMPORTS];
  private doublePromotions: Promotion[] = [...MOCK_PROMOTIONS];
  private doublePolicyVersions: PolicyVersion[] = [...MOCK_POLICY_VERSIONS];
  private doubleVisits: Visit[] = [...MOCK_VISITS];
  private doubleInvestigations: Investigation[] = [...MOCK_INVESTIGATIONS];
  private doubleVerifications: Verification[] = [...MOCK_VERIFICATIONS];
  private doubleReports: Report[] = [...MOCK_REPORTS];
  private doubleJobs: Job[] = [...MOCK_JOBS];
  private doubleJobEvents: JobEvent[] = [...MOCK_JOB_EVENTS];
  private doubleMedia: Media[] = [];

  constructor(config: ApiClientConfig = {}) {
    const explicitDoubles =
      config.useDoubles !== undefined
        ? config.useDoubles
        : typeof process !== "undefined" && process.env.NEXT_PUBLIC_USE_DOUBLES === "true";

    this.baseUrl =
      config.baseUrl ||
      (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_API_URL || "" : "");
    const envToken =
      typeof process !== "undefined" ? process.env.NEXT_PUBLIC_AUTH_TOKEN || null : null;
    this.currentAuthToken = envToken;

    this.getAuthToken =
      config.getAuthToken ||
      (async () =>
        this.currentAuthToken ||
        (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_AUTH_TOKEN || null : null));
    this._useDoubles = explicitDoubles === true;

    const envWorkspace =
      typeof process !== "undefined" ? process.env.NEXT_PUBLIC_WORKSPACE_ID || null : null;
    this.currentWorkspaceId = envWorkspace || DEFAULT_WORKSPACE_ID;

    this.getWorkspaceId =
      config.getWorkspaceId ||
      (() =>
        this.currentWorkspaceId ||
        (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_WORKSPACE_ID || null : null) ||
        DEFAULT_WORKSPACE_ID);
  }

  public setWorkspaceId(workspaceId: string | null): void {
    this.currentWorkspaceId = workspaceId;
  }

  public setAuthToken(token: string | null): void {
    this.currentAuthToken = token;
  }

  public getAuthTokenDirect(): string | null {
    return this.currentAuthToken;
  }

  public resetDoubles(): void {
    this.doubleStores = MOCK_STORES.map((s) => ({ ...s }));
    this.doubleProducts = MOCK_PRODUCTS.map((p) => ({ ...p }));
    this.doubleLocations = MOCK_LOCATIONS.map((l) => ({ ...l }));
    this.doubleImports = MOCK_IMPORTS.map((i) => ({ ...i }));
    this.doublePromotions = MOCK_PROMOTIONS.map((pr) => ({ ...pr }));
    this.doublePolicyVersions = MOCK_POLICY_VERSIONS.map((pv) => ({ ...pv }));
    this.doubleVisits = MOCK_VISITS.map((v) => ({ ...v }));
    this.doubleInvestigations = MOCK_INVESTIGATIONS.map((inv) => ({ ...inv }));
    this.doubleVerifications = MOCK_VERIFICATIONS.map((ver) => ({ ...ver }));
    this.doubleReports = MOCK_REPORTS.map((r) => ({ ...r }));
    this.doubleJobs = MOCK_JOBS.map((j) => ({ ...j }));
    this.doubleJobEvents = MOCK_JOB_EVENTS.map((je) => ({ ...je }));
    this.doubleMedia = [];
  }

  public getDoubleReports(): Report[] {
    return this.doubleReports;
  }

  public getDoubleVisits(): Visit[] {
    return this.doubleVisits;
  }

  public getDoubleInvestigations(): Investigation[] {
    return this.doubleInvestigations;
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
      let errBody: { code?: string; message?: string; details?: unknown } = {
        code: "HTTP_ERROR",
        message: response.statusText,
        details: null,
      };
      try {
        const json = await response.json();
        if (json && typeof json === "object" && "error" in json && typeof json.error === "object" && json.error !== null) {
          errBody = json.error as typeof errBody;
        } else if (json && typeof json === "object") {
          errBody = json as typeof errBody;
        }
      } catch {
        // Fall back to status text
      }

      if (response.status === 409 || errBody.code === "VERSION_CONFLICT") {
        throw new VersionConflictError(errBody.message || "Conflict", errBody.details as Record<string, unknown> | null);
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

  async getStore(id: string): Promise<Store> {
    if (this.useDoubles) {
      const store = this.doubleStores.find((s) => s.id === id);
      if (!store) throw new ApiRequestError(404, "NOT_FOUND", "Store not found");
      return store;
    }
    return this.fetch<Store>(`/stores/${id}`);
  }

  async getStoreHealth(id: string): Promise<Schemas["StoreHealth"]> {
    if (this.useDoubles) {
      const store = this.doubleStores.find((s) => s.id === id);
      if (!store) throw new ApiRequestError(404, "NOT_FOUND", "Store not found");
      const health = MOCK_STORE_HEALTH[id] || {
        store,
        metrics: null,
        readiness: ["PROMOTION_ACTIVE", "DATA_CURRENT"],
        freshness: "CURRENT" as const,
      };
      return health;
    }
    return this.fetch<Schemas["StoreHealth"]>(`/stores/${id}/health`);
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

  // --- Media ---
  async initMedia(data: Schemas["MediaInit"]): Promise<Schemas["MediaUpload"]> {
    if (this.useDoubles) {
      const mediaId = generateUuid();
      const media: Media = {
        id: mediaId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        kind: data.kind,
        filename: data.filename,
        mime_type: data.mime_type,
        byte_size: data.byte_size,
        original_sha256: data.sha256,
        normalized_sha256: null,
        status: "PENDING_UPLOAD",
        store_id: data.store_id || null,
        visit_id: data.visit_id || null,
        product_id: data.product_id || null,
        zone_id: data.zone_id || null,
        zone_kind: data.zone_kind || null,
        captured_at: data.captured_at || new Date().toISOString(),
        width: 1024,
        height: 768,
        rejection: null,
        download_url: `http://localhost:8000/media/${mediaId}`,
        download_url_expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
      };
      this.doubleMedia.unshift(media);
      return {
        media,
        upload_url: `http://localhost:8000/media/upload/${mediaId}`,
        method: "PUT",
        headers: { "Content-Type": data.mime_type },
        expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
      };
    }
    return this.fetch<Schemas["MediaUpload"]>("/media", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async completeMedia(mediaId: string, data: Schemas["VersionCommand"]): Promise<Media> {
    if (this.useDoubles) {
      const idx = this.doubleMedia.findIndex((m) => m.id === mediaId);
      if (idx !== -1) {
        this.doubleMedia[idx].status = "READY";
        this.doubleMedia[idx].version += 1;
        this.doubleMedia[idx].updated_at = new Date().toISOString();
        return this.doubleMedia[idx];
      }
      const media: Media = {
        id: mediaId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 2,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        kind: "VISIT_BEFORE",
        filename: "uploaded.jpg",
        mime_type: "image/jpeg",
        byte_size: 1024,
        original_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        normalized_sha256: null,
        status: "READY",
        store_id: null,
        visit_id: null,
        product_id: null,
        zone_id: null,
        zone_kind: null,
        captured_at: new Date().toISOString(),
        width: 1024,
        height: 768,
        rejection: null,
        download_url: `http://localhost:8000/media/${mediaId}`,
        download_url_expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
      };
      this.doubleMedia.unshift(media);
      return media;
    }
    return this.fetch<Media>(`/media/${mediaId}/complete`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getMedia(mediaId: string): Promise<Media> {
    if (this.useDoubles) {
      const media = this.doubleMedia.find((m) => m.id === mediaId);
      if (media) return media;
      return {
        id: mediaId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        kind: "VISIT_BEFORE",
        filename: "photo.jpg",
        mime_type: "image/jpeg",
        byte_size: 1024,
        original_sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        normalized_sha256: null,
        status: "READY",
        store_id: null,
        visit_id: null,
        product_id: null,
        zone_id: null,
        zone_kind: null,
        captured_at: new Date().toISOString(),
        width: 1024,
        height: 768,
        rejection: null,
        download_url: `http://localhost:8000/media/${mediaId}`,
        download_url_expires_at: new Date(Date.now() + 3600 * 1000).toISOString(),
      };
    }
    return this.fetch<Media>(`/media/${mediaId}`);
  }

  // --- Visits ---
  async listVisits(params?: { store_id?: string; limit?: number; cursor?: string }): Promise<{ items: Visit[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      let items = [...this.doubleVisits];
      if (params?.store_id) {
        items = items.filter((v) => v.store_id === params.store_id);
      }
      return { items, next_cursor: null };
    }
    const query = new URLSearchParams();
    if (params?.store_id) query.set("store_id", params.store_id);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.cursor) query.set("cursor", params.cursor);
    const qs = query.toString();
    return this.fetch<{ items: Visit[]; next_cursor: string | null }>(`/visits${qs ? `?${qs}` : ""}`);
  }

  async createVisit(data: Schemas["VisitCreate"]): Promise<Visit> {
    if (this.useDoubles) {
      const newVisit: Visit = {
        id: generateUuid(),
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        store_id: data.store_id,
        notes: data.notes || "",
        visit_started_at: new Date().toISOString(),
        status: "OPEN",
        before_media_ids: [],
        after_media_ids: [],
        active_investigation_id: null,
        report_ids: [],
      };
      this.doubleVisits.unshift(newVisit);
      return newVisit;
    }
    return this.fetch<Visit>("/visits", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getVisit(visitId: string): Promise<Visit> {
    if (this.useDoubles) {
      const visit = this.doubleVisits.find((v) => v.id === visitId);
      if (!visit) throw new ApiRequestError(404, "NOT_FOUND", "Visit not found");
      return visit;
    }
    return this.fetch<Visit>(`/visits/${visitId}`);
  }

  async updateVisit(visitId: string, data: Schemas["VisitUpdate"]): Promise<Visit> {
    if (this.useDoubles) {
      const idx = this.doubleVisits.findIndex((v) => v.id === visitId);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Visit not found");
      const current = this.doubleVisits[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Visit has been modified concurrently. Expected version mismatch.");
      }
      const updated: Visit = {
        ...current,
        notes: data.notes !== undefined ? data.notes : current.notes,
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleVisits[idx] = updated;
      return updated;
    }
    return this.fetch<Visit>(`/visits/${visitId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  // --- Investigations ---
  async listInvestigations(params?: { visit_id?: string; store_id?: string; limit?: number; cursor?: string }): Promise<{ items: Investigation[]; next_cursor: string | null }> {
    if (this.useDoubles) {
      let items = [...this.doubleInvestigations];
      if (params?.visit_id) items = items.filter((inv) => inv.visit_id === params.visit_id);
      if (params?.store_id) items = items.filter((inv) => inv.store_id === params.store_id);
      return { items, next_cursor: null };
    }
    const query = new URLSearchParams();
    if (params?.visit_id) query.set("visit_id", params.visit_id);
    if (params?.store_id) query.set("store_id", params.store_id);
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.cursor) query.set("cursor", params.cursor);
    const qs = query.toString();
    return this.fetch<{ items: Investigation[]; next_cursor: string | null }>(`/investigations${qs ? `?${qs}` : ""}`);
  }

  async createInvestigation(data: Schemas["InvestigationCreate"]): Promise<Job> {
    if (this.useDoubles) {
      const invId = generateUuid();
      const jobId = generateUuid();
      const newInv: Investigation = {
        id: invId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        store_id: data.store_id,
        visit_id: data.visit_id,
        promotion_id: data.promotion_id,
        policy_version_id: "00000000-0000-0000-0000-000000000071",
        snapshot_id: generateUuid(),
        state: "PROPOSED",
        snapshot_at: new Date().toISOString(),
        metrics: null,
        diagnosis: {
          hypothesis: "EXECUTION",
          support: "SUPPORTED",
          summary: "Detected missing facings on shelf-main.",
          claims: [
            {
              id: generateUuid(),
              kind: "OBSERVATION",
              text: "Facing count is below promotion minimum.",
              evidence_ids: data.media_ids,
            },
          ],
          alternatives: [],
          unresolved_questions: [],
        },
        actions: [
          {
            id: generateUuid(),
            kind: "RESTORE_FACINGS",
            rule_ids: ["00000000-0000-0000-0000-000000000051"],
            claim_ids: [],
            evidence_ids: data.media_ids,
            instruction: "Restore facings to policy minimum on shelf-main.",
            required_zone_ids: ["shelf-main"],
            status: "OPEN",
          },
        ],
        plan_revision: 1,
        accepted_at: null,
        accepted_by: null,
        current_job_id: jobId,
        latest_verification_id: null,
        policy_stale: false,
      };
      this.doubleInvestigations.unshift(newInv);
      const newJob: Job = {
        id: jobId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        type: "INVESTIGATE",
        status: "SUCCEEDED",
        resource_id: invId,
        resource_type: "INVESTIGATION",
        attempt: 1,
        stage: "COMPLETE",
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        error: null,
        linked_previous_job_id: null,
        model_id: "gemini-2.5-flash",
        usage: null,
      };
      this.doubleJobs.unshift(newJob);
      return newJob;
    }
    return this.fetch<Job>("/investigations", {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async getInvestigation(investigationId: string): Promise<Investigation> {
    if (this.useDoubles) {
      const inv = this.doubleInvestigations.find((i) => i.id === investigationId);
      if (!inv) throw new ApiRequestError(404, "NOT_FOUND", "Investigation not found");
      return inv;
    }
    return this.fetch<Investigation>(`/investigations/${investigationId}`);
  }

  async acceptInvestigation(investigationId: string, data: Schemas["VersionCommand"]): Promise<Investigation> {
    if (this.useDoubles) {
      const idx = this.doubleInvestigations.findIndex((i) => i.id === investigationId);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Investigation not found");
      const current = this.doubleInvestigations[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Investigation has been modified concurrently. Expected version mismatch.");
      }
      const updated: Investigation = {
        ...current,
        state: "ACCEPTED",
        accepted_at: new Date().toISOString(),
        accepted_by: "00000000-0000-0000-0000-000000000008",
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleInvestigations[idx] = updated;
      return updated;
    }
    return this.fetch<Investigation>(`/investigations/${investigationId}/accept`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async dismissInvestigation(investigationId: string, data: Schemas["Dismiss"]): Promise<Investigation> {
    if (this.useDoubles) {
      const idx = this.doubleInvestigations.findIndex((i) => i.id === investigationId);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Investigation not found");
      const current = this.doubleInvestigations[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Investigation has been modified concurrently. Expected version mismatch.");
      }
      const updated: Investigation = {
        ...current,
        state: "DISMISSED",
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleInvestigations[idx] = updated;
      return updated;
    }
    return this.fetch<Investigation>(`/investigations/${investigationId}/dismiss`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async updateAction(investigationId: string, actionId: string, data: Schemas["ActionUpdate"]): Promise<Investigation> {
    if (this.useDoubles) {
      const idx = this.doubleInvestigations.findIndex((i) => i.id === investigationId);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Investigation not found");
      const current = this.doubleInvestigations[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Investigation has been modified concurrently. Expected version mismatch.");
      }
      const updatedActions = current.actions.map((act) => {
        if (act.id === actionId) {
          return { ...act, status: data.status as "OPEN" | "CLAIMED_DONE" };
        }
        return act;
      });
      const updated: Investigation = {
        ...current,
        actions: updatedActions,
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleInvestigations[idx] = updated;
      return updated;
    }
    return this.fetch<Investigation>(`/investigations/${investigationId}/actions/${actionId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  }

  // --- Verification & Reports ---
  async verifyInvestigation(investigationId: string, data: Schemas["VerifyRequest"]): Promise<Job> {
    if (this.useDoubles) {
      const idx = this.doubleInvestigations.findIndex((i) => i.id === investigationId);
      if (idx === -1) throw new ApiRequestError(404, "NOT_FOUND", "Investigation not found");
      const current = this.doubleInvestigations[idx];
      if (current.version !== data.expected_version) {
        throw new VersionConflictError("Investigation has been modified concurrently. Expected version mismatch.");
      }
      const verifId = generateUuid();
      const reportId = generateUuid();
      const jobId = generateUuid();

      const newReport: Report = {
        id: reportId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        visit_id: current.visit_id,
        investigation_id: current.id,
        verification_id: verifId,
        created_at: new Date().toISOString(),
        outcome: "PASS",
        summary: "Shelf facings verified compliant after action.",
        checks: [
          {
            rule_id: "00000000-0000-0000-0000-000000000051",
            result: "PASS",
            evidence_ids: data.after_media_ids,
            explanation: "Observed target facings restored.",
          },
        ],
        evidence_ids: data.after_media_ids,
        policy_version_id: current.policy_version_id,
      };
      this.doubleReports.unshift(newReport);

      const newVerif: Verification = {
        id: verifId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        investigation_id: current.id,
        plan_revision: current.plan_revision,
        after_media_ids: data.after_media_ids,
        job_id: jobId,
        checks: newReport.checks,
        result: "PASS",
        requested_retakes: [],
        report_id: reportId,
      };
      this.doubleVerifications.unshift(newVerif);

      const updatedInv: Investigation = {
        ...current,
        state: "RESOLVED",
        latest_verification_id: verifId,
        version: current.version + 1,
        updated_at: new Date().toISOString(),
      };
      this.doubleInvestigations[idx] = updatedInv;

      // Close the visit upon PASS
      const visitIdx = this.doubleVisits.findIndex((v) => v.id === current.visit_id);
      if (visitIdx !== -1) {
        this.doubleVisits[visitIdx].status = "CLOSED";
        this.doubleVisits[visitIdx].version += 1;
        this.doubleVisits[visitIdx].updated_at = new Date().toISOString();
      }

      const newJob: Job = {
        id: jobId,
        workspace_id: this.getWorkspaceId() || DEFAULT_WORKSPACE_ID,
        version: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        type: "VERIFY",
        status: "SUCCEEDED",
        resource_id: verifId,
        resource_type: "VERIFICATION",
        attempt: 1,
        stage: "COMPLETE",
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
        error: null,
        linked_previous_job_id: null,
        model_id: "gemini-2.5-flash",
        usage: null,
      };
      this.doubleJobs.unshift(newJob);
      return newJob;
    }
    return this.fetch<Job>(`/investigations/${investigationId}/verify`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  }

  async listVerifications(investigationId: string): Promise<{ items: Verification[] }> {
    if (this.useDoubles) {
      return {
        items: this.doubleVerifications.filter((v) => v.investigation_id === investigationId),
      };
    }
    return this.fetch<{ items: Verification[] }>(`/investigations/${investigationId}/verifications`);
  }

  async getVerification(verificationId: string): Promise<Verification> {
    if (this.useDoubles) {
      const verif = this.doubleVerifications.find((v) => v.id === verificationId);
      if (!verif) throw new ApiRequestError(404, "NOT_FOUND", "Verification not found");
      return verif;
    }
    return this.fetch<Verification>(`/verifications/${verificationId}`);
  }

  async getReport(reportId: string): Promise<Report> {
    if (this.useDoubles) {
      const report = this.doubleReports.find((r) => r.id === reportId);
      if (!report) throw new ApiRequestError(404, "NOT_FOUND", "Report not found");
      return report;
    }
    return this.fetch<Report>(`/reports/${reportId}`);
  }

  // --- Jobs & Events ---
  async getJob(jobId: string): Promise<Job> {
    if (this.useDoubles) {
      const job = this.doubleJobs.find((j) => j.id === jobId);
      if (!job) throw new ApiRequestError(404, "NOT_FOUND", "Job not found");
      return job;
    }
    return this.fetch<Job>(`/jobs/${jobId}`);
  }

  async getJobEvents(jobId: string, params?: { limit?: number; after_sequence?: number }): Promise<Schemas["JobEvents"]> {
    if (this.useDoubles) {
      let items = this.doubleJobEvents.filter((e) => e.job_id === jobId);
      if (params?.after_sequence !== undefined) {
        items = items.filter((e) => e.sequence > params.after_sequence!);
      }
      const last_sequence = items.length > 0 ? items[items.length - 1].sequence : 0;
      return { items, last_sequence };
    }
    const query = new URLSearchParams();
    if (params?.limit) query.set("limit", String(params.limit));
    if (params?.after_sequence !== undefined) query.set("after_sequence", String(params.after_sequence));
    const qs = query.toString();
    return this.fetch<Schemas["JobEvents"]>(`/jobs/${jobId}/events${qs ? `?${qs}` : ""}`);
  }
}

export const apiClient = new StoreOpsClient();
