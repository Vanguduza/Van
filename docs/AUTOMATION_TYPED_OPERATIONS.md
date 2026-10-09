# Typed automation operations

The gateway accepts this closed operation vocabulary. It does not evaluate
JavaScript, Python, template expressions, regex predicates or arbitrary actions.
The paired owner can read `GET /v1/owner/automation/contracts` and propose an
immutable WorkflowIR through signed `POST /v1/owner/automation/plans`. The body
contains `idempotency_key`, `semantic_name`, `workflow_ir` and optionally an owned
`capability_id` for a new version. Proposal is not admission or deployment.
The exact signed owner command `automation admit {artifact_id}` provisions and
independently reads back the n8n parent and helper graphs, then performs guarded
quarantine, validation and admission. It requires existing protected operator
runtime bindings and current owner authority; proposing a plan grants neither.
Execute uses `automation execute {capability_id} artifact {artifact_id} with
{inputs_json}`. The resolver derives the action class and exact parameters from
the sealed admitted artifact before issuing any biometric approval challenge.
Recognized malformed or unready automation commands refuse without falling back
to a general agent. Both stages finish through actual mission target observation.

Workflow fields are given by the catalog's actual `workflow_ir_schema`. Input
bindings retain `$input.field`, `$steps.step_id.field`, or an output alias's dotted
path. References must point to ancestors. Ordinary expressions are refused.
The command's JSON object must satisfy the closed bounded input-schema subset:
type, properties, required, items, enum, const, numeric bounds, string length and
array length. Every input field must be declared, including when a schema asks
for additional properties. Unsupported or malformed assertions refuse. The
gateway inserts its reserved artifact pin; an owner cannot supply or override it.

Predicates use fixed tags and typed values:

```json
{"op":"EQ","left":{"kind":"PATH","path":"payload.status"},"right":{"kind":"LITERAL","value":"ready"}}
```

`PATH` reads a dotted object path in resolved step inputs; `LITERAL` preserves
literal JSON, including strings that begin with `$`. Operators are `EQ`, `NE`,
`LT`, `LTE`, `GT`, `GTE`, `IN`, `CONTAINS`, `EXISTS`, `ALL`, `ANY`, and `NOT`.
`ALL`/`ANY` take `args`; `NOT` takes `arg`; `EXISTS` takes a PATH `value`.
Other operators take `left` and `right`. Missing operands refuse evaluation
except `EXISTS`. Comparisons do not coerce strings or booleans into numbers.
Predicate limits are depth 8 and 64 nodes. All boolean operands are checked.
Step `precondition` is one such predicate over its resolved input bindings;
false is a durable `REFUSED` receipt and causes no step effect.

| Primitive / operation | Exact input bindings | Result |
| --- | --- | --- |
| FILTER / evaluate_predicate | `payload`, `predicate` | `matched`, `selected_branch` true/false, payload |
| SWITCH / select_branch | `payload`, `cases:[{branch,predicate}]`, `default_branch` | first matching case, predicate results, selected branch |
| MAP_FIELDS / map_fields | `payload`, `fields:{target:value_spec}` | mapped payload; up to 64 flat target fields |
| MERGE / merge_objects | `sources:[object or null]` | merged payload; overlapping keys refuse |
| WAIT / bounded_wait | `delay_ms` integer 0..30000 and below sealed timeout | waited_ms after bounded gateway wait |
| VAN_CAPABILITY / reminder.create | `text`, `due_at_unix`, optional `project_id` | actual reminder ID, verified local target digest and reminder:// pointer |

Selectors require a labelled edge for each case/default or both true/false
outputs. Other steps cannot have labelled outputs. The gateway settles all
incoming parents, then executes a step if any incoming edge is selected. n8n
only schedules callbacks in deterministic topological order. A nonselected
callback consumes its own grant and records `SKIPPED` with exact parent receipt
digests; it never executes the operation. An optional binding at a branch join
is `{"kind":"STEP_RESULT","step_id":"branch_step","path":"payload","optional":true}`.
Only a confirmed SKIPPED ancestor resolves to null. Missing or uncertain data
is refused. MERGE can join these optional results without inventing outputs.
The observer recomputes selections and transformations and reads actual targets.
Exactly one selected terminal result must satisfy the workflow verifier.

`HTTP_REQUEST/write_json` takes `url`, `method` POST/PUT/PATCH, `body`, and
`readback:{url,predicate}`. `HTTP_REQUEST/delete_resource` takes the same fields
except body and uses DELETE. Both require A4, WRITE/DELETE effect, a protected
credential alias with operator-bound domain and explicit allowed method, one
attempt, and postcondition `{"kind":"READ_BACK","field":"verified","expected":true}`.
The gateway sends a deterministic per-run/step Idempotency-Key. It then performs
an independent GET and evaluates the sealed readback predicate. The verifier
GETs again without repeating the write. Both URLs stay on the sealed exact
domain, pass normal TLS verification and global-address DNS pinning, and cannot
redirect. Protected source configurations default to GET-only; add
`allowed_methods:["GET","POST"]` only when the actual provider binding has
been reviewed. Credentials never enter plans, n8n graphs, or owner readbacks.

There is no arbitrary VAN_CAPABILITY dispatch. The defined native operation is
reminder.create, using the existing ReminderService and an exact server-generated
idempotency key; reminder row readback must match the requested text, due time,
project and OPEN state. Payments, financial execution, authority writes and
identity mutation stay prohibited. EXECUTE_SUBWORKFLOW is not a supported user
operation; sealed provisioned helpers are execution plumbing, not mutable nested
owner plans.

Triggers remain INVOKE, UTC five-field SCHEDULE, EVENT, or WEBHOOK. Recurring and
event runs require a gateway-sealed standing authority with exact source event
or due schedule and bounded parameters. Native n8n timers and public webhooks
cannot create owner authority. A4 external writes cannot acquire standing
authority. Expired, disabled or revoked authority refuses every fresh callback.
Mission pause and terminal state fence each fresh step claim in the same SQLite
writer transaction. A call already admitted may finish; pause does not attest
that a provider process stopped. Resume requires a fresh valid admission, not
resurrection of a consumed grant.

`GET /v1/owner/automation/plans` and `/plans/{artifact_id}` expose immutable IR,
digests, lifecycle, binding state and readiness. `/runs/{run_id}` exposes durable
step states and evidence only for that command's owner device. IN_PROGRESS or
REFUSED is not completed success. Uncertain writes cannot be retried; inspect
target state and obtain a new owner decision. A completed identical candidate
proposal replays by idempotency key; changed input conflicts; an interrupted
proposal claim remains pending. Engine success is never owner success.

These are source contracts and local testable services. Live qualification still
requires actual operator source bindings, approved private n8n and worker ingress,
provider canaries and the owner's phone acceptance.
