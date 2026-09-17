# StoreOps Test Execution & Regression Hardening Report (Task T10)

**Date**: 2026-09-17  
**Wave**: Wave 5  
**Task ID**: `T10` — *Integrate every slice and harden regressions*  
**Integration Gate**: `G2–G5 local: full empty-state workflow passes without mocks at service boundaries; model test double clearly identified.`  

---

## 1. Executive Summary

Task T10 integrates every previously delivered vertical slice across Waves 1 through 4 (T01 through T09, T11) into a single, cohesive, hardened regression and contract conformance test suite.

All backend tests execute deterministically without external network access, adhering strictly to the Ports & Adapters architectural pattern (`specs/01-architecture.md`). Application runtime code under `apps/api/` has been verified to import **zero** test fixtures, demo seeds, or evaluation labels (`test_ac26_runtime_modules_import_no_fixtures_or_demo_seeds`).

---

## 2. Test Execution Overview

| Suite | Category | Files | Tests | Pass | Fail | Execution Time |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Backend Contract** | OpenAPI / Schema Conformance | `tests/contract/test_ac25_contract_conformance.py` | 6 | 6 | 0 | ~0.15s |
| **Backend Integration** | Multi-Slice Integration & Hardening | `tests/integration/test_*.py` (5 files) | 19 | 19 | 0 | ~0.55s |
| **Backend E2E** | Full-Flow Acceptance | `tests/e2e/test_*.py` (2 files) | 4 | 4 | 0 | ~0.25s |
| **Backend Unit / Slice** | Domain, Catalog, Imports, Policies, Visits, Verifier | `tests/{catalog,imports,policies,visits,verification,unit}/` | 161 | 161 | 0 | ~1.40s |
| **Frontend Web** | Contract Conformance, Client Doubles, Wire Format, UI | `apps/web/test/*.test.ts` (3 files) | 35 | 35 | 0 | ~1.18s |
| **Total** | **All Test Suites** | **15+ test modules** | **225** | **225** | **0** | **< 4.0s** |

- **Python Tests**: 190 passed, 0 failed (`uv run pytest`)
- **Frontend Tests**: 35 passed, 0 failed (`pnpm --filter web test`)
- **Spec Verification**: 0 drift (`make verify-spec`)

---

## 3. Acceptance Criteria Traceability Matrix (AC02 – AC35)

| Acceptance ID | Description | Test Module | Verification Method |
| :--- | :--- | :--- | :--- |
| **AC02** | Tenant isolation across workspaces | `tests/integration/test_ac02_ac04_ac05_security_catalog.py` | Cross-workspace store/product/visit read isolation |
| **AC04** | Role authorization (REP vs ADMIN) | `tests/integration/test_ac02_ac04_ac05_security_catalog.py` | Unauthorized role mutations rejected with 403 `FORBIDDEN` |
| **AC05** | Media upload flow & hash verification | `tests/integration/test_ac02_ac04_ac05_security_catalog.py` | Init -> PUT upload -> complete with sha256 mismatch rejection |
| **AC06** | Import validation and staged state | `tests/integration/test_ac06_ac07_ac08_imports_regression.py` | Uncommitted import stages facts without writing to DuckDB |
| **AC07** | Invalid SKU rejection in CSV import | `tests/integration/test_ac06_ac07_ac08_imports_regression.py` | Unknown SKU fails import with 0 facts committed |
| **AC08** | Idempotent commit retry | `tests/integration/test_ac06_ac07_ac08_imports_regression.py` | Exact commit replay returns 202 without row duplication |
| **AC10** | Policy version concurrency (OCC) | `tests/integration/test_ac10_ac34_ac35_policy_lifecycle.py` | Concurrent approval on same version returns 409 `VERSION_CONFLICT` |
| **AC12** | Multi-turn investigation synthesis | `tests/integration/test_ac12_ac15_ac16_investigation_workflow.py` | Investigation limits to <= 3 actions, grounded hypotheses & claims |
| **AC13** | Action grounding & evidence locators | `tests/visits/test_ac13_actions.py` | Proposed actions explicitly cite grounded evidence IDs |
| **AC14** | Single active investigation invariant | `tests/visits/test_ac14_dismissal.py` | At most one active investigation per visit; conflicts return 409 |
| **AC15** | Idempotent plan acceptance & dismissal | `tests/integration/test_ac12_ac15_ac16_investigation_workflow.py` | Repeated plan accept returns 200 without side effects |
| **AC16** | Rep action completion vs verified | `tests/integration/test_ac12_ac15_ac16_investigation_workflow.py` | Rep can claim `CLAIMED_DONE`; direct `VERIFIED` returns 422 |
| **AC17** | Compliant verification & atomic closure | `tests/integration/test_ac17_ac18_ac19_ac20_verification_resilience.py` | PASS outcome marks actions `VERIFIED`, visit `CLOSED`, generates report |
| **AC18** | Stale policy rejection during verify | `tests/verification/test_ac18_superseded_policy.py` | Policy updated after investigation blocks verify with 409 `STALE_POLICY` |
| **AC19** | Ineligible media rejection | `tests/integration/test_ac17_ac18_ac19_ac20_verification_resilience.py` | Submitting `VISIT_BEFORE` media or reused hash returns 422 |
| **AC20** | Non-compliant / incomplete verification | `tests/verification/test_ac20_verification_failures.py` | Partial / failing checks yield explicit `FAIL` or `INCONCLUSIVE` |
| **AC21** | Job persistence, leasing & events | `tests/integration/test_ac21_ac22_ac33_jobs_and_failures.py` | Job leases fenced by generation, outbox pattern, event sequence streaming |
| **AC22** | Provider failure handling | `tests/integration/test_ac21_ac22_ac33_jobs_and_failures.py` | Quota exhaustion yields `status: FAILED`, never fake success |
| **AC23** | Empty workspace initial state | `tests/e2e/test_ac23_ac24_empty_and_complete.py` | Empty workspace returns clean empty collections without demo seeds |
| **AC24** | Full end-to-end user lifecycle | `tests/e2e/test_ac23_ac24_empty_and_complete.py` | Full flow: store setup -> import -> investigation -> action -> verify -> report |
| **AC25** | OpenAPI contract conformance | `tests/contract/test_ac25_contract_conformance.py` | OpenAPI spec validation, Pydantic model conformance, error format |
| **AC26** | Profile hardening & anti-fabrication | `tests/integration/test_ac26_ac32_hardening.py` | Cloud mode refuses stub/in_memory; runtime imports 0 test fixtures |
| **AC32** | Prompt injection hardening | `tests/integration/test_ac26_ac32_hardening.py` | Malicious prompt injection stored strictly as untrusted data |
| **AC33** | Concurrent idempotency keys | `tests/integration/test_ac21_ac22_ac33_jobs_and_failures.py` | Conflicting payloads with identical Idempotency-Key return 409 |
| **AC34** | Policy draft edit isolation | `tests/integration/test_ac10_ac34_ac35_policy_lifecycle.py` | Approved policy versions are immutable; edits occur in new drafts |
| **AC35** | Catalog product reference constraint | `tests/integration/test_ac10_ac34_ac35_policy_lifecycle.py` | Policy rules referencing non-existent products rejected with 422 |

---

## 4. Model Test Double Identification

Per `specs/01-architecture.md` and `specs/06-quality.md`, all tests clearly identify whether they use test doubles or live model credentials:
- **`DeterministicModelGateway` / `ConfigurableModelGateway`**: In-memory test doubles implementing the `ModelGateway` protocol. Used exclusively in local unit, integration, and E2E test runs (`LOCAL` profile with `ai_mode="STUB"`). Generates predictable, schema-validated structured responses based on prompt inspection.
- **Live Gemini Gate**: Configured via `AI_MODE="LIVE"` and requires `GEMINI_API_KEY`. Cloud profiles (`PROFILE="CLOUD"`) enforce `AI_MODE="LIVE"` and fail fast at startup if configured with stub mode (`test_ac26_cloud_mode_refuses_stub_or_in_memory_configuration`).
