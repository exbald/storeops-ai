# Goal: Execute Wave 6 (Cloud Parity, Live Evaluations & Optional Demo Seed)

## Objective
Execute **Wave 6** tasks:
- **T12**: Run cloud parity and live model acceptance (depends on `T10`, `T11`)
- **T13** *(Optional)*: Independent demo seed and replay suite (depends on `T10`)

---

## Tasks & Scope

### 1. T12 - Cloud Parity & Live Gemini Acceptance
- **Acceptance IDs**: `AC27`, `AC28`, `AC29`
- **Owned Paths**: `evals/`, `tests/cloud/`, `docs/evaluation/`
- **Deliverables**:
  - Parity check between local DuckDB and cloud BigQuery metric calculations.
  - Live Gemini evaluation runs on labeled benchmark datasets (investigation accuracy, visual compliance scoring, false-positive resistance).
  - Recorded model metrics: latency, token usage, cost per investigation, schema validation error rate.
- **Gate G3/G5/G6 Live**:
  - Live model gates pass against real Gemini API endpoints.
  - *Note on Credentials*: If external Google Cloud or Gemini API credentials are not provided in the environment, report the exact blocked checks in `docs/evaluation/` rather than faking success.

### 2. T13 (Optional) - Demo Dataset & Seed Utility
- **Acceptance IDs**: `AC30`
- **Owned Paths**: `fixtures/demo/`, `scripts/seed_demo/`, `tests/demo/`
- **Deliverables**:
  - Realistic multi-store retail dataset (stores, planograms, promotion PDF, transaction CSVs, visit photos).
  - Standalone seeding script `python3 scripts/seed_demo/seed.py` that populates a workspace using normal public HTTP API endpoints.
  - Demonstration replay test suite in `tests/demo/`.
- **Gate**: The core application and all non-demo test suites must run and pass completely when `fixtures/demo/` is absent.

---

## Execution Steps
1. Verify `T10` and `T11` are integrated.
2. Run BigQuery parity tests and live evaluation benchmarks:
   ```bash
   uv run pytest tests/cloud/
   python3 evals/run_evals.py
   ```
3. If implementing optional T13, create demo fixtures and seed script, and verify application independence:
   ```bash
   uv run pytest tests/demo/
   ```
4. Record evaluation results in `docs/evaluation/report.md`.
5. Update `status` of `T12` (and `T13` if built) in [plan/tasks.json](../../plan/tasks.json) to `"integrated"`.
6. Submit handoff per [AGENTS.md](../../AGENTS.md).

---

## Completion Criteria (Do Not Stop Until Satisfied)
- Live model evaluation report generated.
- Cloud adapter checks completed (or specific credential blockers documented without falsifying passes).
- Demo seed is strictly decoupled from the core application.
- Tasks marked `"integrated"` in `plan/tasks.json`.
