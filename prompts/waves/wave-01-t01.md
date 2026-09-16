# Goal: Execute Wave 1 (T01 - Foundation)

## Objective
Implement task **T01**: *Empty identity, persistence and durable job foundation*.
Ensure that an empty authenticated application persists state through restarts without invoking any business seed data, and satisfy acceptance criteria `AC01` and `AC37`.

---

## Task Packet Details
- **Task ID**: `T01`
- **Owner Role**: `foundation`
- **Prerequisites**: `T00` (already integrated)
- **Requirements**: `R01`, `R03`, `R12`, `R14`, `R15`
- **Acceptance IDs**: `AC01`, `AC37`
- **Operation IDs**: `getHealth`, `getMe`, `getWorkspace`, `getJob`, `getJobEvents`, `retryJob`
- **Owned Paths**:
  - `apps/api/core/`
  - `apps/api/ports/`
  - `apps/api/adapters/state/`
  - `apps/api/adapters/blob/`
  - `apps/api/jobs/`
  - `apps/api/main.py`
  - `apps/api/worker.py`
  - `tests/foundation/`
  - `scripts/bootstrap.py`
- **Mandatory References**:
  - [AGENTS.md](../../AGENTS.md)
  - [specs/01-architecture.md](../../specs/01-architecture.md)
  - [specs/02-domain.md](../../specs/02-domain.md)
  - [specs/03-workflows.md](../../specs/03-workflows.md)
  - [contracts/openapi.json](../../contracts/openapi.json)
  - [contracts/SEMANTICS.md](../../contracts/SEMANTICS.md)

---

## Deliverables
1. **Workspace Bootstrap & Membership**: Multi-tenant workspace creation with role preservation (`ADMIN`, `OPERATOR`, `MANAGER`, `AUDITOR`) from Firebase UID without creating sample business records.
2. **State & Blob Ports**: In-memory and Firestore/local filesystem adapters respecting strict port interfaces.
3. **Outbox, Lease Fencing & Idempotency**:
   - Outbox pattern for asynchronous job scheduling.
   - Fencing tokens and lease expiration preventing concurrent job execution.
   - Idempotency key replay returning identical responses or 409 conflict on payload mismatch.
4. **Health & Job Endpoints**: Clean `/health`, `/me`, `/workspaces/{id}`, and job control APIs.

---

## Execution Steps
1. **Baseline Assessment**:
   Run `uv run pytest tests/foundation/` to view the existing failing tests.
2. **TDD Fixes**:
   - Fix role comparison (`Role.ADMIN` vs string representation).
   - Implement PNG/JPEG dimension parsing in the blob adapter (`finalize_upload`).
   - Fix Job enum types (`JobType` and `resource_type` enums matching the OpenAPI / Pydantic models).
   - Ensure idempotency replay and lease fencing logic match contract requirements.
3. **Integration Gate Check (Gate G1)**:
   Run all foundation tests:
   ```bash
   uv run pytest tests/foundation/
   ```
   All tests must pass cleanly.
4. **Task Ledger & Status Update**:
   Update `status` of `T01` in [plan/tasks.json](../../plan/tasks.json) from `"planned"` to `"integrated"`.
5. **Handoff**:
   Format the final summary according to the required `AGENTS.md` handoff template.

---

## Completion Criteria (Do Not Stop Until Satisfied)
- `uv run pytest tests/foundation/` exits 0 with 0 failures.
- No dummy business records seeded.
- `plan/tasks.json` marks `T01` as `"integrated"`.
