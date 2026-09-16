# Implementation decisions

| ID | Decision | Reason |
|---|---|---|
| ADR01 | Build an empty, data-driven application; optional seeds are separate | The earlier PRD conflated a convincing demo fixture with the software's behavior |
| ADR02 | Firestore owns operational catalog/policy/workflow state; BigQuery owns imported facts | Supports ordinary management and transactional task writes while retaining real analytical tool use |
| ADR03 | Durable jobs with 202/polling replace request-owned synchronous investigation | Browser refresh/disconnect must not lose work; queue delay is explicit and not a promised realtime SLA |
| ADR04 | Contract files and acceptance IDs govern parallel work | Agents need compatible data, error and state semantics before independent implementation |
| ADR05 | CSV ingestion and policy review are required MVP features | Users must be able to populate the product without editing database rows or code |
| ADR06 | Model outputs are proposals; services own authorization/math/state | A valid JSON response cannot authorize a business effect or establish visual truth |
| ADR07 | Gemini 3.8 Flash is primary; 3.5 is an evaluated fallback candidate | Honor the preferred current model while making lifecycle changes explicit and testable |
| ADR08 | Small engineering fixtures precede the final demo seed | Regression and multimodal feasibility must be checked during development, not only after completion |

This specification does not authorize immediate cloud deployment or spending. It specifies
what implementation agents must build and verify when execution is authorized.
