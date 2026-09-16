# Goal: Execute Wave 2 (Core Foundations)

## Objective
Implement and integrate the independent parallel tasks of **Wave 2**:
- **T02**: Catalog, locations and validated media
- **T03**: CSV ingestion, analytics revisions and metric service
- **T05**: Web shell and management screens against frozen contracts
- **T06**: Gemini gateway, observations and investigation reasoning
- **T11**: Provision authorized cloud development deployment

All tasks in Wave 2 are independent of each other and depend strictly on `T01`.

---

## Tasks & Owned Paths

### 1. T02 - Catalog & Media
- **Acceptance IDs**: `AC03`, `AC04`, `AC05`, `AC35`
- **Owned Paths**: `apps/api/modules/catalog/`, `tests/catalog/`
- **Deliverables**: Store, backroom location, and product CRUD; media init/complete flow with content validation and reference binding; archive operations.
- **Gate**: Catalog APIs work on arbitrary IDs with zero prepopulated records; invalid media and archive tests pass.

### 2. T03 - CSV Ingestion & Metric Service
- **Acceptance IDs**: `AC06`, `AC07`, `AC08`, `AC13`, `AC14`
- **Owned Paths**: `apps/api/modules/imports/`, `apps/api/analytics/`, `migrations/bigquery/`, `tests/data/`
- **Deliverables**: CSV schema validation (products, inventory, sales), staging and atomic commit; DuckDB local analytics adapter and BigQuery migrations; deterministic `peer_gap_v1` metric computations.
- **Gate**: Valid/invalid/correcting imports and local math tests pass; cloud parity remains flagged for T12.

### 3. T05 - Web Shell & Management Screens
- **Acceptance IDs**: `AC38`
- **Owned Paths**: `apps/web/`, `tests/web-management/`
- **Design Tokens**: Pre-completed and locked in [DESIGN.md](../../DESIGN.md) (dual-mode Obsidian Glass / Ice Glass tokens ready for Tailwind CSS integration).
- **Deliverables**: Next.js App Router shell; Firebase auth and workspace selector; management pages for stores, products, imports, and policies against generated client contracts.
- **Gate**: Management screens satisfy contracts; mock/fixture doubles isolated to client test suites.

### 4. T06 - Gemini Gateway & Reasoning
- **Acceptance IDs**: `AC39`
- **Owned Paths**: `apps/api/ai/`, `tests/ai/`
- **Deliverables**: Google Gen AI SDK gateway with versioned prompts; structured planogram and visual compliance extractors; read-only investigator tools; strict JSON Schema verification.
- **Gate**: Structured extraction and adversarial tests pass; if live API keys are unavailable, gate is cleanly marked blocked for cloud evaluations.

### 5. T11 - Cloud Deployment Setup
- **Acceptance IDs**: `AC41`
- **Owned Paths**: `infra/`, `scripts/deploy/`, `docs/cloud-setup.md`
- **Deliverables**: Terraform/scaffold for Cloud Run, Cloud Tasks, Cloud Storage, Firestore, and BigQuery; service account configuration and deployment scripts.
- **Gate**: Cloud scaffold validates cleanly; missing cloud credentials produce an explicit blocked gate rather than fake success.

---

## Execution Steps
1. Execute tasks in their respective `owned_paths`. If working sequentially, follow order `T02` -> `T03` -> `T06` -> `T05` -> `T11`.
2. Write test-first failing tests for each task's scoped acceptance criteria before writing implementations.
3. Verify each task suite passes:
   ```bash
   uv run pytest tests/catalog/
   uv run pytest tests/data/
   uv run pytest tests/ai/
   pnpm test # in apps/web if configured
   ```
4. Verify overall integration across all Wave 2 components.
5. Update `status` of `T02`, `T03`, `T05`, `T06`, and `T11` in [plan/tasks.json](../../plan/tasks.json) to `"integrated"`.
6. Submit reviewable handoff per [AGENTS.md](../../AGENTS.md).

---

## Completion Criteria (Do Not Stop Until Satisfied)
- All test suites for T02, T03, T05, T06, and T11 pass.
- No shared contracts or composition roots modified without coordinator review.
- Tasks updated to `"integrated"` in `plan/tasks.json`.
