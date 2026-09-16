# Start the StoreOps build

Implement the StoreOps MVP described by this repository's specification pack.

Read README.md, AGENTS.md, specs/ and plan/tasks.json. Start with T00 and T01. Preserve
the empty-database behavior and the separation between application, tests and demo seed.
Do not implement from the competition scenario alone.

Maintain a visible task ledger with planned, active, review, integrated or blocked states.
For each ready task, state owned paths, required contracts, tests and dependencies. If
parallel agents are available and authorized, assign independent ready tasks in the
documented waves. Otherwise use the same packets sequentially. You own shared contracts,
composition roots and integration; do not let specialists create competing interfaces.

Implement one accepted vertical slice at a time, with failing acceptance tests before
the implementation. Demonstrate persisted behavior after every wave. Run the combined
branch's contract/integration gate before unlocking dependents. Do not count a stubbed
model or in-memory database as a live cloud implementation.

Resolve routine implementation details yourself using the written constraints. For a
material spec gap, propose a precise contract change and its affected tests. Respect
session authorization for deployment/spend/external actions. If credentials are missing,
finish all local work and report the specific blocked live gate.

The target is T14 complete: an empty installation that can be populated through normal
screens/imports and complete a real investigation/acceptance/verification cycle. T13 demo
data is optional. Report exactly what is implemented, tested, deployed and live evaluated.
