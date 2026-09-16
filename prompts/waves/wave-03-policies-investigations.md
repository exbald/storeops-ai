# Goal: Execute Wave 3 (Policies and Investigations)

## Objective
Implement and integrate **Wave 3** tasks:
- **T04**: Reviewed, versioned policy workflow (depends on `T02`, `T06`)
- **T07**: Persisted visits, investigations, plans, and evidence (depends on `T02`, `T03`, `T06`)

---

## Tasks & Scope

### 1. T04 - Policy Management & Approval Workflow
- **Acceptance IDs**: `AC09`, `AC10`, `AC34`, `AC35`
- **Operation IDs**: `listPromotions`, `createPromotion`, `getPromotion`, `updatePromotion`, `extractPolicy`, `approvePolicy`, `listPolicyVersions`
- **Owned Paths**: `apps/api/modules/policies/`, `tests/policies/`
- **Key Rules & Semantics**:
  - Unapproved draft policies extracted from uploaded agreement documents cannot be used in investigations or verifications.
  - Mandatory admin approval creates an immutable, versioned policy snapshot.
  - Concurrent updates or modifications to older policy versions must fail with conflict (409) or precondition failed (412).
- **Gate G2 Backend**: Admin approval required; concurrent/stale policy writes fail safely.

### 2. T07 - Visits, Investigations & Action Plans
- **Acceptance IDs**: `AC11`, `AC12`, `AC13`, `AC15`, `AC16`
- **Operation IDs**: `createVisit`, `listVisits`, `getVisit`, `updateVisit`, `createInvestigation`, `listInvestigations`, `getInvestigation`, `acceptInvestigation`, `dismissInvestigation`, `updateAction`, `listEvidence`, `getEvidence`, `getReport`
- **Owned Paths**: `apps/api/modules/visits/`, `tests/visits/`
- **Key Rules & Semantics**:
  - Visit records capture associate inputs and audit metadata.
  - Investigation jobs leverage the T06 AI investigator agent to compare store photos, backroom inventory, sales metrics (from T03), and active approved policies (from T04).
  - Produces structured findings, root cause reasoning, and corrective actions (e.g. restock, re-facing).
  - Explicit `NO_ACTION` report when full compliance is verified.
- **Gate**: Persisted input changes alter new investigation outputs; zero dependency on fixed demo fixtures.

---

## Execution Steps
1. Verify Wave 2 dependencies (`T02`, `T03`, `T06`) are marked `"integrated"`.
2. Write test-first failing tests in `tests/policies/` and `tests/visits/`.
3. Implement `apps/api/modules/policies/` and `apps/api/modules/visits/`.
4. Run task test suites:
   ```bash
   uv run pytest tests/policies/
   uv run pytest tests/visits/
   ```
5. Update `status` of `T04` and `T07` in [plan/tasks.json](../../plan/tasks.json) to `"integrated"`.
6. Record handoff in [AGENTS.md](../../AGENTS.md) format.

---

## Completion Criteria (Do Not Stop Until Satisfied)
- `tests/policies/` and `tests/visits/` pass 100%.
- Draft policies cannot resolve verifications without admin approval.
- Concurrency/stale version guards verified.
- Tasks updated to `"integrated"` in `plan/tasks.json`.
