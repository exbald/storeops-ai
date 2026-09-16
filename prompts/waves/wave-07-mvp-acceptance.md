# Goal: Execute Wave 7 (Core MVP Acceptance & Handover)

## Objective
Implement task **T14**: *Accept the core MVP from an empty install*.
Conduct the final acceptance verification of the StoreOps application starting from a fresh empty database, and produce complete operator handover documentation.

---

## Task Details
- **Task ID**: `T14`
- **Owner Role**: `coordinator`
- **Prerequisites**: `T12` (Wave 6 integrated)
- **Acceptance IDs**: `AC01`, `AC24`, `AC26`, `AC31`
- **Owned Paths**:
  - `docs/release.md`
  - `docs/user-guide.md`
  - `docs/empty-install.md`
- **Mandatory References**:
  - [AGENTS.md](../../AGENTS.md)
  - [specs/00-product.md](../../specs/00-product.md)
  - [specs/06-quality.md](../../specs/06-quality.md)
  - [specs/07-delivery.md](../../specs/07-delivery.md)
  - [DECISIONS.md](../../DECISIONS.md)

---

## Verification Criteria
1. **Empty-State Lifecycle (AC31)**:
   - Deploy/run the application with an empty database.
   - Authorized user signs in and bootstraps a new workspace.
   - User creates stores, backrooms, and products via UI/API.
   - User imports sales/inventory CSVs and uploads a promotion agreement.
   - Admin approves the extracted policy.
   - Store associate records a visit with real photos, triggering an investigation.
   - User reviews the AI investigation findings and accepts corrective action tasks.
   - Store associate uploads a resolution photo; the verifier agent evaluates and marks it compliant.
   - Final audit report is generated and persisted.
   - **Crucial**: No sample business records were pre-seeded; all records originated from normal user flows.
2. **Release Documentation**:
   - `docs/empty-install.md`: Step-by-step instructions to run the application locally or in cloud.
   - `docs/user-guide.md`: End-user operational runbook for retail managers and field associates.
   - `docs/release.md`: Formal verification ledger listing all 15 tasks (`T00`–`T14`), 41 acceptance cases (`AC01`–`AC41`), test results, and evaluation summaries.

---

## Execution Steps
1. Perform clean installation check:
   - Wipe local database / state directories.
   - Run startup scripts and verify application starts in a clean empty state.
2. Run the full verification suite:
   ```bash
   python3 tools/verify_spec.py
   uv run pytest
   ```
3. Document deployment instructions, verification runs, and operational guidelines in `docs/`.
4. Update `status` of `T14` in [plan/tasks.json](../../plan/tasks.json) to `"integrated"`, and set overall plan status to `"completed"`.
5. Submit final coordinator handoff.

---

## Completion Criteria (Do Not Stop Until Satisfied)
- Complete MVP operational from zero data.
- All 15 tasks in `plan/tasks.json` marked `"integrated"`.
- Documentation in `docs/` complete and accurate.
