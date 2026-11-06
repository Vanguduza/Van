# Renderer-independent chart workspace persistence

Chart workspace backend component: additive migration56, typed renderer-independent multi-panel settings, exact native product refs as unverified owner context, decimal-string price/time drawings and seven typed presentation/research indicator configurations. Revision-checked atomic CRUD, immutable snapshots/restore-as-new-revision, paged histories, owner-scoped original request identities/outcomes and failed-commit recovery; deletion removes live SQL state/revision bodies and retains no notes in minimal outcome receipts. Explicit original scope/hash/capacity refusals; authenticated current owner/device proof and private no-store responses.57 focused/144 integrated/10 privacy/1 real backup-restore/29 registry/79 rebuild pass0skip,15 fault/control pairs caught/restored. New9routes ->457endpoints333schemas;42features105functions78surfaces preserved. No newUI/Androidconsumer, certifiedindicatorcalc/nativebinding/export/renderqualification or wholeBE018 claim.

This implements a backend component of the original BE-018 contract, without importing a renderer or changing Android visuals. Saved instrument selection preserves venue, environment, API family, native product/symbol/account and optional contract revision. Same symbols at different providers remain distinct. These are owner-authored contextual references; every read explicitly marks native binding unverified, and no order, grant or certified VATI result can be created by saving them.

Workspace schema 1 has stable panel/indicator/drawing identities; layouts, timeframes, chart type, viewport and sync selection; exact UTC millisecond and decimal-string anchors; and typed SMA, EMA, RSI, ATR, MACD, Bollinger and anchored VWAP settings. Pixels, floats as prices, duplicate child IDs, invalid parameter versions and false VATI_SOURCE claims are refused. Settings support PRESENTATION and RESEARCH, with certified server calculation still pending in the original programme. Restoring a prior revision can reset settings or undo/redo a saved layout without editing the original history.

| Method | Route under `/v1/trading/charts` | Result |
| --- | --- | --- |
| GET | `/capabilities` | Actual component schema and limits; pending native/renderer/calculation capabilities remain false |
| GET | `/operations/{request_id}` | Exact original minimal outcome; read never dispatches |
| GET | `/workspaces` | Paged owner workspace summaries and actual total |
| POST | `/workspaces` | Create with stable request identity |
| GET | `/workspaces/{workspace_id}` | Current or exact `revision` snapshot |
| PUT | `/workspaces/{workspace_id}` | Full typed state and expected current revision |
| DELETE | `/workspaces/{workspace_id}` | Revision-checked deletion and original minimal outcome |
| GET | `/workspaces/{workspace_id}/revisions` | Paged immutable history |
| POST | `/workspaces/{workspace_id}/restore` | Copy one owned original snapshot as a new revision |

A request ID is bound to owner, operation, target and canonical full request. Identical replay returns its original outcome even if the current head changed or was deleted; changed scope is refused. A concurrent stale save reports CHART_REVISION_CONFLICT with the current revision. One native SQLite write transaction commits head, revision and minimal receipt. After a failed commit acknowledgement, a fresh exact operation lookup distinguishes observed original completion, known absence and unavailable/conflicting readback. The latter remains OUTCOME_UNKNOWN with request ID; a newer head or conflicting caller cannot become the original result. Cancellation or failed receipt insertion before commit leaves no partial state. Unknown results can be read before any repeat.

State size, workspace count and revision-count budgets fail explicitly; no automatic retention or history eviction is chosen. Workspace deletion removes all live revision bodies, while minimal operation outcomes contain IDs, revisions and hashes only. This is logical SQL deletion, not a physical-media sanitisation qualification. The existing owner-memory inventory explicitly names saved chart work separately from inferred memory and points to the dedicated delete control. Existing backup and restore services preserve all current/original snapshots and outcomes, and additive migration resumes partial table creation without losing earlier owner data.

Evidence: `../receipts/CHART_WORKSPACE_SOURCE_20261023.json`. Two initial gateway 404 failures demonstrate missing wiring; a malformed new test fixture and the intermediate missing no-store header are recorded separately. Source assertions and deliberately broken behaviours use actual SQLite persistence, conflicts, cancellation, lost ACK, native readback and current authenticated ingress, not mocks claiming broker effects. The registry links original planned chart feature IDs and lists each new endpoint; Android consumption remains pending.

Original remaining work includes certified indicator calculation, native instrument/data/freshness integration, live subscriptions/depth, observation consent/export, renderer/device performance and full cross-domain qualification. No original feature, requirement, action or gate is retired by this component.
