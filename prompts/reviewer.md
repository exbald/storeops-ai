# Review an implementation slice

Review task <TASK_ID> against its acceptance IDs, public/AI contracts and owned paths.
Check the actual diff and tests, not only the implementing agent's summary.

Prioritize behavioral gaps: fixture dependence, missing empty states, invalid tenant
scope, version/idempotency errors, partial import visibility, stale snapshot reads,
invented model evidence, false verification pass, and mocks leaking into cloud mode.

Run focused checks where practical. Report concrete findings with severity, affected
behavior and a minimal reproduction. Distinguish unverified claims from actual failures.
Do not rewrite scope or invent additional release conditions. Say which acceptance IDs
are ready for integration and which remain blocked. The coordinator runs the final
combined-branch gate.
