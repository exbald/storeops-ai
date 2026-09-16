# StoreOps specification driven MVP build

Version 2.0 · 16 September 2026

This is an implementation specification for coding agents. The target is a working
StoreOps application that starts with no business records, accepts data through its
own management and import workflows, and completes an investigation, approved action
plan and visual verification. Demonstration data is an optional later addition.

**Status:** specification and contract pack, not an implemented application. The only
executable utility supplied here checks the pack itself. Task and acceptance statuses
are all planned. No application tests or live Gemini evaluations have been run.

## What changed from the competition PRD

The earlier document remains useful for the pitch and demonstration narrative. This
pack supersedes its implementation choices wherever they conflict. It adds the missing
application lifecycle: empty-state setup, catalog management, CSV ingestion, policy
review, durable jobs, user roles, versioned contracts and incremental acceptance gates.

- Stores, SKUs, rules, dates and image references are data, never application constants.
- The database is created through migrations; seeding is a separate command.
- Small test factories and representative images are used while building each slice.
- A larger demo dataset can be imported after the core MVP passes acceptance.
- Parallel agents work within explicit boundaries after shared contracts are frozen.

## Read and build in this order

| File | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Binding working procedure for implementation agents |
| [Product](specs/00-product.md) | Required behavior and the definition of a complete MVP |
| [Architecture](specs/01-architecture.md) | Components, local/cloud profiles and adapter interfaces |
| [Domain](specs/02-domain.md) | Persistent entities, ownership, imports and temporal semantics |
| [Workflows](specs/03-workflows.md) | State transitions, atomicity, retries and concurrent edits |
| [UI](specs/04-ui.md) | Screens, empty states, actions and error behavior |
| [AI](specs/05-ai.md) | Two agents, tools, observations, grounding and model settings |
| [Quality](specs/06-quality.md) | Tests during implementation, live evaluations and release gates |
| [Delivery](specs/07-delivery.md) | Commands to implement, deployment and operational acceptance |
| [Parallel work](specs/08-parallel.md) | Dependency waves, code ownership and integration protocol |
| [OpenAPI](contracts/openapi.json) | Versioned public HTTP contract and request/response schemas |
| [Tool contracts](contracts/tools.json) | Typed agent inputs and evidence-returning tools |
| [AI schemas](contracts/ai-output.schema.json) | Model output contracts, separate from public API responses |
| [Wire semantics](contracts/SEMANTICS.md) | Cross-field validation and retry rules |
| [Imports](contracts/imports.json) | Exact CSV columns, field rules and correction behavior |
| [State machines](contracts/states.json) | Allowed application and job transitions |
| [Tasks](plan/tasks.json) | Assignable work packets with dependencies and acceptance IDs |
| [Acceptance](plan/acceptance.json) | Given/when/then cases linked to requirements and owners |
| [Decisions](DECISIONS.md) | Deliberate changes and their reasons |

The Markdown specifications explain semantics; the contract files define wire shapes.
If they disagree, record a contract issue and resolve it before dependent code. Neither
an agent's convenience nor a passing mock is authority to change intended behavior.

## Starting an implementation session

Extract this directory as the repository root, initialize Git, and give the coordinating
agent [prompts/orchestrator.md](prompts/orchestrator.md). It begins with T00, then T01.
The ready tasks in `plan/tasks.json` determine when parallel work is possible.

Run the supplied check before editing the pack:

```bash
python3 tools/verify_spec.py
```

The application commands listed in the delivery spec must be implemented during T00
and T01; they do not exist yet. The coordinator records exact runtime/dependency
versions and resolves genuine implementation blockers without expanding product scope.

## Complete means usable without the demo

From an empty deployment, an authorized user can create stores and products, upload
references, import sales and stock, approve rules from a real uploaded agreement,
record a visit, investigate, accept tasks, upload new evidence and receive a saved
verification report. Missing data is an explicit state. Refreshing the browser or
retrying a job does not lose work or duplicate writes.

The build also has automated regression tests, cloud adapter checks and a live Gemini
evaluation report. A green test-double run alone is not proof of an AI-capable MVP.

The first optional demo seed is T13. It is deliberately not a prerequisite for T14,
the core MVP completion gate. Budget and timing estimates in the earlier competition
PRD should be revised after T00/T01 expose actual implementation effort.
