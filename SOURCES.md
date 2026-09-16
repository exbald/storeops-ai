# Technical references

Checked 16 September 2026. These sources support platform capabilities, not claims that
StoreOps has been implemented or has achieved an evaluation target.

- [Gemini 3.8 Flash](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash): image/PDF inputs, structured output, function calling and supported thinking levels.
- [Model lifecycle](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions): 3.8's shorter lifecycle and long-lived fallback options; recheck at implementation/release.
- [ADK deployment](https://google.github.io/adk-docs/deploy/cloud-run/): ADK applications can run on Cloud Run.
- [Structured output](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output): provider schema support is a subset; retain independent validation.
- [Bounding boxes](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/bounding-box-detection): normalized image coordinate convention.
- [Cloud Tasks](https://docs.cloud.google.com/tasks/docs/dual-overview): asynchronous at-least-once dispatch requires idempotent handlers and gives no strict dispatch timing guarantee.
- [BigQuery transactions](https://docs.cloud.google.com/bigquery/docs/transactions): transactional DML for fact and manifest commit; test the chosen load/staging approach.
- [Firebase emulators](https://firebase.google.com/docs/emulator-suite): local service emulation for development; it does not replace cloud adapter acceptance.
- [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html): public API description and JSON Schema dialect.

Competition positioning, deadlines and deliverables remain in the earlier competition
PRD. They are not application constants or release-test inputs.
