# Repository and delivery contract

## Repository layout to implement

| Directory | Contents |
|---|---|
| apps/api/core and apps/api/ports | Configuration, auth, errors, jobs, scope, versioning and interfaces |
| apps/api/modules/catalog | Stores, locations, products and media-facing services |
| apps/api/modules/imports | CSV validation, staging, commit and analytics adapters |
| apps/api/modules/policies | Drafts, reviewed rules and versioned approval |
| apps/api/modules/visits | Visit, investigation, action and report services |
| apps/api/ai | ModelGateway, ADK agents, prompts, tool wrappers and schema conversion |
| apps/web | Next.js routes, Firebase sign-in and generated API client consumers |
| packages/contracts | Generated language types; sourced from root contracts/ |
| migrations and infra | Versioned schemas/indexes, deployment configuration and service accounts |
| tests/unit, contract, integration, e2e | Deterministic regression layers |
| evals | Unlabeled model inputs, separately protected labels and live evaluation runner |
| fixtures/demo | Optional demo data/seed manifest; never imported by runtime code |

## Command interface to implement in T00 and T01

These are required command contracts, not claims that the app or commands already exist.
Document prerequisites and make each target fail with an actionable message when absent.

| Command | Required behavior |
|---|---|
| make setup | Install exact locked dependencies and check runtimes; no cloud writes or business data |
| make dev | Start local emulators, API, worker and web; show local/AI mode; no automatic seed |
| make migrate | Apply idempotent local schema/index setup; cloud target must be explicit |
| make bootstrap-admin | Provision an empty workspace for an existing Firebase uid; documented CLI inputs |
| make generate-contracts | Produce TypeScript/client and Python conformance artifacts deterministically |
| make add-member | ADMIN-only CLI to add an existing Firebase uid/role to a workspace; no invitation or public self-registration |
| make verify-spec | Run the supplied pack validator plus a pinned OpenAPI/JSON Schema validator added in T00 |
| make test | Deterministic unit, contract and local integration tests |
| make test-e2e | Browser acceptance on an isolated empty local workspace |
| make test-cloud | Adapter/authorization parity on a dedicated disposable cloud test dataset |
| make eval-live | Run model cases, export denominators, errors, versions, latency and cost |
| make deploy-dev | Build/deploy to explicitly configured, authorized Google Cloud development resources |
| make seed-demo | Optional T13 command; explicit target workspace, normal service/import path, idempotent |

Use environment variables or a local ignored configuration file for project/uid values.
Never select a production project automatically. Destructive cleanup must be separately
named and must verify its disposable test target. Do not make “test” erase a normal database.

## Cloud release

T11 provides repeatable deployment with narrow service accounts, private worker endpoints,
Cloud Tasks authentication, scheduled outbox repair, Firestore indexes, private objects
and an analytical dataset in the chosen region. Use backend workload credentials, no
downloaded service-account keys in source control. Explicitly validate Firebase tokens
even when the API has public network ingress.

Health reports process readiness; it must not pretend unavailable required providers are
healthy. Include structured error logging, correlation/job IDs, tokens/cost and retry
counts. Cap model calls, daily workspace usage and query bytes. Start with a configurable
USD 100 development budget, but enforce application quotas because billing alerts do
not stop spend. Avoid production data in logs and public evaluation artifacts.

After deploying an empty application, exercise the normal management/import/rep flow in
a fresh browser. Confirm restart recovery, signed-media access and denied cross-workspace
requests in the deployed environment. Preserve a deployment revision and documented
rollback procedure. Do not describe fixture playback as a live model response.

## Completion evidence

Record the implemented commit, deployment revision/URL, migration/index versions, test
commands/results, live evaluation report and unresolved limitations in docs/release.md.
Provide empty-install instructions and normal CSV templates. The coordinating agent
must distinguish “implemented locally”, “deployed”, “live evaluated” and “blocked”.
The competition video/deck remains a later submission task after the software is accepted.
