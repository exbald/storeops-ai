# Goal: Execute Wave 5 (Hardened Regressions & Concurrency)

## Objective
Implement task **T10**: *Integrate every slice and harden regressions*.
Harden the entire combined-branch system against concurrency races, failure restarts, idempotency replays, and network retries across the full empty-state lifecycle.

---

## Task Details
- **Task ID**: `T10`
- **Owner Role**: `coordinator`
- **Prerequisites**: `T08`, `T09` (Wave 4 integrated)
- **Acceptance IDs**: `AC02`, `AC04`–`AC08`, `AC10`, `AC12`–`AC26`, `AC32`–`AC35`
- **Owned Paths**:
  - `tests/integration/`
  - `tests/contract/`
  - `tests/e2e/`
  - `.github/workflows/`
  - `docs/test-results.md`
- **Mandatory References**:
  - [AGENTS.md](../../AGENTS.md)
  - [specs/06-quality.md](../../specs/06-quality.md)
  - [specs/03-workflows.md](../../specs/03-workflows.md)
  - [contracts/SEMANTICS.md](../../contracts/SEMANTICS.md)

---

## Deliverables
1. **Full Integration Regression Suite**:
   End-to-end tests without service mocks (using local Firestore emulator and local blob storage) verifying empty workspace creation, product setup, CSV ingestion, agreement upload & approval, store visit, AI investigation, action acceptance, and re-verification.
2. **Failure & Concurrency Testing**:
   - Outbox recovery and worker crash/restart scenarios.
   - Concurrent policy approvals and lease token expirations.
   - Idempotency key replay consistency across all mutation endpoints.
3. **Contract Conformance & Drift Detection**:
   Automated check verifying TypeScript and Python client models match `contracts/openapi.json`.
4. **Clean Decoupling**:
   Verify zero dependence on demo seeds, fixtures, or evaluation labels in the main application bundle.

---

## Execution Steps
1. Run OpenAPI conformance and spec verification:
   ```bash
   python3 tools/verify_spec.py
   ```
2. Write integration tests in `tests/integration/` and `tests/contract/`.
3. Execute the full combined test suite:
   ```bash
   uv run pytest tests/
   ```
4. Verify CI workflow configuration in `.github/workflows/`.
5. Update `docs/test-results.md` with exact results and timings.
6. Update `status` of `T10` in [plan/tasks.json](../../plan/tasks.json) to `"integrated"`.
7. Submit handoff per [AGENTS.md](../../AGENTS.md).

---

## Completion Criteria (Do Not Stop Until Satisfied)
- `tests/integration/` and `tests/contract/` pass 100%.
- Full lifecycle executes from an empty state without seed data.
- Task marked `"integrated"` in `plan/tasks.json`.
