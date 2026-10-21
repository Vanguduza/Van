# OWNER DECISION 2026-09-30 — network-effect guard for browser automation (review I6 M4)

Status: OWNER ANSWER RECORDED VERBATIM.

Channel: owner answer in Claude Code session `session_01ELKqm4GCPmPvF3ggKkgB1J`, 2026-09-30,
after independent review I6. No device, biometric or cryptographic signature is claimed. This
is not signed-ingress evidence.

Related records:
- `docs/decisions/OWNER-DECISION-20260930-BROWSER-TASK-SCOPE.md`: the same session's earlier
  answer on task-truth scope.
- Owner decisions 2026-09-29 §7–§9 (no lane self-certifies; the Harness is the single
  executor; router order with owner takeover as lane 4 that preempts automation).

## 1. The question put to the owner

> Some pages move money inside a JavaScript click handler behind a harmless label like "Next"
> or "Go". No check before the click can see this, and even a path-scoped task clicks them. How
> should Programme B handle it?

(Review I6 finding M4: I5's words page, #w5 "Next" and #w8 "Go", executed its payment handler
in origin-wide mode and with the pages served inside the path scope: 2/31 in both.)

## 2. Owner answer (verbatim, selected option label and option text)

> Network-effect guard (Recommended)

> While the Harness acts, it intercepts the page's network requests and blocks write requests
> (POST/PUT/DELETE and similar) unless the task is admitted as mutating. A blocked request goes
> to you. This catches handler-driven payments whatever the label, but tasks that legitimately
> submit forms must be admitted as mutating.

sha256 of the UTF-8 label `Network-effect guard (Recommended)` (no quotes, no newline):
`1fc63b2f9355a9c8534003a65e0bd8550288092795b4d07d2dcb2dec371107b0`.
sha256 of the UTF-8 option text above as one line (no quotes, no newline):
`b9b94542a3742f52de3bd01361b3e492624febc951b8ad937b48176e74d89352`.

## 3. How it is carried out (unit G9c; engineering, not further owner decisions)

- Harness (`deploy/van-browser-core/browser/harness_service.py`, `NETWORK_GUARD_PY`): CDP Fetch
  interception on the page, on a browser-target session and on every related out-of-process
  iframe and service worker, enabled before an action's input is dispatched and kept for a
  settle window (network idle 500 ms, at most 2000 ms after the input returns). Writes are
  failed with `BlockedByClient`; the action ends as a typed refusal
  `NETWORK_WRITE_BLOCKED:<kind>` (closed vocabulary; no URL, body or header). The guard
  refuses the action (`NETWORK_GUARD_UNAVAILABLE`) when it cannot be enabled.
- "Admitted as mutating" is task truth: `browser_tasks.mutating` (migration 37), set only when
  a task created with `mutating=true` passed `BrowserPolicyEngine.check_task`. Default false.
  The Harness honours it only under an effect MAC (`van-harness-effect/1`) over the lease
  fence, the task id, the flag and the scope digest; a mutating task may write only inside its
  task scope.
- Lane 4: the router and `/assignments` map the refusal to owner takeover; the task goes to
  `WAITING_FOR_OWNER` with `OWNER_TAKEOVER:NETWORK_WRITE_BLOCKED:<kind>`.
- Stated limits: a WebSocket handshake cannot be intercepted by CDP Fetch in Chromium 1194 (an
  open is detected and handed to the owner, not prevented); writes issued after the settle
  window are not covered by this action's guard.
