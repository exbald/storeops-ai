# Workflow semantics and concurrency

The allowed states are also encoded in contracts/states.json. Business state and Job
state are different: a successfully executed validation job can produce an INVALID
import, and a successfully executed verification job can produce FAIL or INCONCLUSIVE.

## Setup and catalog

Bootstrap creates a workspace and an ADMIN membership for an existing Firebase uid.
It creates no store, product, location, visit or policy. An admin creates stores and
products through the normal API/UI. Creating a store creates its empty backroom location
in the same transaction. Distributor locations are separate records shared by stores.
Assigning a distributor does not duplicate its stock across stores.

## Media

1. Create media metadata and a bounded upload URL. Bind kind and subject IDs before upload.
2. Upload bytes. The upload alone does not make an asset available to agents.
3. Complete the upload. Inspect actual bytes, checksum, MIME, dimensions and limits;
   normalize image orientation and remove EXIF. Retain original and normalized hashes.
4. Mark READY or REJECTED. Only READY media may be consumed. Download URLs expire in
   ten minutes; do not store them as evidence identifiers.

Limits: images JPEG/PNG ≤5 MB and normalized long edge ≤2,048 px; PDFs ≤10 MB/10 pages;
CSV ≤10 MB/50,000 rows. CSV is UTF-8 with the exact header contract. Reject path traversal,
incorrect type and wrong-workspace references. Spreadsheet cells beginning with formula
characters remain data; exported error CSVs must escape formula injection.

## Import

POST /imports validates a READY CSV and creates an Import plus a validation Job. Report
row numbers, field, code and message. Any invalid row makes the import INVALID, with
zero facts committed. A VALIDATED import requires an explicit commit command carrying
its version. Commit verifies catalog versions/references again; a changed dependency
returns a validation conflict rather than silently accepting stale mappings.

CSV identifiers are user-facing store_code, sku and location_code; resolve them within
the caller's workspace. Unknown references are errors, not implicit entity creation.
An identical committed file hash and import kind returns the existing result. A different
file can correct keyed rows without double counting. Before declaring a commit failed, reconcile its BigQuery batch. If the commit outcome is unknown, retain COMMITTING with a failed job and let reconciliation resolve it; do not mark a known committed batch FAILED. Committed imports cannot be edited
or deleted in the MVP; corrections are new imports.

## Policy

Create a DRAFT promotion with dates/store scope and upload its agreement. Extraction
produces proposed rules with page/quote citations and gaps. It cannot approve or publish
rules. An admin reviews every rule, edits ambiguous fields and approves an immutable
policy version. Manual rules are allowed but explicitly use source.kind=MANUAL with a
reviewer note; they must never display a fabricated PDF citation. Support only MIN_FACINGS,
REQUIRED_PRODUCT and REQUIRED_DISPLAY. Every active policy contains at least one rule.

Approval with an outdated expected_version returns 409. Edits create a new draft and
retain the previous approved version until the replacement is approved. Approval of a
replacement marks open cases based on the old policy as stale. Accept/verify then returns
409 STALE_POLICY and requires a new investigation. Past resolved reports stay historical.
An archived policy cannot start or close new work.

## Visit and investigation

Create an OPEN visit, add notes and before images. Start an investigation only when the
store is active, the visit belongs to it, the chosen policy is approved/active and at
least one appropriate image is READY. Capture the data snapshot before the first tool
call. Empty or stale commercial data produces gaps and null metrics; it is not grounds
for fabricating availability. The worker persists events at each real stage.

A valid response becomes PROPOSED. An entirely supported NO_ISSUE diagnosis with no
tasks becomes NO_ACTION, which closes the visit with a NO_ACTION report and is distinct from execution verified. Invalid model output
or infrastructure exhaustion becomes INCOMPLETE with usable evidence retained. Retry
creates a new linked job/attempt and never edits historical output in place. The allowed explicit retry commands are defined in contracts/SEMANTICS.md.

The rep accepts the complete proposal revision or dismisses it with a reason. Acceptance
creates stable actions exactly once and sets ACCEPTED. Rep checkboxes set CLAIMED_DONE;
they never resolve the case. A stale proposal version cannot be accepted or verified.

## Verification

Verify only ACCEPTED or NEEDS_WORK cases, using the same approved policy/plan version.
The rep must provide new media bound to the visit and correct zones. Reject reused
before-image normalized hashes; captures must be within the visit, no older than 30
minutes, and no more than five minutes in the future relative to the server Clock.
These checks limit simple replay but do not prove physical authenticity.

Require exactly one check for every frozen rule, with no additional/duplicate rule IDs.
Missing coverage, occlusion or uncertain SKU identity yields UNKNOWN. A clear observed
violation yields FAIL. Code derives the aggregate in this order:

1. Any UNKNOWN → INCONCLUSIVE.
2. All PASS → PASS.
3. All FAIL → FAIL.
4. Otherwise → PARTIAL.

Only PASS atomically sets all covered actions VERIFIED, investigation RESOLVED and visit
CLOSED and writes the report. All other outcomes set NEEDS_WORK and retain the OPEN
visit. Each attempt is immutable. No manual override is presented as an automatic pass.

## Jobs and idempotency

Every mutating POST requires Idempotency-Key. Scope it to uid/method/route, retain for
24 hours, and bind it to a canonical request-body hash. Same key/body replays the original
resource or response; same key/different body returns 409. This is separate from entity
versions and import hash deduplication.

Create job, resource transition and outbox entry in one Firestore transaction. Dispatch
best effort immediately, and drain the outbox once per minute to repair failures. Use
job_id as the Cloud Task identity. Workers claim a lease with a fencing generation;
duplicate active claims do no work. Every state write checks that generation. Lease
expiry is 60 seconds with a heartbeat every 20 seconds. Terminal duplicates acknowledge
without repeating writes. A live lease duplicate returns retryable status to the queue.

Persist stage checkpoints before acknowledging completion. Do not promise exactly-once
model calls or distributed transactions: a crash may repeat inference. Deduplicate final
business effects, record actual call costs and resume from validated checkpoints. Allow
three dispatch attempts, one structured-output repair per stage and a 180-second total
processing deadline. Enforce maximum 8 model calls and 20 tool calls per investigation;
verification maximum 4 model calls. Budget exhaustion returns INCOMPLETE, never PASS.

Queue delay is separately reported and may exceed the processing target. Transient
provider errors retry with bounded jitter; authorization/schema/input errors do not.
No cancellation endpoint is required for the MVP. Job status remains available after
browser navigation, refresh or disconnection.
