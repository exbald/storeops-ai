# Live Model Evaluation & Benchmark Report (T12 / AC28)

This document records the evaluation methodology, dataset splits, baseline metrics, and live gate status for multimodal diagnostics and visual verification per `specs/06-quality.md`.

---

## 1. Dataset Provenance & Frozen Splits

The evaluation dataset comprises **30 independent, unshared scenarios** structured into development and frozen holdout sets:
* **Development Split (10 cases)**: Used for prompt engineering and setting baseline thresholds.
* **Frozen Holdout Split (20 cases)**: Held out and never edited to erase failures.

### Categorical Distribution
| Scenario Category | Total Cases | Development Split | Frozen Holdout Split |
|---|---|---|---|
| **Diagnostic (D01 - D15)** | 15 | 5 (D01-D05) | 10 (D06-D15) |
| **Verification (V01 - V09)** | 9 | 3 (V01-V03) | 6 (V04-V09) |
| **Robustness (R01 - R06)** | 6 | 2 (R01-R02) | 4 (R03-R06) |
| **Total** | **30** | **10** | **20** |

### Data Security & Label Isolation
* Unlabeled scenario inputs are stored in `evals/data/scenarios/*.json`. These contain only operational telemetry, planogram constraints, and simulated visual observations.
* Ground truth labels are stored separately in `evals/labels/ground_truth.json` and are forbidden from import into application code, migrations, or agent-visible context.

---

## 2. Baseline Model Performance

To ensure objective benchmarks against Gemini multimodal inference, two deterministic baselines were established:

### Baseline Comparison Summary
| Metric | Deterministic Sales/Stock Baseline | Image-Only Baseline | Gemini Target (G6 Gate) |
|---|---|---|---|
| **Diagnostic Accuracy (Holdout)** | 90.0% (9/10) | 30.0% (3/10) | ≥ 90.0% (≥ 9/10 on 3 repeats) |
| **Verification False Resolutions** | 0 (0/6 noncompliant passed) | 1 (1/6 false pass on occluded item) | 0 across all 3 repeats |
| **Compliant Verification Recall** | 100% (2/2 compliant passed) | 100% (2/2 compliant passed) | 100% compliant passed |
| **Factual Claim Grounding** | 100% cited valid IDs | N/A (no entity citations) | ≥ 95% claims supported & cited |
| **Mean Evaluation Runtime** | < 0.01 s / scenario | < 0.01 s / scenario | p95 ≤ 60 s / investigation |

### Key Baseline Takeaways
1. **Deterministic Heuristic Baseline**: Excels when sales numbers and backroom inventory are fully populated, but cannot verify physical shelf condition or detect subtle visual compliance breaches.
2. **Image-Only Baseline**: Vulnerable to false resolutions when shelves appear visually full of lookalike products or when backroom stock is unobservable.
3. **Multimodal Fusion Need**: Confirms the architectural design requiring Gemini to fuse numerical inventory/sales data with visual shelf evidence.

---

## 3. Live Model Gate G6 Status

Per `AGENTS.md` and `specs/06-quality.md`:
> *"A stubbed provider cannot satisfy a live gate. Missing credentials produce a blocked live gate, not a successful test. Never silently skip a mandatory check or mark an unimplemented task done."*

### Current Gate G6 Status: `[BLOCKED]`
* **Command Executed**: `make eval-live` (`uv run python3 evals/run_evals.py --mode live`)
* **Live API Credential Status**: No valid Google Gemini API key is configured in the execution environment (returns `400 INVALID_ARGUMENT: API key not valid`).
* **Harness Behavior**: Evaluator detects invalid credentials immediately, outputs `[BLOCKED] Missing or invalid Google Gemini credentials for live evaluation gate G6`, and exits with code 2.
* **Integrity Guarantee**: No mocked success or silent pass was emitted. Unit tests, adapter parity tests, and baseline evaluations pass deterministically, while the live model evaluation gate remains explicitly blocked pending valid credentials.
