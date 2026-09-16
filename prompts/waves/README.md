# StoreOps Wave-by-Wave Execution Prompts

These prompt templates are designed for use with the `/goal` command or autonomous agent sessions. Each file corresponds directly to an implementation wave defined in [specs/08-parallel.md](../../specs/08-parallel.md) and task packets in [plan/tasks.json](../../plan/tasks.json).

---

## How to Run a Wave

To execute a wave, run `/goal` with the corresponding wave file:

```markdown
/goal Execute Wave 1 following prompts/waves/wave-01-t01.md
```

The agent will run until the wave's integration gate passes, all acceptance tests for that wave are green, and the task statuses in `plan/tasks.json` are updated to `"integrated"`.

---

## Wave Roadmap

| Wave | File | Tasks | Primary Focus | Gate |
| :--- | :--- | :--- | :--- | :--- |
| **Wave 1** | [wave-01-t01.md](wave-01-t01.md) | `T01` | Empty identity, persistence, and durable job foundation | **G1**: Empty authenticated app persists state through restart; zero seed |
| **Wave 2** | [wave-02-core-foundations.md](wave-02-core-foundations.md) | `T02`, `T03`, `T05`, `T06`, `T11` | Catalog, CSV ingestion, Web UI shell, Gemini gateway, Cloud setup | Independent module gates & contract doubles |
| **Wave 3** | [wave-03-policies-investigations.md](wave-03-policies-investigations.md) | `T04`, `T07` | Reviewed policies and persisted investigations | Admin approval required, safe stale policy writes, unseeded investigations |
| **Wave 4** | [wave-04-connected-ui-verifier.md](wave-04-connected-ui-verifier.md) | `T08`, `T09` | Connected browser workflow & execution verifier | **G4**: Compliant photos close once; UI consumes live services with reload recovery |
| **Wave 5** | [wave-05-hardened-regressions.md](wave-05-hardened-regressions.md) | `T10` | Regression hardening, concurrency, failure modes | **G2–G5 local**: Deterministic suite passes without service boundary mocks |
| **Wave 6** | [wave-06-live-cloud-evaluations.md](wave-06-live-cloud-evaluations.md) | `T12`, `T13` | Cloud parity, live Gemini evaluations, optional demo seed | **G3/G5/G6 live**: Actual cloud & model gates pass; demo data optional |
| **Wave 7** | [wave-07-mvp-acceptance.md](wave-07-mvp-acceptance.md) | `T14` | Final core MVP acceptance from empty install | Full fresh deployment accepted; zero seed dependency |
