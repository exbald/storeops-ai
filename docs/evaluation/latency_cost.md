# Latency & Operational Cost Model (T12 / AC28)

This document outlines the performance profiles, queue delay expectations, token consumption models, and operational cost projections for StoreOps automated investigations and verifications per `specs/06-quality.md`.

---

## 1. Quality & Performance Gate Targets

The release criteria established in `specs/06-quality.md` replace earlier unverified PRD targets with realistic operational boundaries:

| Pipeline Stage | Target p50 Latency | Target p95 Latency | Max Allowable Timeout | Target Cost / Invocation |
|---|---|---|---|---|
| **Investigation Loop** | ≤ 25 s | ≤ 60 s | 120 s | ≤ USD $0.35 |
| **Verification Loop** | ≤ 18 s | ≤ 45 s | 90 s | ≤ USD $0.15 |
| **Combined Full Cycle** | ≤ 43 s | ≤ 105 s | 210 s | **≤ USD $0.50** |
| **Async Queue Delay** | ≤ 2.0 s | ≤ 5.0 s | 15.0 s | N/A (Cloud Tasks / Outbox) |

---

## 2. Model Configuration & Prompt Versioning

StoreOps enforces pinned model and prompt configurations to ensure reproducible diagnostic inference:

### Investigation Pipeline
* **Model ID**: `gemini-2.5-flash`
* **Temperature**: `0.2` (low temperature to minimize hallucination of inventory numbers)
* **Max Output Tokens**: `2048`
* **Input Token Profile**:
  * System prompt & schema: ~1,100 tokens
  * 14-day sales window & inventory facts: ~800 tokens
  * Vendor promotion & planogram rules: ~600 tokens
  * Store visit notes & visual evidence tags: ~500 tokens
  * **Total Prompt Tokens**: ~3,000 tokens
* **Output Token Profile**:
  * Diagnostic JSON schema response: ~350 - 550 tokens
* **Estimated Cost per Investigation**:
  * Input: 3,000 tokens * $0.075 / 1M = $0.000225
  * Output: 500 tokens * $0.30 / 1M = $0.000150
  * Visual token equivalent (1 image): ~258 tokens * $0.075 / 1M = $0.000019
  * **Direct Gemini Cost**: **~$0.0004** (well within $0.35 cap)

### Verification Pipeline
* **Model ID**: `gemini-2.5-flash`
* **Temperature**: `0.1` (deterministic visual verification)
* **Max Output Tokens**: `1024`
* **Input Token Profile**:
  * System prompt & schema: ~950 tokens
  * High-resolution shelf after-image: ~516 tokens (standard visual crop)
  * Planogram constraints: ~400 tokens
  * **Total Prompt Tokens**: ~1,866 tokens
* **Output Token Profile**:
  * Verification JSON schema response: ~200 - 350 tokens
* **Estimated Cost per Verification**:
  * **Direct Gemini Cost**: **~$0.0003** (well within $0.15 cap)

> [!NOTE]
> **Analytical Model vs Empirical Telemetry**: The cost and token projections above represent architectural pricing models calculated using official Gemini rate cards ($0.075 / 1M prompt tokens, $0.30 / 1M candidate tokens) and prompt sizing. They are theoretical models, not live billing measurements. Per `AGENTS.md`, live model evaluation gates (G3/G5/G6) remain explicitly `[BLOCKED]` pending cloud credentials and are not claimed as empirically passed.

---

## 3. Operational Reliability & Resilience

### Failures & Abstentions
1. **Excluded from Timing**: Failed requests (e.g. 429 quota exhaustion or network dropouts) are tracked separately and do not mask failure rates by skewing timing averages.
2. **Exponential Backoff**: Transient provider errors trigger up to 3 retries with jittered exponential backoff before the job is marked `FAILED` with non-retryable reason.
3. **Fail-Closed Verification**: Any ambiguity in image clarity, occlusion, or missing evidence defaults to `outcome: UNKNOWN` or `outcome: FAIL`, preventing unverified resolution of noncompliant shelf states.

