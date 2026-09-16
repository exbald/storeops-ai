# Wire contract semantics

The OpenAPI file defines exact shapes. This file adds cross-field rules that ordinary
JSON Schema cannot fully express. All request objects reject unknown fields.

## Scope, lists and versions

All protected endpoints except /me require X-Workspace-Id. This is only a requested
context: verify membership before using it and verify every resource belongs to it.
GET /me returns selectable memberships. Role ADMIN includes REP capabilities. For
foreign object IDs return 404 after checking membership; missing membership/role is 403.
Existing-resource commands require expected_version, returning 409 on conflict. For
updateAction this is the parent investigation version, incremented atomically with the
action update. Initial creation uses server-generated IDs and version=1.

Lists use opaque cursors, limit 1–100, stable order created_at descending then id, and
nullable next_cursor. Unless active is supplied, catalog lists include both states so
management can discover archived records; the rep's active-store query sends active=true.
Sorting by opportunity happens after fetching health for the visible store set; the MVP
may paginate that view rather than issue an unbounded fleet-wide model run.

## Media binding

PRODUCT_REFERENCE requires product_id; AGREEMENT and IMPORT have no store/visit/product
binding; VISIT_BEFORE/AFTER require matching store_id and visit_id plus zone_id,
zone_kind and captured_at. Inapplicable fields must be null. Reference/agreement/import
creation and completion require ADMIN; reps may upload only visit media. Mime/kind
compatibility is checked before and after upload. Finalizing visit media appends its ID
once to the appropriate visit array in the same transaction; product reference IDs are
attached explicitly through updateProduct after readiness validation.

Media outside the normalized image catalog is not sent as a user-provided external URL.
The server resolves bytes from an authorized media ID. download_url is computed at read
time, not persisted as the canonical evidence locator.

## Policy predicates

MIN_FACINGS: SHELF zone, min_facings >0; product_id may be null for the brand total or a
catalog ID for one product. REQUIRED_PRODUCT: SHELF, non-null product_id, null min_facings.
REQUIRED_DISPLAY: DISPLAY, null product_id and min_facings. DOCUMENT source requires
media_id, page and nonempty quote from the promotion's ready agreement, with reviewer_note
optional. MANUAL source requires reviewer_note and null document fields. Rule IDs are
unique within a version, and store/product/zone references are validated. dates require
starts_on ≤ ends_on. Case size changes affect future stock imports, never old normalized rows.

Extracted rules with unresolved fields remain extraction gaps, not invalid Rule DTOs.
The service assigns UUID rule IDs to complete proposals and maps AI claim_keys to durable
claim IDs after validation. The browser may generate UUIDs for manually added rules;
the service checks uniqueness and ownership. The model does not select the approved
catalog, approve a rule or assign a workspace.

## Investigation and result handling

At most one nonterminal investigation exists per visit. Starting another requires
dismissing the old case (PROPOSED, ACCEPTED, NEEDS_WORK or INCOMPLETE). Reject a new start
while a job is QUEUED, INVESTIGATING or VERIFYING. A fully supported NO_ISSUE with zero
actions closes the visit as NO_ACTION and creates a NO_ACTION report, without a claim of
verified corrective work. Define material decline as sales_delta ≤−0.10 by default;
make the threshold an explicit versioned setting. NO_ISSUE also requires complete
commercial coverage, fresh stock and all visible policy checks satisfied.

Missing display media remains UNKNOWN even if the before shelf is clear. Required-product
presence needs at least one unambiguous front detection; face counts need distinct accepted
boxes in the correct zone. Deduplicate exact/near-identical detections using same-product
IoU ≥0.85; preserve the raw output. An overlap/identity that cannot be safely deduplicated
is unknown, not an arbitrary count. Box area must be positive. The deterministic evaluator
checks model-proposed rule results before computing the aggregate.

Evidence support is SUPPORTED only if approved policy, complete commercial windows,
fresh relevant location stock and usable required image zones agree without unresolved
contradiction. Otherwise it is LIMITED. This is a completeness label, not a probability.
Freshness defaults: backroom ≤4h, distributor ≤24h; before photos captured during the visit
and ≤30m at investigation start. All checks use server Clock and stored source times.

Verification creates the resource first with result=null and empty checks while queued.
That placeholder becomes immutable after the terminal attempt. A completed verification
requires exactly all frozen rule IDs. Every terminal semantic outcome gets a report;
technical failures expose job.error and never invent checks. Only PASS closes the visit.

## Retry commands

retryJob is allowed for FAILED INVESTIGATE or POLICY_EXTRACT jobs only. It creates a new job for the same resource,
preserving earlier evidence/events; investigation uses its frozen input snapshot and
requires the policy still be valid. No terminal job changes status in place.

For a failed import, create a new import with the ready file and a new idempotency key;
if its batch actually committed, reconciliation returns the existing committed result.
For a failed verification, call verifyInvestigation again to create a new attempt.
Other retryJob types return 409 RETRY_WITH_RESOURCE_COMMAND. Temporary worker retries
inside the same active job are different from this explicit user retry command.

The API carries UUIDs and nullable fields exactly as declared; decimal metrics remain
strings. Do not derive action success from a checkbox or treat a Job SUCCEEDED status as
proof that its import/verification business outcome passed.
