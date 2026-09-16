# StoreOps implementation agent instructions

These instructions apply to implementation work using this specification pack. Follow
the user's current instructions first. Do not treat this file as authorization to
publish, spend money, contact people or overwrite unrelated work.

## Read before changing code

Read README.md, the task packet in plan/tasks.json, its referenced specifications,
contracts/openapi.json, contracts/SEMANTICS.md and applicable acceptance cases. Do not implement from the
competition PRD alone. All task records initially describe planned work.

## Work one accepted slice at a time

1. Check dependencies. A task is ready only after its dependencies are integrated.
2. State its acceptance IDs, input/output contracts and owned paths.
3. Write meaningful failing tests for the slice's observable behavior.
4. Implement the smallest complete change through its required layers.
5. Run the task tests and affected contract/integration tests.
6. Submit a reviewable diff and a handoff using the template below.
7. The coordinator integrates it, reruns the gate, and then unlocks dependents.

Use test fixtures from the start. Never wait until the whole app is written to test it.
Do not add sample business records in migrations, app startup, deployments or normal
requests. Application modules must not import fixtures, demo seeds or evaluation labels.

## Contracts and parallel ownership

The coordinator owns contracts/, the composition roots, shared dependency locks,
integration settings and changes to this pack. After T00, contracts are frozen for each
wave. Raise a concise change request before changing public shapes, persistence keys,
state transitions or adapter interfaces. Include affected tasks and acceptance tests.

Use one branch/worktree per active task. Do not edit another task's owned paths. If a
change crosses ownership boundaries, coordinate it; do not copy a competing type or
repository implementation into your module. Use the contract's names exactly.

Type generation may create files, but do not hand-edit generated clients. Keep all
database schema changes in versioned migrations owned by the data task. No fabricated
APIs, implicit in-memory production stores or success-shaped fallback responses.

## Completion and honesty

Report actual commands and results. Distinguish unit tests, adapter integration tests,
browser acceptance and live model evaluations. A stubbed provider cannot satisfy a
live gate. Missing credentials produce a blocked live gate, not a successful test.
Never silently skip a mandatory check or mark an unimplemented task done.

Keep implementation iterations local or in authorized development infrastructure.
Respect existing repository changes. Create commits only when authorized by the session
or repository workflow. Do not add Codex attribution to commits or pull requests.

## Required handoff

- Task ID and acceptance IDs covered
- Contracts consumed and any proposed changes
- Files changed and migration implications
- Tests run with exact results and remaining blocked checks
- Screens/requests that demonstrate the behavior
- Known limitations, next dependency and rollback notes

Update the task's execution record only after integration; preserve the original
acceptance criteria. If the user changes scope, update the spec and traceability first.
