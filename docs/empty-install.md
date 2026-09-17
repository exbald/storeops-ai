# StoreOps: Clean Installation & Empty Workspace Acceptance Guide

This guide describes how to deploy, initialize, and accept the StoreOps Autonomous Retail Operations Intelligence MVP from an empty install, without importing any sample fixtures, evaluation labels, or demo seed data (conforming to **AC01**, **AC24**, **AC26**, and **AC31**; related empty-state verification in **AC23**).

---

## 1. System Requirements & Prerequisites

StoreOps enforces pinned runtimes and package managers as documented in [versions.md](versions.md).

| Runtime / Tool | Required Version | Verification Command | Notes |
| :--- | :--- | :--- | :--- |
| **Python** | `3.11+` (tested on 3.12.9) | `python3 --version` | Standard Python interpreter |
| **uv** | `0.11+` | `uv --version` | Package & virtualenv manager |
| **Node.js** | `v20+` (tested on v24.11) | `node --version` | JavaScript/TypeScript runtime |
| **pnpm** | `10.0+` | `pnpm --version` | Monorepo package manager |
| **Make** | Any standard POSIX make | `make --version` | Command runner interface |
| **Docker** | Engine 20+ (Optional) | `docker --version` | Optional for local GCP emulator containers |

---

## 2. Installation & Dependency Setup

### Step 1: Clone the Repository
```bash
git clone https://github.com/exbald/storeops-ai.git
cd storeops-ai
```

### Step 2: Install Pinned Dependencies (`make setup`)
Execute `make setup` to install exact locked dependencies across Python and Node workspaces. This does **not** create cloud resources, make network requests outside dependency mirrors, or inject sample business data:
```bash
make setup
```

### Step 3: Validate Frozen Contracts & Specification Integrity
Verify that contracts, OpenAPI definitions, JSON schemas, tool definitions, and task dependency DAGs are 100% compliant:
```bash
make verify-spec
```
Expected output:
```json
{
  "status": "passed",
  "kind": "specification_integrity_only",
  "application_tests": "not_run",
  "full_openapi_meta_validation": "passed",
  "requirements": 15,
  "tasks": 15,
  "acceptance_cases": 41,
  "api_operations": 49,
  "api_schemas": 69,
  "ai_definitions": 10,
  "schema_refs_checked": 598,
  "schema_examples_checked": 13,
  "typed_tool_contracts": 7,
  "tool_schema_refs_checked": 15,
  "local_links_checked": 67
}
```

---

## 3. Environment Profiles & Configuration

StoreOps provides two isolated execution profiles per `specs/01-architecture.md` and `apps/api/core/config.py`:
1. **`LOCAL` profile**: In-memory state, local DuckDB analytics, local filesystem media storage, and deterministic model gateways. Zero external network access or GCP credentials required.
2. **`CLOUD` profile**: Google Cloud Firestore, BigQuery, Google Cloud Storage, Cloud Tasks, Cloud Run, and live Google Gemini API (`gemini-2.5-pro` and `gemini-2.5-flash`).

### Local Mode Configuration
Copy the default environment configuration template from `.env.example`:
```bash
cp .env.example .env
```
Ensure the following settings are present in `.env` (matching `apps/api/core/config.py` and `.env.example`):
```ini
APP_ENV=development
PROFILE=LOCAL
AI_MODE=STUB
PORT=8000
MEDIA_STORAGE_DIR=.local_storage/media
STATE_BACKEND=in_memory
FIREBASE_PROJECT_ID=storeops-dev
```

### Anti-Fabrication Rule (AC26)
Per `specs/06-quality.md`, if `PROFILE=CLOUD` is specified, the application will refuse to start if any stub, emulator, or in-memory adapter is configured (`AI_MODE=STUB` or `STATE_BACKEND=in_memory`). Local mode is always explicitly labeled.

---

## 4. Database Migration & Tenant Initialization

### Step 1: Run Migrations (`make migrate`)
Confirm database migration readiness:
```bash
make migrate
```
In `LOCAL` mode, `make migrate` verifies the existence of the `migrations/` directory and confirms readiness. DuckDB tables and analytical views are initialized dynamically on first access, while in-memory state structures require no upfront DDL. In `CLOUD` mode, BigQuery dataset and Firestore indexes are provisioned via Terraform as detailed in `infra/`.

### Step 2: Bootstrap an Empty Workspace
Provision an empty workspace with an initial administrative user using `scripts/bootstrap.py`:
```bash
uv run python3 scripts/bootstrap.py \
  --workspace-name="Acme Retail West" \
  --brand-name="Acme Beverages" \
  --currency="USD" \
  --admin-uid="admin-usr-001" \
  --email="admin@acmeretail.com"
```
The command outputs:
```
Successfully bootstrapped workspace 'Acme Retail West' (<WORKSPACE_UUID>) with admin 'admin-usr-001'.
Currency: USD, Brand: Acme Beverages
```

*(Note on `STATE_BACKEND`: In `LOCAL` mode with `STATE_BACKEND=in_memory`, state resides in process memory. In `CLOUD` mode or when using `STATE_BACKEND=firestore`, state persists across CLI invocations. For multi-step CLI operations against Firestore, or when running the HTTP server, operations can also be executed directly via the REST API).*

### Step 3: Add a Member (Optional CLI)
To provision an additional user in a persistent Firestore backend:
```bash
uv run python3 scripts/bootstrap.py \
  --add-member \
  --workspace-id="<WORKSPACE_UUID>" \
  --uid="rep-usr-101" \
  --role="REP" \
  --email="rep101@acmeretail.com"
```
The command outputs:
```
Successfully added user 'rep-usr-101' with role 'REP' to workspace '<WORKSPACE_UUID>'.
```

---

## 5. Starting Application Services

StoreOps separates the HTTP API, background asynchronous workers, and the web frontend:

### 1. API Server (`make dev`)
Start the FastAPI server:
```bash
make dev
```
*(Executes `uv run uvicorn apps.api.main:app --reload --port 8000`). The OpenAPI documentation is available at `http://127.0.0.1:8000/docs` and OpenAPI schema at `/openapi.json`.*

### 2. Background Worker
In a separate terminal, start the asynchronous background worker to process imports, investigations, and verification jobs:
```bash
uv run python3 apps/api/worker.py
```

### 3. Web Management Console
In a separate terminal, launch the Next.js development server:
```bash
pnpm --filter web dev
```
The web dashboard is available at `http://127.0.0.1:3000`.

---

## 6. Verifying the Clean Empty State (AC01 & AC23)

Before populating any records, verify that the application returns clean empty envelopes (`{"items": []}`) rather than fake seed records:

```bash
# Check stores (returns empty envelope {"items": []})
curl -s -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     http://127.0.0.1:8000/stores | jq .items
# Output: []

# Check products (returns empty envelope {"items": []})
curl -s -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     http://127.0.0.1:8000/products | jq .items
# Output: []

# Check promotions (returns empty envelope {"items": []})
curl -s -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     http://127.0.0.1:8000/promotions | jq .items
# Output: []

# Check visits (returns empty envelope {"items": []})
curl -s -H "Authorization: Bearer rep-usr-101" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     http://127.0.0.1:8000/visits | jq .items
# Output: []
```

In the Web UI (`http://127.0.0.1:3000`), navigating to the dashboard renders honest empty state strings:
- *"No sales data"* (for empty revenue/sales metrics via `formatSales` and `formatRevenue`)
- *"Stock unknown"* (for unobserved inventory metrics via `formatStock`)
- *"Insufficient comparison data"* (for opportunity projections via `formatOpportunityProxy`)
- *"No stores found. Create your first store to get started."* (on the stores management view)
- *"No products in catalog. Add your first product to configure merchandising rules."* (on the catalog view)
- *"No promotions or agreements registered. Create your first promotion to extract policy rules."* (on the promotions view)

---

## 7. Standard Ingestion CSV Specifications & Templates

StoreOps ingests daily point-of-sale transactions and distribution inventory via standard CSV files strictly conforming to `contracts/imports.json`.

### A. Sales CSV Specification (`SALES`)
- **Header Line**: `store_code,sku,business_date,units,revenue,currency`
- **Validation Rules**:
  - `store_code`: String (`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`) matching an active store code in the workspace.
  - `sku`: String (`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`) matching an active product SKU in the workspace.
  - `business_date`: ISO-8601 date (`YYYY-MM-DD`). Future business dates are **invalid** (`imports.json:59`).
  - `units`: Integer ≥ 0. Explicit zero rows establish zero sales.
  - `revenue`: Decimal string with exactly two fractional digits (e.g., `96.00`). Pattern: `^\d+\.\d{2}$`.
  - `currency`: 3-letter ISO code strictly matching workspace currency. Allowed enum: `["SGD", "USD", "AUD"]`.

#### Valid `sales_template.csv`:
```csv
store_code,sku,business_date,units,revenue,currency
STR-001,SKU-WAT-01,2026-09-14,48,96.00,USD
STR-001,SKU-WAT-01,2026-09-15,36,72.00,USD
STR-002,SKU-WAT-01,2026-09-15,24,48.00,USD
```

### B. Inventory CSV Specification (`INVENTORY`)
- **Header Line**: `location_code,sku,observed_at,quantity,unit`
- **Validation Rules**:
  - `location_code`: String (`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`) matching a distributor location code or store backroom (`<STORE_CODE>-BACKROOM`).
  - `sku`: String matching an active product SKU.
  - `observed_at`: ISO-8601 UTC timestamp (`YYYY-MM-DDTHH:MM:SSZ`). Future timestamps beyond a 5-minute clock tolerance are **invalid** (`imports.json:104`).
  - `quantity`: Integer ≥ 0.
  - `unit`: String enum strictly matching `["UNIT", "CASE"]` (singular).

#### Valid `inventory_template.csv`:
```csv
location_code,sku,observed_at,quantity,unit
LOC-DIST-WEST,SKU-WAT-01,2026-09-15T08:00:00Z,250,CASE
STR-001-BACKROOM,SKU-WAT-01,2026-09-15T08:30:00Z,12,UNIT
```

---

## 8. First-Run Acceptance Walkthrough (AC31)

Follow these steps to exercise the complete business loop in a fresh workspace without demo seed scripts:

### Step 1: Create Catalog Locations & Stores (ADMIN)
1. **Create Distributor Location**:
   ```bash
   curl -X POST http://127.0.0.1:8000/locations \
     -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     -H "Idempotency-Key: loc-dist-west-01" \
     -H "Content-Type: application/json" \
     -d '{
       "code": "LOC-DIST-WEST",
       "name": "West Regional Distribution Hub",
       "type": "DISTRIBUTOR"
     }'
   ```
2. **Create Retail Store**:
   ```bash
   curl -X POST http://127.0.0.1:8000/stores \
     -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     -H "Idempotency-Key: store-str-001" \
     -H "Content-Type: application/json" \
     -d '{
       "code": "STR-001",
       "name": "Market Street Supermarket",
       "retailer": "Grand Retail",
       "region": "West",
       "format": "SUPERMARKET",
       "timezone": "America/Los_Angeles",
       "distributor_location_id": "<DISTRIBUTOR_LOCATION_ID>"
     }'
   ```
3. **Register Product**:
   ```bash
   curl -X POST http://127.0.0.1:8000/products \
     -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: <WORKSPACE_UUID>" \
     -H "Idempotency-Key: prod-wat-01" \
     -H "Content-Type: application/json" \
     -d '{
       "sku": "SKU-WAT-01",
       "name": "Spring Water 500ml",
       "case_units": 24
     }'
   ```

### Step 2: Upload and Commit CSV Telemetry (ADMIN)
1. Request upload URL via `POST /media` with `kind: "IMPORT"`.
2. Upload CSV content via `PUT` to the returned upload URL.
3. Complete upload via `POST /media/{media_id}/complete`.
4. Stage import via `POST /imports` (`kind: "SALES"`, `media_id`).
5. Commit import atomically via `POST /imports/{import_id}/commit` (`expected_version: 1`).

### Step 3: Author and Approve Promotional Policy (ADMIN)
1. Create draft promotion via `POST /promotions`.
2. Approve promotional agreement rules via `POST /promotions/{promo_id}/approve` specifying:
   - `expected_version: 1`
   - `catalog_product_ids: ["<PRODUCT_ID>"]`
   - `rules: [{"rule_id": "<RULE_UUID>", "kind": "MIN_FACINGS", "min_facings": 3, "zone_id": "shelf-beverage", "zone_kind": "SHELF", "product_id": "<PRODUCT_ID>", "source": {"kind": "MANUAL", "reviewer_note": "Mandatory 3 facings agreement"}}]`

### Step 4: Conduct Rep Field Visit & Trigger Investigation (REP)
1. Rep starts store visit: `POST /visits` with `store_id: "<STORE_ID>"`.
2. Upload before-image of shelf: `POST /media` with `kind: "VISIT_BEFORE"`, PUT image bytes, and complete.
3. Launch investigation: `POST /investigations` with `visit_id`, `store_id`, `promotion_id`, `media_ids: ["<BEFORE_MEDIA_ID>"]`.
4. System investigates: analyzes POS sales trends, backroom inventory stocks, planogram contracts, and visual shelf facings. Returns synthesized diagnosis and actionable plan (≤ 3 actions).

### Step 5: Execute & Verify Merchandising (REP)
1. Rep accepts plan: `POST /investigations/{id}/accept`.
2. Rep restocks shelf and marks action: `PATCH /investigations/{id}/actions/{action_id}` with `status: "CLAIMED_DONE"`.
3. Rep uploads after-image: `POST /media` with `kind: "VISIT_AFTER"`, PUT image bytes, and complete.
4. Rep triggers verification: `POST /investigations/{id}/verify` with `after_media_ids: ["<AFTER_MEDIA_ID>"]`.
5. Multimodal verifier assesses after-photo against policy rules:
   - On `PASS`: Atomic resolution marks actions `VERIFIED`, closes visit (`CLOSED`), and generates an immutable audit report (`GET /reports/{id}`).

---

## 9. Test Suite Verification Commands

To verify all system layers deterministically:
```bash
# Run all unit, contract, integration, and e2e tests
uv run pytest -W ignore

# Run frontend test suite
pnpm --filter web test

# Verify code style and linting
uv run ruff check apps/ tests/ scripts/
```
All suites pass deterministically in under 5 seconds.
