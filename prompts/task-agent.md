# Bounded implementation task

Task ID: <TASK_ID>
Integration base commit: <COMMIT>
Branch or worktree: <PATH>

Read AGENTS.md and your task packet in plan/tasks.json. Read its specs, operations,
contracts and acceptance IDs. Work only inside owned_paths; the coordinator owns shared
contract and composition-root changes. Do not expand scope.

First return a short implementation/test plan. Then write meaningful acceptance tests,
implement the slice, and run the specified checks. Use ports and contract-compatible
test doubles where dependencies permit them. Identify every simulated dependency in
the handoff; no stub can satisfy a live acceptance criterion.

If an interface is missing or inconsistent, send a contract-change request with the
affected operations/tasks and proposed tests. Do not fork the interface locally.

Finish with changed files, acceptance evidence, exact commands/results, remaining
blocked checks, migration/registration requests and a reviewable diff.
