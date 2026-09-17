# StoreOps: Clean Installation & Empty Workspace Acceptance Guide

This guide describes how to deploy, initialize, and accept the StoreOps Autonomous Retail Operations Intelligence MVP from an empty install, without importing any sample fixtures, evaluation labels, or demo seed data (conforming to **AC01**, **AC23**, **AC24**, **AC26**, and **AC31**).

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
  "full_openapi_meta_validation": "passed",
  "requirements": 15,
  "tasks": 15,
  "acceptance_cases": 41
}
```

---

## 3. Environment Profiles & Configuration

StoreOps provides two isolated execution profiles per `specs/01-architecture.md`:
1. **`LOCAL` profile**: In-memory state, local DuckDB analytics, local filesystem media storage, and deterministic model gateways. Zero external network access or GCP credentials required.
2. **`CLOUD` profile**: Google Cloud Firestore, BigQuery, Google Cloud Storage, Cloud Tasks, Cloud Run, and live Google Gemini API (`gemini-2.5-pro` and `gemini-2.5-flash`).

### Local Mode Configuration
Copy the default environment configuration:
```bash
cp .env.example .env
```
Ensure the following settings are present in `.env`:
```ini
STOREOPS_PROFILE=LOCAL
AI_MODE=STUB
PORT=8000
WEB_PORT=3000
LOG_LEVEL=INFO
LOCAL_STORAGE_DIR=.local_storage/media
DUCKDB_PATH=:memory:
```

### Anti-Fabrication Rule (AC26)
Per `specs/06-quality.md`, if `STOREOPS_PROFILE=CLOUD` is specified, the application will refuse to start if any stub, emulator, or in-memory adapter is configured. Local mode is always explicitly labeled.

---

## 4. Database Migration & Tenant Initialization

### Step 1: Run Migrations (`make migrate`)
Apply versioned schema migrations:
```bash
make migrate
```
In `LOCAL` mode, this initializes the DuckDB analytics schema, memory state structures, and filesystem directories.

### Step 2: Bootstrap an Empty Workspace (`make bootstrap-admin`)
Provision a brand-new workspace for an administrative user:
```bash
make bootstrap-admin \
  NAME="Acme Retail West" \
  BRAND="Acme Beverages" \
  CURRENCY="USD" \
  UID="admin-usr-001" \
  EMAIL="admin@acmeretail.com"
```
The command outputs the new workspace details:
```json
{
  "workspace_id": "8f3b2049-7104-4ec2-881b-59d0458b0932",
  "name": "Acme Retail West",
  "brand": "Acme Beverages",
  "currency": "USD",
  "admin_uid": "admin-usr-001"
}
```

### Step 3: Add a Field Representative Member (`make add-member`)
Add a field sales representative to the workspace:
```bash
make add-member \
  WORKSPACE_ID="8f3b2049-7104-4ec2-881b-59d0458b0932" \
  UID="rep-usr-101" \
  ROLE="REP" \
  EMAIL="rep101@acmeretail.com"
```

---

## 5. Starting the Application Services (`make dev`)

Launch the local development environment:
```bash
make dev
```
This starts:
- **FastAPI Backend Server**: Running on `http://127.0.0.1:8000` (API documentation at `/docs` and OpenAPI JSON at `/openapi.json`).
- **Background Worker**: Processing asynchronous jobs (imports, investigations, verifications) via generation-fenced leases and transactional outbox.
- **Next.js Web Management Console**: Running on `http://127.0.0.1:3000`.

---

## 6. Verifying the Clean Empty State (AC01 & AC23)

Before populating any records, verify that the application returns clean empty states rather than errors or sample data:

```bash
# Check stores (returns empty array)
curl -s -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
     http://127.0.0.1:8000/stores | jq .

# Check products (returns empty array)
curl -s -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
     http://127.0.0.1:8000/products | jq .

# Check promotions (returns empty array)
curl -s -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
     http://127.0.0.1:8000/promotions | jq .

# Check visits (returns empty array)
curl -s -H "Authorization: Bearer rep-usr-101" \
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
     http://127.0.0.1:8000/visits | jq .
```
In the Web UI (`http://127.0.0.1:3000`), navigate to the dashboard. The UI explicitly renders:
- "No stores configured yet"
- "No sales data"
- "Stock unknown"
- "No active promotions"

---

## 7. Standard Ingestion CSV Specifications & Templates

StoreOps ingests daily point-of-sale transactions and distribution inventory via standard CSV files conforming to `contracts/imports.json`.

### A. Sales CSV Specification (`SALES`)
- **Header Line**: `store_code,sku,business_date,units,revenue,currency`
- **Validation Rules**:
  - `store_code`: String matching a registered store code in the workspace.
  - `sku`: String matching an active product SKU.
  - `business_date`: ISO-8601 date (`YYYY-MM-DD`). Cannot be more than 1 day in the future.
  - `units`: Integer ≥ 0.
  - `revenue`: Decimal number ≥ 0.00 (two decimal places).
  - `currency`: 3-letter ISO code matching workspace currency (`USD`, `SGD`, `AUD`, `EUR`, `GBP`).

#### `sales_template.csv` Example:
```csv
store_code,sku,business_date,units,revenue,currency
STR-001,SKU-WAT-01,2026-09-14,48,96.00,USD
STR-001,SKU-WAT-01,2026-09-15,36,72.00,USD
STR-002,SKU-WAT-01,2026-09-15,24,48.00,USD
```

### B. Inventory CSV Specification (`INVENTORY`)
- **Header Line**: `location_code,sku,observed_at,quantity,unit`
- **Validation Rules**:
  - `location_code`: String matching either a distributor location code (`LOC-...`) or store backroom (`<STORE_CODE>-BACKROOM`).
  - `sku`: String matching an active product SKU.
  - `observed_at`: ISO-8601 timestamp in UTC (`YYYY-MM-DDTHH:MM:SSZ`).
  - `quantity`: Integer ≥ 0.
  - `unit`: String (`CASES` or `UNITS`).

#### `inventory_template.csv` Example:
```csv
location_code,sku,observed_at,quantity,unit
LOC-DIST-WEST,SKU-WAT-01,2026-09-15T08:00:00Z,250,CASES
STR-001-BACKROOM,SKU-WAT-01,2026-09-15T08:30:00Z,12,CASES
```

---

## 8. First-Run Acceptance Walkthrough (AC31)

Follow these steps to exercise the complete business loop in a fresh workspace without demo seed scripts:

### Step 1: Create Catalog Locations & Stores (ADMIN)
1. **Create Distributor Location**:
   ```bash
   curl -X POST http://127.0.0.1:8000/locations \
     -H "Authorization: Bearer admin-usr-001" \
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
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
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
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
     -H "X-Workspace-Id: 8f3b2049-7104-4ec2-881b-59d0458b0932" \
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
   - `rules: [{"kind": "MIN_FACINGS", "min_facings": 3, "zone_id": "shelf-beverage", "product_id": "<PRODUCT_ID>"}]`

### Step 4: Conduct Rep Field Visit & Trigger Investigation (REP)
1. Rep starts store visit: `POST /visits` with `store_id: "<STORE_ID>"`.
2. Upload before-image of shelf: `POST /media` with `kind: "VISIT_BEFORE"`, PUT image bytes, and complete.
3. Launch investigation: `POST /investigations` with `visit_id`, `store_id`, `promotion_id`, `media_ids: ["<BEFORE_MEDIA_ID>"]`.
4. System investigates: analyzes POS sales trends, backroom inventory stocks, planogram contracts, and visual shelf facings. Returns synthesized diagnosis and actionable plan (≤ 3 actions).

### Step 5: Execute & Verify Merchandising (REP)
1. Rep accepts plan: `POST /investigations/{id}/accept`.
2. Rep restsocks shelf and marks action: `PATCH /investigations/{id}/actions/{action_id}` with `status: "CLAIMED_DONE"`.
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
