# Quality and regression strategy

## Tests begin with the first slice

Use minimal factories and representative media while implementing. These are engineering
test inputs, independent of the optional competition seed. Tests must run against changing
store/SKU names, dates and IDs so a demo-specific implementation cannot pass by coincidence.

| Layer | Purpose | When |
|---|---|---|
| Spec checks | References, schema examples, task DAG, ownership and requirement traceability | Every spec edit |
| Unit | Decimal math, missing/zero distinctions, freshness, predicates, state transitions, permissions | Each relevant task |
| Contract | API requests/responses, generated client and domain-model schema conformance | Every task touching an interface |
| Adapter integration | Firestore transactions, blob finalization, import atomicity, BigQuery/local parity | Before integrating each backend slice |
| Browser | Empty setup, catalog/import/policy flow, investigate/accept/verify, reload recovery | Each completed vertical slice |
| Live model eval | Vision, policy extraction, evidence support, diagnosis and false resolution | Spike and before release |

Tests must assert behavior, not mirror implementation steps. Avoid snapshotting incidental
LLM wording. Assert allowed labels/actions, cited sources, required gaps, rule results and
absence of unsafe resolution. A missing credential may skip an explicitly optional local
test but blocks the corresponding required cloud/live release gate.

## Deterministic suite

Implement every case in plan/acceptance.json and keep its ID in the test name or marker.
Run with real local persistence adapters and an injected deterministic ModelGateway in
ordinary CI. Test doubles belong in tests/ and an explicit local-only provider module.
Production startup rejects AI_MODE=stub and emulator environment variables.

Include malformed imports, duplicate lines, corrections, empty coverage, archived refs,
stale versions, wrong-workspace IDs, role bypass, expired uploads, mismatched checksums,
missing camera zones, provider errors and job crash/replay. Concurrent verification must
produce one terminal report and one business transition, even when two deliveries occur.

## Live evaluation

Build 30 independent scenarios: 15 diagnostic, 9 verification and 6 robustness cases.
Freeze 20 held-out cases (10/6/4) after using 10 for development. Do not reuse the same
photo or cosmetic variant across splits. Store labels separately from agent-readable
inputs. Include execution, confirmed supply shortage, unexplained decline, healthy stores,
stale/missing evidence, partial fixes, lookalikes, injection text and provider failures.

Targets: ≥9/10 correct held-out diagnostic labels on each of three repeats; zero false
resolutions in noncompliant/ambiguous held-out verification cases across repeats; every
clearly compliant held-out case passes; all factual claims cite resolvable IDs and ≥95%
are supported on human review. Report numerator/denominator, abstentions and failures.
These small synthetic/staged samples do not establish general retail accuracy.

Compare Gemini 3.8 settings on development cases and evaluate the selected configuration
on the frozen set. Evaluate any 3.5 fallback separately. Include an image-only and a
deterministic sales/stock baseline. Never edit the holdout to erase failures. If a product
condition is removed from scope, record the scope change and keep the old result.

## Latency and operational evidence

Measure ≥30 live jobs: queue delay, warm/cold processing p50/p95, tokens and actual costs.
Initial targets are investigation processing p95 ≤60 s, verification ≤45 s and mean
inference cost ≤USD 0.50 per complete loop. These replace the earlier PRD's untested
tighter targets and are not achieved measurements or guaranteed queue-time SLAs.
Record failures separately; excluding them from timing cannot hide the failure rate.

## Release gates

G0 contracts validated and dependency versions pinned. G1 empty authenticated app persists
records. G2 imports and reviewed policies work through normal UI. G3 live investigation
uses persisted inputs. G4 accepted actions and new evidence close only compliant cases.
G5 deterministic and cloud adapter regressions pass. G6 live evaluations and deployment
are documented with any limits. T14 cannot claim completion until all six gates pass.

The optional demo seed has its own acceptance and is not a prerequisite for G1–G6.
Regression test factories already exist before it is added.
