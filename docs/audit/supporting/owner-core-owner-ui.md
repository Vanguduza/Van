# Owner service and browser UI completion — 2026-10-07

Local implementation and checks only. No S24 Ultra, Artemis device route, production deployment, media transfer, or provider live acceptance was exercised by this work.

## Implemented owner information

`OwnerServiceRoutes.kt` and its pure `OwnerServicePresentation.kt` now render every previously missing owner-safe browser-outcome DTO field: the worker's nullable final goal proposal, source trust, injection assessment, exact URL/DOM/screenshot/extraction digest references, and missing postconditions. An absent proposal is not inferred from `execution_completed`; neither an empty missing-postconditions array nor trust labels imply verified task success. Linked mission verification remains separately scoped, with recorded verification time and evidence references. Knowledge/research citations additionally expose supplied source trust and content digests; knowledge evidence state and scope are displayed when supplied.

## Implemented browser review and control

`BrowserActivity` now exposes the existing real Take Control action and a Downloads & phone files panel. The panel uses the owned-session downloads GET and an owner-signed, scoped DELETE. It shows host state, known size/type, dangerous/quarantine/failure information and the supported delete decision. An explicit confirmation explains that record removal does not prove physical host cleanup or remove a separate phone copy. Removal succeeds visibly only after a receipt for the exact download ID and an independent downloads GET reporting that same record as DELETED. A lost or malformed reply, lost confirmation, mismatched receipt, stale state, or absent record stays unknown. No unkeyed deletion is retried automatically. Reads preserve the previous confirmed records on failure and block further mutation until refresh.

The controller's actual Take Control/pause/end paths share one atomic pending lease. Repeated or simultaneous taps/lifecycle calls cannot issue parallel unkeyed control mutations. Input is held during the request. Cancellation propagates while leaving authority uncertain and the last confirmed snapshot visible. A readback is required before another control decision. Late heartbeat or other confirmation snapshots cannot replace a newer control generation, viewport revision, or session identity. Terminal/already-owner states do not generate another Take Control request.

## Explicit unsupported states

Saving/opening/analysing/sending a download and phone upload are visible as unavailable because the gateway supplies no qualified binary route for them. The host's advertised actions alone do not manufacture a transfer API. The phone file chooser is refused before opening; `beginUpload` no longer manufactures TRANSFERRING tickets or a literal upload ID without sending bytes. Clipboard sharing remains off; reviewing a file does not grant file analysis authority.

At the checked backend snapshot, downloads GET advertises DELETE for CREATED/IN_PROGRESS although its broker refuses those transitions. The frontend blocks these actions and states that a supported final host state is required. Root was notified to align the backend advertisement with actual transitions.

## Validation

- Targeted production-pure JVM code: **38 cases, four suites, zero failures/errors/skips**. Includes nullable proposal/digests/trust/postcondition presentation, guarded concurrent control requests, cancelled request authority, monotonic snapshot replacement, exact removal readback, transport ambiguity, unsupported states, malformed replies, and cancellation propagation. Log: `/workspace/van-audit/owner-ui-browser-focused.log`.
- Existing Android compilation/design/navigation source contracts: **24 passed**. Log: `/workspace/van-audit/owner-ui-contracts.log`.
- Real ASGI/backend browser takeover/download and interactive-browser API cases: **85 passed**. Log: `/workspace/van-audit/owner-ui-browser-api.log`.

These focused checks overlap the full suites and must not be added to aggregate totals. Root owns final application compilation, lint, registry source citation refresh and immutable final evidence capture.

## Registry refresh guidance

- `van.browser.outcome`: missing DTO presentation fields are implemented; independent standalone task-goal observation and live provider/handset qualification remain unverified.
- `van.browser.downloads`: now reachable as `BrowserActivity`'s Downloads & phone files panel. Review and record removal are implemented. Binary download/open/save/send/analysis, phone upload and physical cleanup qualification remain unavailable; this surface is partially implemented rather than fully complete.
- Browser control surfaces: Take Control is reachable, pending authority mutations are serialized and failures/cancellation preserve unknown outcomes. Owner authority/media/viewport gates still apply.
- Do not change frozen baseline provenance. Add current citations for `BrowserDownloadReview.kt`, `BrowserDownloadsPanel.kt`, `BrowserActivity.kt`, `BrowserControlMutation.kt`, `BrowserSessionController.kt`, `BrowserUpload.kt`, `VanGatewayClient.kt`, `OwnerServiceRoutes.kt` and `OwnerServicePresentation.kt` after the final source freeze.
