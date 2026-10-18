# Backend-to-Experience Contract Bundle — Rev 1.11

This bundle is completed in BE-032 and accepted at BG-001. It is not a server-generated UI framework: the backend reports capabilities and state; a separately designed native frontend controls composition under locked design authority.

## Stable context identity

Every context carries project/owner scope, selected account ID (never inferred from aggregate ALL), canonical instrument and venue, source epoch/revision, event/received time, validity/freshness, permission revision and an explicit authoritative outcome. Use opaque IDs, exact quantities, currency and unit type. Display-rounded numbers never re-enter risk calculations.

## Required per-capability contract

`capability_id`, `owner_requirement_refs`, `domain_owner`, `purpose`, `allowed_contexts`, `read_operations`, `effect_operations`, `inputs`, `outputs`, `validation`, `authorization`, `state_machine_ref`, `persistence`, `idempotency_scope`, `receipt_lookup`, `recovery`, `rate_limit`, `source_age_rules`, `provider_support`, `version`, `deprecation`, `tests`, `source_binding`, `runtime_proof_refs`.

Every effect operation declares preview, argument digest, exact owner/device proof where required, eligibility read, domain execution, idempotency/outbox and reconciliation lookup. Neither a model nor renderer can call raw broker or infrastructure commands.

## Required per-action presentation data

`action_id`, `capability_id`, `subject_ref`, `context_digest`, `classification NAVIGATE|READ|DRAFT|OWNER_EFFECT`, `eligibility AVAILABLE|REVIEW_REQUIRED|STALE|NOT_SUPPORTED|UNKNOWN`, reason code and short text, exact proposed effect, source time, visible units, semantic warning, expected state transitions and cancellation semantics. The app cannot enable a financial action simply because its control was rendered.

The server supplies stable semantic keys and verified facts, not HTML/JavaScript that can mint grants or a compulsory grid of every internal field. UI text is generated from approved templates or checked facts. Security metadata, hashes and low-level request bodies stay in expandable evidence surfaces, not Home.

## Snapshot and event contract

Use `source_id`, `stream_id`, `epoch`, `sequence`, `event_id`, `occurred_at`, `received_at`, `snapshot_revision`, `subject_id`, `payload_schema`, `freshness`, `correlation_id` and `authority_effect`. A reconnect obtains a versioned snapshot and subsequent ordered events. Duplicates do not animate again or submit again. A cursor gap or incomparable epoch does not merge old and new truth.

Trading and work domains keep independent revisions. A global badge cannot claim all sources LIVE because market prices are fresh while positions or task ownership are stale. Tick coalescing may reduce redraw frequency, never drop meaningful order, approval or ledger transitions.

## Native versus backend ownership

| Concern | Complete in backend phase | Complete after BG-001 |
|---|---|---|
| Chart | Instrument/bar/provenance APIs; canonical settings/drawings/indicator models; bridge schema; research intake; replay namespace | Renderer, crosshair/gesture/surface lifecycle, native/web host, local viewport/store and accessible controls |
| Orb | Orthogonal presence sources, severity reducer policy, freshness, canonical attention/briefing projections | Metallic render, motion, hit targets, Home composition, compact popup and accessible captions |
| Tasks | Authoritative graph, assignments, stage progress, handoff/lease events and actions | Spatial layout/gestures, node selection, mini-map, list alternative and tactile hierarchy |
| Accounts/funds | Full identity/auth/quote/approval/operation/reconciliation/capability services | Native forms, verified provider handoff chrome, receipt/detail/protection UI |
| Voice/device | Server protocol, policy, stored consent, existing qualified device adapter interface and test vectors | New Android mic/overlay/notification/provisioning UX and exact S24 permission/lifecycle proof |
| Muse/browser | Real scoped job/session/approval broker with provider readback | Native conversation/control panel and viewport touch interaction |

## Headless consumer acceptance before frontend

For every action, exercise the genuine registered gateway contract from an isolated authorized test client. Validate exact scope, messages, real dependent services, positive/refusal/unknown outcomes and readback. Unit tests and fake endpoints remain development aids, never the sole integration evidence. Headless tests must not skip authentication because the mobile signing UI is not built; use an already qualified signing/test authority whose scope excludes live effects where not approved.

Include complete contract data for every feature, not just five representative flows. Representative flows are risk-discovery probes in BQ; they cannot certify untested sibling capabilities.

## Consolidated model/research/execution extensions

Every target screen resolves against the same completed BE-032 catalogue. The additional model registry, calibrated expectations, candidate trial history, source/evaluator qualification, risk-policy activation and pending-order recovery contexts are declared in ALL_SURFACE_CONTRACTS.json. Model scores, event-market probabilities and DSR/PBO statistics have different semantics and labels; none can directly create a trade. Global hard risk covers all origins, while discretionary and autonomous cooldown scopes are displayed distinctly. Order submission, venue working, fill, protection confirmation and terminal cancellation/expiry remain different states.
