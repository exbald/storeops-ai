# StoreOps Dependency and Contract Version Ledger

Recorded at interface freeze: 16 September 2026

## 1. Pinned Runtimes & Package Managers

| Runtime / Tool | Version | Verification Command | Notes |
|---|---|---|---|
| **Python** | `3.11.2` | `python3 --version` | Standard Python runtime |
| **uv** | `0.11.13` | `uv --version` | Fast Python package & virtualenv manager |
| **Node.js** | `v24.11.0` | `node --version` | Node LTS / execution environment |
| **pnpm** | `10.30.0` | `pnpm --version` | Workspace package manager |
| **Docker** | Installed | `docker --version` | Local emulator container runtime |

---

## 2. Frozen Contract Manifest (Version 2.0.0)

| Contract File | Version / Standard | Checksum / Status |
|---|---|---|
| `contracts/openapi.json` | OpenAPI `3.1.1` (API v2.0.0) | Meta-validated (`openapi-spec-validator`) |
| `contracts/ai-output.schema.json` | JSON Schema 2020-12 (v2.0.0) | Checked (10 schema definitions) |
| `contracts/tools.json` | v2.0.0 | Checked (7 typed tool definitions) |
| `contracts/states.json` | v2.0.0 | Checked (6 finite state machines) |
| `contracts/imports.json` | v2.0.0 | Checked (SALES & INVENTORY specs) |
| `contracts/examples.json` | v2.0.0 | Checked (13 valid/invalid test cases) |
| `contracts/SEMANTICS.md` | v2.0.0 | Checked (cross-field semantics frozen) |

---

## 3. Pinned Core Dependencies

### Node Workspace (`packages/contracts`, `apps/web`)
- `openapi-typescript`: `7.13.0`
- `typescript`: `5.9.3`

### Python Virtual Environment (`apps/api`, tooling)
- `fastapi`: `0.141.1`
- `pydantic`: `2.13.5`
- `uvicorn`: `0.53.0`
- `google-cloud-firestore`: `2.30.0`
- `duckdb`: `1.5.5`
- `google-genai`: `2.23.0`
- `httpx`: `0.28.1`
- `python-multipart`: `0.0.32`
- `datamodel-code-generator`: `0.81.0`
- `openapi-spec-validator`: `0.9.0`
- `jsonschema`: `4.26.0`

---

## 4. Contract Generation Artifacts

| Source File | Destination Artifact | Generator |
|---|---|---|
| `contracts/openapi.json` | `packages/contracts/src/api.ts` | `openapi-typescript` |
| `contracts/openapi.json` | `packages/contracts/dist/` | `tsc` (bundled ESModule + `.d.ts`) |
| `contracts/openapi.json` | `packages/contracts/python/storeops_contracts/models.py` | `datamodel-code-generator` (Pydantic v2) |

---

## 5. Wave 0 / Gate G0 Verification Ledger

- **Gate G0 Criteria:** Schemas/examples validate and generated artifacts reproduce cleanly.
- **Verification Commands Executed:**
  1. `make verify-spec` → `status: passed`, `full_openapi_meta_validation: passed`.
  2. `make generate-contracts` → generated TypeScript and Python contracts without drift.
- **Gate Status:** **PASSED**.
- **Task T00 Status:** **INTEGRATED**.
- **Unlocked Next Wave:** Wave 1: **Task T01 (Empty identity, persistence and durable job foundation)**.
