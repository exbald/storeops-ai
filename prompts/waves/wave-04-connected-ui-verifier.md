# Goal: Execute Wave 4 (Connected UI and Verification Backend)

## Objective
Implement and integrate **Wave 4** tasks:
- **T08**: Connect the complete browser workflow (depends on `T04`, `T05`, `T07`)
- **T09**: Execution verifier and atomic resolution (depends on `T04`, `T06`, `T07`)

---

## Tasks & Scope

### 1. T08 - Connected Browser Workflow & E2E
- **Acceptance IDs**: `AC40`
- **Owned Paths**: `apps/web/`, `tests/e2e/`
- **Deliverables**:
  - Full end-to-end user journey connected to live API backend.
  - Store associates can upload visit evidence, trigger investigations, view AI reasoning, accept action items, and upload re-verification photos.
  - Resilient polling and reload recovery (refreshing browser does not duplicate jobs or drop uncommitted state).
  - Mobile-responsive UI adhering to [specs/04-ui.md](../../specs/04-ui.md).
- **Gate**: UI consumes actual services rather than test mocks; verified with minimal test factories without demo seeds.

### 2. T09 - Verifier Agent & Atomic Resolution
- **Acceptance IDs**: `AC17`, `AC18`, `AC19`, `AC20`, `AC32`, `AC33`, `AC34`
- **Operation IDs**: `verifyInvestigation`, `listVerifications`, `getVerification`
- **Owned Paths**: `apps/api/ai/verifier/`, `apps/api/modules/verification/`, `tests/verification/`
- **Deliverables**:
  - Specialized second AI agent ("Verifier") inspecting newly uploaded resolution photos against the original violation and frozen policy rules.
  - Deterministic per-rule verdict: `COMPLIANT`, `NON_COMPLIANT`, `INCONCLUSIVE`.
  - Exactly-once business state transitions: a compliant photo resolves the action item once; stale or previously uploaded photos are rejected.
  - Immutable verification history and audit report generation.
- **Gate G4 Backend**: Compliant photos close action once; partial, blurry, or duplicate evidence never falsely resolves.

---

## Execution Steps
1. Verify Wave 3 dependencies (`T04`, `T07`) are integrated.
2. Implement T09 verification module and test suite in `tests/verification/`.
3. Implement T08 frontend routes and Playwright / RTL e2e test suite in `tests/e2e/`.
4. Run tests:
   ```bash
   uv run pytest tests/verification/
   pnpm --filter web test:e2e # or specified web test command
   ```
5. Update `status` of `T08` and `T09` in [plan/tasks.json](../../plan/tasks.json) to `"integrated"`.
6. Submit handoff per [AGENTS.md](../../AGENTS.md).

---

## Completion Criteria (Do Not Stop Until Satisfied)
- `tests/verification/` passes 100%.
- E2E browser test flow passes against actual backend services.
- Exactly-once resolution verified (cannot re-resolve or false-pass).
- Tasks marked `"integrated"` in `plan/tasks.json`.
