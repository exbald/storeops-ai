# Product requirements

## Outcome

A field operations team can load its own brand, stores, merchandising requirements and
commercial data, then investigate and resolve a store execution issue with inspectable
evidence. The MVP works with an empty database and with arbitrary supported store and
SKU identifiers. “Resolved” means required execution was verified, not sales recovered.

## Scope

One brand and one supported currency per workspace. Initial currencies are SGD, USD
and AUD, each with two decimal places. A workspace may contain many stores and products;
no rule fixes them to the demonstration's ten stores or four products. Cap the relevant
reference catalog at 25 active products per investigation by default, with a clear
validation error when exceeded. This limit is configurable and must be reevaluated
before expansion. Roles are ADMIN and REP; ADMIN also has all REP capabilities.

The cloud MVP uses Firebase identity, Next.js, Python/FastAPI, Google ADK, Gemini 3.8
Flash, Firestore, Cloud Storage, BigQuery and durable worker jobs. Initial inputs are
manual management, CSV files, PDFs and photos. No POS integrations, external messages,
orders, native mobile app, billing, public self-registration or arbitrary SQL tools.

## Required behavior

| ID | Requirement |
|---|---|
| R01 | Authorize every request by workspace membership and role. Bootstrap an empty workspace and first admin; do not create business fixtures. |
| R02 | Create, edit, list and archive stores, distributor locations and products; attach reference images. Preserve referenced history. |
| R03 | Upload and validate images/PDF/CSV assets, bind them to authorized entities and retrieve them through expiring URLs. |
| R04 | Validate sales/stock CSVs, show row-level errors, explicitly commit valid imports and retain correction history. |
| R05 | Create a promotion, extract proposed rules from an agreement, let an admin review/edit them and approve an immutable version. |
| R06 | Create a store visit with notes and dated shelf/display evidence. Persist visits independently of AI execution. |
| R07 | Investigate using current persisted records and return a grounded hypothesis, alternatives, gaps and up to three proposed actions. |
| R08 | Compute commercial metrics in code/SQL and bind claims to immutable source references and a captured data snapshot. |
| R09 | Require a rep to accept an action plan; record claimed completion without treating it as verified completion. |
| R10 | Evaluate new evidence per approved rule and close an issue only when every required rule passes. Unknown and partial results remain open. |
| R11 | Provide all management and rep workflows in a responsive UI, including loading, empty, invalid, stale, failure and retry states. |
| R12 | Persist jobs and progress, survive browser disconnects, bound retries, and prevent duplicate or stale writes. |
| R13 | Maintain deterministic regression tests, contract checks and a separate live model evaluation suite. |
| R14 | Reproduce an empty local installation and an authorized cloud deployment with logs, configuration, migrations and operating instructions. |
| R15 | Keep optional demo seeds and labeled evaluation data outside application logic; support independent data loading after the core build. |

## Minimum complete journey

An admin signs in, creates a store and its backroom/distributor mapping, adds products
and reference images, imports complete sales windows and stock snapshots, uploads an
agreement, reviews extracted rules and approves the promotion. A rep creates a visit,
uploads shelf and display photos, runs an investigation, reads the evidence, accepts
the proposed tasks, does the physical work and submits after photos. The system saves
each verification attempt and a readable report. Reloading any screen preserves state.

## Boundaries and missing information

Missing sales or stock permits a limited investigation, with null metrics and explicit
gaps. A store, open visit, at least one ready photo and an approved active policy are
required to start. A missing policy is a setup action, never an invented contract.
Sources that are unreadable, stale or outside a camera's coverage cannot prove absence.

The implementation may use a tiny representative fixture during development, but a
complete MVP must also pass acceptance with a new workspace and differently named data
entered through its normal interfaces. The application must never special-case Pulse,
S001, a particular PDF page, a fixed date or a canned diagnosis.
