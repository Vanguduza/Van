# VAN Autonomous Web Acquisition Fabric — Rev 2 Hardened

**Status:** implementation candidate on PR #76; not production authority until acceptance gates pass.
**Authority:** Hermes and the existing VAN Browser Fabric remain authoritative. JEV is advisory only.
**Scope:** public web and supplier-consented account-visible acquisition. No supplier infrastructure administration is required by default.

## 1. Consolidated decision

VAN owns the acquisition control plane and treats fetch/crawl tools as replaceable workers.

The near-term estate uses the existing SQLite store, Browser Session Broker, Browser Harness, Stagehand and existing durable automation/Temporal facilities. Postgres/Valkey/Redpanda/DBOS are deferred until measured scale proves they are necessary. Steel is deferred because VAN already has an authoritative session broker and browser worker plane.

Crawlee is not a mandatory dependency. Its durable-frontier patterns are implemented in VAN core; Crawlee remains eligible as a scale-out plugin behind explicit benchmark triggers.

## 2. Exact stack

| Layer | Canonical responsibility | Status |
|---|---|---|
| Hermes | mission authority, scope, action-class bounds | existing |
| VAN Browser Harness | deterministic authenticated browser actuation and profile authority | existing |
| VAN Acquisition Frontier | durable queue, dedupe, priority, fencing, retry, cooldown, checkpoint, dead letter | implemented PR #76 |
| JEV | fast state/routing signal only; cannot admit a route | advisory |
| Scrapling 0.4.15 | public HTTP + public dynamic extraction/Markdown | pinned worker candidate |
| Katana 1.4.0 | optional bounded shallow URL/JS reconnaissance | optional worker |
| Browser network observation | runtime endpoint candidates from managed browser session, with query/header/body removal | Browser Harness |
| Stagehand 4.1.0 | semantic recovery/exploration when deterministic paths are insufficient | existing |
| n8n | slow schedules/deferred orchestration only | existing |
| Temporal | durable cross-step mission workflow where needed | existing/deferred by workload |
| Crawlee | future scale-out plugin only | deferred |
| Steel | no canonical role unless benchmark proves value | deferred |

## 3. Trust zones

PUBLIC uses the public_research browser profile. Public worker routes have no credential/profile mutation surface, challenge solving is disabled, sensitive credential-bearing query strings are rejected, and private/loopback network destinations are denied.

ACCOUNT_VISIBLE uses an admitted non-public Browser Fabric profile. Scrapling/Katana public-worker execution is inadmissible. Routing returns HARNESS, or STAGEHAND only when semantic interaction is explicitly required, so existing profile leases, secret indirection and action bounds remain authoritative.

## 4. Deterministic routing

JEV may select only among independently admissible routes and can never create a capability or authority. Authenticated profile work routes to Harness/Stagehand. Public structured data uses the cheapest direct/HTTP path. Unknown public sites use Katana reconnaissance. Qualified skills use deterministic replay. Dynamic public pages use Scrapling browser. Semantic uncertainty uses Stagehand.

## 5. Perception ladder

Prefer: structured network/API response -> hydration/application state -> accessibility representation -> normalized DOM/Markdown -> semantic model -> vision.

Katana maps the surface; it is not the canonical source of live API truth. Managed-browser network observation is the runtime source of endpoint candidates and strips query strings, headers, cookies and bodies.

## 6. Frontier invariants

Required invariants: profile-scoped URL dedupe; priority ordering; bounded attempts; fenced owner/token leases; renewable heartbeat; stale-worker mutation refusal; transaction-atomic failure transitions; restart reclamation; per-domain concurrency/delay/cooldown; rate-limit backoff; checkpoint/resume; and convergence into VAN's existing automation dead-letter sink.

## 7. Domain-skill lifecycle

EXPLORE -> CANDIDATE -> REPLAY -> QUALIFIED -> HOT -> CANARY -> HOT or QUARANTINED -> REPAIR -> REQUALIFY.

Qualification requires deterministic replay success, evidence, and at least one golden-case reference or explicit success assertion. Canary failure quarantines the current version while the most recent previously-qualified version remains available as last-known-good fallback. Learning cannot add domains, raise action class, acquire credentials or alter authority.

## 8. Evidence and provenance

Raw acquired payloads are not persisted in the acquisition SQLite tables. The evidence ledger stores content SHA-256, source URL digest, route, optional artifact reference, manifest digest, optional external-signature reference, byte size, and a hash-chain sequence/previous-hash/entry-hash. Verification recomputes both manifest digest and custody entry hash.

An external signature reference is not falsely treated as a verified signature. Cryptographic signature verification remains a separate qualification gate.

## 9. Runtime boundary

The van-web-acquisition-worker/1.0.0 process is loopback-only and public/read-only. Scrapling is pinned to 0.4.15. Static requests use safe redirect behavior. Dynamic requests use the pinned Chromium executable with a public-egress pre-navigation guard. The worker has no managed browser profile input.

Katana is optional and pinned to 1.4.0 when installed. It runs without authenticated crawling, custom credential headers, headless browser attachment, XHR extraction or CAPTCHA-solver options. Depth, duration, pages, concurrency, rate and private-IP access are bounded.

## 10. P0 corrections incorporated

Muse correctly found three P0 issues and all are addressed in this revision: long-job lease renewal; fail() lease-fence TOCTOU; and JEV route-admissibility leakage. Additional hardening adds public/authenticated route separation, last-known-good skill fallback, deterministic golden-case qualification, canary quarantine, content-addressed evidence, typed Hermes controls, sensitive-URL rejection, SSRF controls, network-candidate observation, and route telemetry.

## 11. Deliberately deferred

Do not add Steel, Postgres/Valkey/Redpanda/DBOS, mandatory Crawlee, Katana authenticated crawling/CAPTCHA solving, Scrapling challenge solving, raw generic CDP, or arbitrary proxy/credential headers to the public worker without new evidence and authority review.

## 12. Scale-out triggers

Reconsider a distributed frontier only after measured queue latency, SQLite contention, multi-host requirements, recovery time or supplier freshness SLOs demonstrate that the current store cannot meet demand after tuning. Crawlee is the first scale-out plugin candidate because it does not require changing VAN authority.

## 13. Acceptance gates

Repository GREEN requires migrations 31/32, acquisition/frontier/API/runtime tests, existing authority/security tests, lease-race tests, evidence-tamper tests, skill canary/fallback tests, and no credential material in acquisition state.

Runtime GREEN requires loopback-only worker, exact versions, no auth/challenge-solver surface, a real public canary, content digest, verified evidence chain, persisted readiness evidence, sanitized Browser Harness network observation, and typed retry/dead-letter failure behavior.

Production ready additionally requires representative static/SPA/infinite-scroll/account-visible qualifications, restart/reclaim and rate-limit canaries, redesign/drift recovery, golden-set extraction thresholds, resource budgets on van-trading-core, and no VATI/trading regressions.

## 14. Promotion rule

PR #76 remains draft until CI is green and the canonical owner/Hermes estate-control path installs and live-qualifies the runtime on van-trading-core. Repository code must not weaken privileged deployment controls merely to make installation easier.
