# Expert review — VAN Remote Browser Production Blueprint Rev 1

**Status:** Review. Not an authority document; it does not amend Rev 1, `docs/SECURITY_POLICY.md`, `docs/PROJECT_TRUTH_PROTOCOL.md`, `PROJECT_CANONICAL_STATE.json`, `config/browser/profiles.yaml`, or any other locked authority.
**Reviewed document:** `VAN_REMOTE_BROWSER_PRODUCTION_BLUEPRINT_REV_1.md` (Rev 1, 47 sections, 3389 lines), supplied by the owner.
**Repository state considered:** `main` @ `0b0efad` (`0.5.0-dev`), schema version 16.
**Reviewed at:** 2026-09-19.

## Verdict

Rev 1 states its baseline correctly — `0b0efad0e63600a2f55597e448cd37b359d475a1`, version `0.5.0-dev` — and its
account of the existing Browser Fabric is accurate: `BrowserTask`, `BrowserTaskStatus`, `BrowserStrategy`,
`AutonomyTier`, `PageLease`, `BrowserEvidence`, `BrowserObservation`, `BrowserSessionBroker`, `BrowserTaskService`
and `BrowserPolicyEngine` all exist where the document says they do. Its summary of
`PROJECT_CANONICAL_STATE.json` is faithful. After the Rev 1.2 review had to open with a baseline that named a
branch which did not exist, that is worth saying first.

The architecture is also right. The three-plane split — Android owns presence and touch, Hermes/Gateway own
authority, Oracle owns web execution — with the explicit rule that **Hermes, the Gateway and Stagehand are all
outside the pixel loop**, is the correct design for this product. ADR-RB-006's separation of the *profile* lease
from a new *control* lease is the single best idea in the document: it names two genuinely different exclusivity
problems that a lesser blueprint would have collapsed into one. §5.3's `control_generation` on every input packet,
enforced server-side, with §22.3's explicit note that *"a UI-only 'Take over' button without server
control-generation invalidation is not sufficient"*, is the difference between a demo and a product.

The problems are not architectural. They are that **the deployment target named in §25.1 cannot run this system
and cannot be reached by the phone**, and that four of the repository contracts Rev 1 says it will extend do not
have the shape Rev 1 assumes. Five findings are blocking. All are fixable inside the document, but B1 and B2
change the infrastructure plan, which under
`PROJECT_CANONICAL_STATE.json → policy.agent_self_authorization_forbidden` is an owner decision.

---

## Blocking findings

### B1 — The phone cannot reach the host §25.1 puts the runtime on

`deploy/van-trading-core/README.md:3-4` describes the target VM as:

```text
private IP 10.0.1.233, subnet 10.0.1.0/24,
SSH + control port 9133 admitted only from 10.0.0.0/16
```

`van-trading-core` has no public address, and its security list admits only the internal VCN. Its entire posture
is "no public ingress; `dial-hermes-control` is the only peer." Against that:

- **ADR-RB-002** makes `S24 ⇄ direct UDP/ICE ⇄ Browser Stream Gateway` the *preferred* transport;
- **§15.3** requires a bounded public UDP media range and HTTPS/WSS signalling ingress on the runtime;
- **§25.1** places `van-browser-streamd`, the Chromium session, the encoder *and coturn* on this VM.

No ICE candidate pair can form. The direct path is impossible, and the TURN fallback is impossible for the same
reason — a relay on a private subnet relays nothing. §15.2's "TURN SHALL be in the same OCI region" is satisfied
by a host the client cannot address.

There are only three honest resolutions, and Rev 1 must pick one as an owner decision rather than leave it to an
implementation agent:

1. Give `van-trading-core` a public IP and open a UDP media range — which punches public ingress into the host
   running `vati-commander`, `vati-vekl`, `vati-supabase` and the broker PKI. This contradicts §25.2's isolation
   intent and §31.6's VATI containment, and should be rejected.
2. Put signalling and TURN on a separate public-facing host and relay media inward — which adds a hop and
   forfeits ADR-RB-002's "direct first" latency premise, so §26's budget must be restated.
3. Stand up a dedicated, public-facing streaming host — i.e. §25.3's "promotion gate" is a **Phase 0 decision**,
   not a Phase-9 discovery.

(3) is the only option that preserves both the security boundary and the latency argument. See B2 for why it is
also forced on compute grounds.

### B2 — The compute budget and the placement contradict each other

The same VM is `VM.Standard.A1.Flex, 2 OCPU / 12 GB, Ubuntu 24.04 ARM64` (`deploy/van-trading-core/README.md:3`,
`bootstrap.sh:3`). Ampere Altra exposes **no hardware video encoder** — no NVENC, no QSV, no VA-API. So §14.2's
profile is x264 software encode, on two ARM cores, and §25.1 asks those two cores to simultaneously run:

- Chromium rendering a 1080p viewport at 60 FPS;
- full-frame capture at 60 Hz (see S8);
- x264 `tune=zerolatency` 1080p60;
- coturn;
- the existing Stagehand and Playwright/Browser Harness runtimes;
- and, per §25.2, without starving `vati-commander`, `vati-session@<alias>` and `vati-supabase` (PostgreSQL 17)
  on the same box.

1080p60 zerolatency x264 is on its own roughly 1.5–3 modern cores. §26's `server encode <12 ms p95` and
`server capture <5 ms p95` are not reachable here, and §25.2's "MUST NOT starve VATI" is not a tuning constraint
on this shape — it is a contradiction with §14.1's target.

§25.3 already lists the right promotion triggers (`encode p95 > 15 ms`, `CPU > 80%`, `Hermes/VATI latency
materially regresses`), and §42.6 correctly forbids lowering the gate to make it pass. The defect is that Rev 1
presents §25.1 as the plan of record and §25.3 as a contingency, when the measurement it mandates has a
predictable outcome. Required correction: state the honest Phase-1 target for the A1 as a **path proof only**
(e.g. 720p at 30–45 FPS, measured, explicitly not the product target), and move the dedicated-host decision
into Phase 0 alongside B1, so one infrastructure decision resolves both.

### B3 — Every profile alias in the document would be refused by the policy engine

`config/browser/profiles.yaml` declares exactly two aliases:

```yaml
profiles:
  public_research: ...
  authenticated_owner: ...
runtime:
  profile_root: /var/lib/van-trading/browser/profiles
```

Rev 1 uses `owner-personal` in §5.4, §6.1 and §6.3, and §13.3 invents five more —
`owner-personal`, `dial-development`, `research`, `trading-readonly`, `automation` — at a **relocated** root,
`/var/lib/van-browser/profiles/`.

`BrowserSessionBroker.register_profile` calls `BrowserPolicyEngine.check_profile` (`browser/service.py:52`,
`browser/policy.py`), which raises `BrowserPolicyError` on an alias absent from `profiles.yaml`. §6.2 step 4
therefore fails on the first request the blueprint describes, and every JSON example in §5.4/§6 is invalid.

This also contradicts Rev 1's own rules: ADR-RB-009 assigns browser profiles to `BrowserSessionBroker`, and §33
says *"Existing profile/domain files remain the policy authorities."* Either use the two aliases that exist, or
add an owner-signed amendment to `profiles.yaml` as a Phase 0 artifact — and in either case drop the invented
`/var/lib/van-browser/` root, which silently forks `runtime.profile_root`.

### B4 — A profile lease cannot hold an interactive session, and expires in five minutes

`PageLease` (`browser/models.py:157-164`) requires a non-optional `task_id`. `BrowserSessionBroker` exposes
`acquire_lease` and `release_lease` only, with `DEFAULT_LEASE_SECONDS = 300`. **There is no renew, extend or
heartbeat method anywhere in the repository.**

So §6.2 step 5 — "acquire existing profile lease" — buys a five-minute browsing session, after which the profile
becomes acquirable by any competing browser task while the owner is still scrolling a page. §29.5's reassurance
that under a Hermes outage manual browsing "MAY continue for the lifetime of the existing bounded session lease"
means five minutes, which is not what it reads as.

Separately, `InteractiveBrowserSession.profile_lease_id` (§5.1) has no valid `task_id` to supply. The two ways
out are (a) make `PageLease.task_id` optional and add a `holder_kind` discriminator, or (b) mint a synthetic
`BrowserTask` per session — which §5 explicitly forbids (*"Do not overload `BrowserTask` with interactive-session
lifecycle"*). Rev 1 must choose (a) and additionally specify:

- a renewal API driven by `last_client_seen_at_ms`;
- the renewal interval and the grace period;
- what happens when renewal fails while frames are still flowing (the answer must be: stop accepting owner input
  and enter a degraded state, not keep streaming a profile the session no longer holds).

This belongs in §5 and in the Phase 2 exit gate, and `test_interactive_profile_leasing.py` in §36.1 should assert
the expiry-mid-session case specifically.

### B5 — §20 claims the existing event store can carry the realtime envelope; it cannot

The existing table (`storage/db.py:92-98`) is:

```sql
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at_unix INTEGER NOT NULL
);
```

Against §20.1's envelope and §20.2's delivery semantics:

| Rev 1 requires | Repository has |
|---|---|
| `event_id`, used to dedupe | no such column |
| `mission_id`, `command_id`, `correlation_id` as envelope fields | payload-only, unindexed |
| `occurred_at_ms` | `created_at_unix`, seconds |
| "monotonic **per-device** sequence" | a **global** `seq` |
| replay from the existing store | `EventBus.replay` filters on `seq >` alone and is **not device-scoped** (`events/bus.py:23-26`) — every device replays every event |

§5.5's migration list contains only `browser_*` tables, so the envelope has nowhere to live, and §20.2's
"duplicates are ignored by `event_id`/`seq`" depends on a column that does not exist. §5.5 also says *"Add a
single semantic migration"* while the repository's convention is a numbered entry in `MIGRATIONS` against
`SCHEMA_VERSION = 16` — say 17, explicitly.

Pick one and write it down: either degrade §20.1 to the existing shape (envelope fields live inside `payload`,
`seq` stays global, dedupe keys on `seq`), or add the `events` extension and per-device scoping to §5.5's
migration and to Phase 5's exit gate. The current text asserts a contract the store does not provide, which is
precisely the `BUILT_UNWIRED` class of gap §0 and §40 exist to prevent.

---

## Significant findings

These do not block Phase 0, but each must be closed before the phase that depends on it.

### S1 — The two-channel input split is not orderable as specified (blocks Phase 3)

§7.3 puts pointer MOVE on an unordered, zero-retransmit channel; §7.4 puts DOWN and UP on a reliable ordered
channel. These are separate SCTP streams, and **SCTP guarantees no ordering between streams**. Therefore:

- a MOVE can arrive before its DOWN, or after its UP;
- a retransmitted DOWN can land after several MOVEs for the same pointer;
- §8.2's invariant `DOWN -> MOVE* -> UP/CANCEL` is not enforceable from arrival order.

§8.3's discard rule only covers MOVE-versus-MOVE. §8.2's healing mechanism — "sequence gap detection" — also
misfires: if `input_seq` is a single space shared across both channels, every legitimately dropped unreliable
MOVE reads as a gap, so gap detection fires continuously during normal scrolling.

Required correction in §8: a per-pointer server-side state machine that buffers or drops MOVEs falling outside an
open DOWN..UP window, and either a per-channel sequence space or a rule that gap detection applies to the
reliable channel only. Add a contract test to §36.2 for reordered cross-channel delivery — §38 item 35 ("packet
reordering") currently implies this but does not name the cross-channel case.

### S2 — §23 references a `BrowserTask.mission_id` that does not exist (blocks Phase 7)

`BrowserTask` carries `command_id`, `execution_id` and `capability_id` only (`browser/models.py:133-155`), and
`browser_tasks` has no `mission_id` column (`storage/db.py:560`). Mission binding is a *request-time* field on
the browser task API (`browser/api.py:74`, `810-827`) that calls `MissionBinder` to create an Activity
*reference* — `mission/binding.py` is deliberate about this: *"binding is a reference, not a move."*

The §23 requirement is satisfiable and the existing design is the right one, but `InteractiveBrowserSession.mission_id`
needs its **own** binder path; `bind_browser_task` will not accept a session. Name that path in §23 and add it to
§41 as a distinct work item, otherwise RB-037 will be closed by binding the child task and leaving the session
itself absent from Mission Activity — the "manual backfill" §23 forbids.

### S3 — The grant signing key has no lifecycle (blocks Phase 2)

§5.4 prefers an Ed25519 gateway signing key with the runtime holding only a public verifier. The repository's
existing asymmetric scheme is **EC/ECDSA P-256**, device public keys in PEM verified at
`approval/service.py:184-194`. A second algorithm family is acceptable — this is a gateway→runtime key, not a
device→gateway one — but must be justified rather than asserted.

More importantly, §5.4 and §31.1 rest entirely on that key and Rev 1 never specifies its generation, storage,
**distribution to a host on a different subnet**, or rotation. Add key provisioning to Phase 0 and to
`registries/remote_browser_dependencies.json`, and add "grant signed by a rotated key is rejected" to §38.

### S4 — Cellular data cost is absent from a phone product (blocks Phase 4)

§14.1's operating range of 4–12 Mbps is 1.8–5.4 GB per hour. §27's quality ladder is driven only by RTT, jitter,
loss, bitrate, encode time, CPU and frame rate — nothing keys off `ConnectivityManager.isActiveNetworkMetered`.
§3.1 covers "network handoff/reconnect" but no data-saver state, and §30's degraded vocabulary has no
`BROWSER_METERED_NETWORK`.

Add a metered-network cap to §27 and an owner-visible session data counter. Without it Rev 1 is a Wi-Fi-only
product no matter how good the latency is, and the owner discovers that through a phone bill rather than through
the UI.

### S5 — Two new Android dependencies are unnamed, and one of them is not a simple Maven coordinate (blocks Phase 3)

`android/app/build.gradle.kts` has **no HTTP client and no WebSocket library**: `VanGatewayClient` is built on
`HttpURLConnection` (`VanGatewayClient.kt:14`, `167`, `479`). §20's `WSS /v1/realtime` therefore needs a new
WebSocket dependency, and §9 needs a WebRTC one.

§32 lists "WebRTC Android source/artifact revision" generically. That understates the decision: Google's
`org.webrtc:google-webrtc` Maven artifact has been unpublished for years, so this is a build-from-source or
community-fork choice with licence, digest and reproducibility consequences — and it also determines whether
H.264 is available at all on the client, since H.264 on Android WebRTC depends on MediaCodec hardware support
rather than a bundled software codec. On the S24 the hardware decoder exists, but ADR-RB-003's "H.264 first"
should state that dependency explicitly.

Both dependencies belong in `registries/remote_browser_dependencies.json` at Phase 0, per §32's own "do not use
floating latest", and §42.1's repository-first checklist should name them.

### S6 — Phase 7 depends on an adoption decision that is still `PENDING_OWNER`

`docs/project-state/AUTOMATION_BROWSER_FABRIC_PREFLIGHT.md:156` records
`docs/decisions/VAN-ADOPT-STAGEHAND-001.yaml` as `PENDING_OWNER`, and the same preflight is explicit that the
browser runtimes are not installed or started. §16 correctly requires a *new* owner decision for
`OWNER_INTERACTIVE_BROWSER`; §35 Phase 0 should additionally list the unblocking of the existing Stagehand
decision as a Phase 7 entry condition, rather than reaching Phase 7 and finding the dependency unsigned.

### S7 — §8.1 and §12.2 leave a normative choice unmade (blocks Phase 3)

§8.1: packets with an old `viewport_revision` are *"rejected or transformed only if the transformation is
deterministic."* §12.2: input for an unacknowledged viewport is *"withheld or transformed deterministically."*
A normative document must pick one. Recommend **reject and withhold**: a deterministic transform across a
Chromium reflow is not actually available, and §12.2's own 150 ms debounce already accepts a brief input pause
during rotation. Say so, and make the client hold input until `viewport.ack(revision)`.

### S8 — The capture mechanism is the largest unbudgeted cost and is specified as a shrug (blocks Phase 1)

ADR-RB-004 and §13 say "X11 or Wayland capture" without choosing. `ximagesrc` at 1080p60 is a full-frame CPU
copy — on the order of 500 MB/s of memory bandwidth — and will not meet §26's `capture <5 ms p95` on a GPU-less
two-core ARM box. The low-cost Linux route is DMA-BUF/PipeWire portal capture, which needs a Wayland compositor,
and nothing in `deploy/van-trading-core/` currently installs a display server at all
(`browser/` contains only `bootstrap-browser-runtime.sh`, `package.json`, `package-lock.json`,
`runtime.env.example`).

Phase 1's exit gate should name the display server and the capture element, and measure capture **separately**
from encode. Rolling the two into one "server-side" number is how a capture regression hides behind an encoder
tuning claim.

### S9 — The canary pages and the SSRF boundary are in direct conflict

§36.5 hosts deterministic canaries "on the runtime". §15.4 blocks `127.0.0.0/8` and "localhost aliases", and §38
item 13 red-teams "navigation to localhost". As written, the test fixtures are unreachable by the mechanism the
test suite is meant to prove. State how canaries are served — a distinct VCN-private origin with its own
allowlist entry is the clean answer — so the SSRF boundary is not quietly widened to make CI pass.

### S10 — Minor: §11.1 conflates touch sampling with display rate

"60 Hz MotionEvent sampling where device/display permits" — the S24 samples touch well above 60 Hz and batches
into `MotionEvent` history. Capping the *send* rate at one coalesced packet per display frame is correct
(§8.3 already says this); discarding the batched historical samples is not, because fling velocity in §11.1 is
computed from them. Reword to: coalesce per frame, retain historical samples for velocity.

### S11 — Minor: declare matrix schema compatibility

§33 adds `docs/project-state/REMOTE_BROWSER_IMPLEMENTATION_MATRIX.json` while
`docs/project-state/UNIFIED_INTELLIGENCE_IMPLEMENTATION_MATRIX.json` already uses
`"schema": "van-implementation-matrix/1"`. A second matrix for a separate mission is reasonable, but §40 should
declare it as that same schema with the nine-state booleans as an extension, or ADR-RB-009's "no third source of
truth" starts to apply to the matrices themselves.

---

## What Rev 1 gets right

These are not filler; they are the parts an implementation agent should not be allowed to weaken.

**§0's nine states and §40's matrix statuses.** `BUILT_UNWIRED` as a first-class status, and the refusal to let
an agent collapse the ladder into `DONE`, is the correct response to the repository's own history. §41's fifty
tracked items with "no item can disappear because an implementation agent chooses to defer it silently" is the
enforcement clause that makes it real.

**ADR-RB-006.** Separating the profile lease from the control lease is the load-bearing insight. Profile
exclusivity and actuation authority are different problems with different lifetimes, and conflating them is how
the owner ends up locked out of their own session.

**§5.3 and §22.3 together.** `control_generation` on every input packet, validated server-side, with stale
generations rejected, is what makes §22.3's preemption a security property rather than a UI affordance. The
sentence *"A UI-only 'Take over' button without server control-generation invalidation is not sufficient"*
should survive into the implementation verbatim.

**ADR-RB-008.** Durable state changes go in the ledger, pixels and cursor motion do not. §20.2's
"high-frequency input/video does not enter this channel" repeats it at the right place. On a SQLite store this is
not a stylistic preference — it is what keeps the ledger writable.

**§8.1's normalized coordinates with viewport revisions.** Correct, and correctly motivated by rotation,
system-bar changes and dynamic resize rather than by abstraction for its own sake.

**§21.2's `BrowserContextRef`.** Sending a reference and resolving DOM/accessibility tree server-side, instead of
shipping a page dump from the phone, is right on latency, on cost and on §31.4's trust boundary simultaneously.

**§31.4.** Manual owner browsing does not make page instructions trusted. The existing `InjectionAssessment`
stays active and `source_trust = UNTRUSTED_EXTERNAL` holds. This is the rule most likely to be eroded by "but the
owner typed the URL themselves", and Rev 1 states it plainly.

**§39.** *"CI SHALL NOT claim the real Oracle/WebRTC/S24 gate is green"*, with a fail-closed test asserting
readiness is not `READY` without live evidence. That is `PROJECT_CANONICAL_STATE.json → policy.ci_is_not_project_truth_authority`
stated back accurately.

**§42.6.** "Do not thin requirements to make tests pass", with the 1080p60 encoding case named explicitly. B2
above is exactly the situation that clause exists for; Rev 1 anticipated it, and then §25.1 undercut it.

**§35's phase order.** Proving the Oracle media path in Phase 1, before any Android code, is the right dependency
order — and it is the thing that would have surfaced B1 and B2 in week one. The order is sound; only the target
host is wrong.

---

## Recommended disposition

1. Resolve B1 and B2 as a **single owner infrastructure decision** in Phase 0 — a dedicated, public-facing
   streaming host, with `van-trading-core` left private and unchanged. Restate §14.1 and §26 against the chosen
   shape. Do not start Phase 1 against the A1 except as an explicitly-labelled path proof.
2. Close B3, B4 and B5 inside the document before Phase 2: real profile aliases, a lease model that can hold a
   long session, and an event contract that matches the store or a migration that changes the store.
3. Fix S1 and S7 before Phase 3; S5 and S8 before their phases' exit gates; S2, S3, S4, S6 before Phases 7, 2, 4
   and 7 respectively.
4. Leave §0, §5.3, §22.3, ADR-RB-006, ADR-RB-008, §31.4, §39 and §42 untouched.

Rev 1 is a better document than its deployment section. Every blocking finding is closable inside the blueprint
plus one owner decision, and none of them requires re-architecting.
