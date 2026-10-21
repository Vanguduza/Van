# VAN implementation and pre-S24 qualification — 8 October 2026

The owner-requested repository wiring is implemented for the defined native
contracts below. This report supersedes the eight missing-contract statements
in the 7 October source review. It does **not** establish that only S24 testing
remains: actual production access, trust/signing/provisioning, live services and
the governed Oracle/VEKL artifact contract remain prerequisites.

The selected backend is **van-trading-core**, with Hermes profile `van` on
**dial-control**. Later handset acceptance must use native Artemis directly
through DIAL/Commander, outside Hermes actuation. Physical S24 acceptance is
deferred as instructed. The reported USB device is RFCX2054F5W / SM_S928B on the
owner's Windows PC; it has not been independently observed by this workspace.

## Implemented functions and boundaries

| Area | Implemented owner function | Refusal and recovery behavior |
| --- | --- | --- |
| Decisions | Exact choices, evidence, revision, expiry, owner answer and immutable request readback | Stale/conflicting choices refuse; an answer records judgment rather than action approval; replay does not recreate erased memory |
| Mission controls | Durable pause/resume and direction, worker poll and adoption receipts | Fences future dispatch at the native writer boundary; preserves cancellation/revocation; resume never replays a previously refused command; running OS suspension is not claimed |
| Derived memory | Paginated exact records, screened export, dependency scope and revision-bound biometric erasure | Changed content/dependencies refuse; atomic erasure retains other records and invalidates derived caches |
| Learning | Actual owner decision patterns, counterexamples, external evidence and producer readiness | Exact case-sensitive choice IDs; canonical owner authority required; stale/malformed/unsupported observations remain unmeasured; candidate evidence never becomes owner truth automatically |
| Owner consent | Fresh A4 exact action/parameter scope, finite expiry and admission budget, revocation and readback | Native authority still required for every use; atomic canonical admission charged once; expiry/revocation rechecked under the effect transaction; uncertain reservations are not refunded into replay |
| Automation | Defined typed predicates, filters, switches, mappings, merges, preconditions, waits, native reminders and protected HTTP effects; proposal, exact admission and execution | Sealed graph/artifact/input identity and class floors; single-use fresh A4 grants; current mission fence; one external write attempt and independent target readback; unknown branches/expressions refuse |
| Browser effects | Signed preparation, immutable click/fill plans, current profile/domain/custody review and exact A4 execution | Current prepared and command Mission fences; four bounded native calls per effect for actuation plus independent observations; reply loss remains UNKNOWN; terminal plans permit observation only |
| Browser repeat work | Verified task completion and fresh preparation after explicit owner takeover | Exact completed-plan evidence closes the broader freeform goal UNVERIFIABLE; interrupted metadata recovery never repeats an effect |
| Browser files | Bounded import, static analysis, inert preview, operation recovery, phone download/upload and clipboard controls | Exact hashes/size/current session and one-use grants; quarantined content is refused; recovery reads results without retrying uncertain uploads; file-recovery metadata uses Keystore-backed encrypted preferences |
| Android integration | Current clients and controls on actual existing host screens, hardware-bound proof, fresh biometric approval and explicit unavailable/error states | No in-app host, port, key, token or CA settings; normal Android permissions/biometrics remain necessary; browser approval stays in the foreground activity |

The central command seal and action identity are immutable under serialized
writes. Duplicate admission cannot overwrite a terminal execution, consume a
second permission reservation or relabel committed revocation as submitted or
successful. Post-effect state updates use conditional writes; revocation retains
every canonical terminal outcome. Controlled concurrent tests cover these races.

## Registry for the frontend redesign

The [designer contract](OWNER_FRONTEND_CONTRACT.html) and
[registry guide](OWNER_FRONTEND_REGISTRY_GUIDE.md) describe **42 feature groups,
97 source functions, 76 screens or hosted controls, 338 endpoints and 198 schemas**.
Each implemented function includes its authority gate, actual hosting surface,
source/client binding and happy, refusal and recovery acceptance requirements.
Hosted controls do not invent navigation routes. The
[Artemis plan](VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-08.json) contains **798 candidate
cases and zero physical executions**; it cannot certify a native run by itself.

There are 37 groups classified SOURCE_WIRED_REQUIRES_ACCEPTANCE and five classified
EXTERNAL_CONTRACT_OR_ASSET_REQUIRED. The latter retain the explicit Oracle/VEKL,
production acoustic and deferred Rive/visual boundaries. A working subfunction
does not qualify an unavailable branch of the whole group. Earlier inventories
and plans remain historical; current registries are bound to the final source
manifest and Android receipt.

## Validation evidence

The [final validation receipt](VAN_PRE_S24_VALIDATION_2026-10-08.json) supplies
authoritative counts, runner selections, logs, JUnit and source hashes. Focused
overlapping tests are not added to aggregate counts. Android assembly, app/JVM
tests, lint, native ELF alignment and APK ZIP alignment are separately bound to
the final Android source. The resulting APK is a developer debug build, not a
signed owner release.

The complete local runners record **6,988 passed and four optional skips**. Two
current opt-in AGP guard checks passed separately, for **6,990 fresh passing
executions**. Two retained real PostgreSQL/DDS checks have matching current input
hashes, yielding **6,992 qualified source cases**. The four original skips remain
visible in their JUnit, and neither retained check is described as a new run.

The complete backend run passed 3,145 cases. Its global wrapper correctly records
one concurrent Android-only privacy correction. All remaining full-run inputs,
including backend/runtime/test code, retained exact bytes. Both backend modules
that read Android source were rerun against the final encrypted implementation:
16 passing overlapping cases. The
[component qualification](validation/backend-component-requalification-2026-10-08.json)
preserves the original wrapper's whole-input-stability result and does not
inflate the total. Trading/Hermes/contracts use their final current source
bindings; native services have their own imported-protocol/package manifest.

Actual opt-in AGP tests verify refusal without the deployment profile or existing
production signing identity. Retained PostgreSQL and DDS resolver supplements
have independently rechecked unchanged input hashes. Read-only OCI helper
fixtures now run without root; they do not prove the remote host's firewall.
Native browser tests use controlled TLS/CDP/WebRTC fixtures rather than a live
production Chromium host or physical handset.

## Remaining prerequisites before handset acceptance

| Prerequisite | Current evidence and prepared work |
| --- | --- |
| Production DIAL/Commander route | This session exposes no DIAL/Commander/Artemis tools, outbound identity or production credential binding. The existing admin MCP's permissions are not disputed. Repository loopback routes and a separate diagnostic URL are not an admitted live route |
| Core deployment and private services | Deployment preparation, preflight, systemd rendering, trust checks, rollback and bounded pre-phone collection are implemented. No exact-source core deployment, fresh private Hermes/service canary or live kernel/firewall qualification was executed |
| Owner release/provisioning | Existing production signer, trusted gateway profile/CA, attestation anchors and installer bindings are absent. Release guards refuse missing bindings. The app needs no in-app configuration once the actual release and signed installer payload are supplied |
| Oracle/VEKL artifacts | Strict bounded consumer and independent persisted-byte readback are implemented, but the real governed target API and canonical signed admission/introspection integration are unavailable. DDS requires an actual owner-originated Oracle job; a local archive or public research worker is not a substitute |
| Production acoustic assets | Recognition/wake/speaker assets and their release identities need actual qualification. Personalized device/acoustic measurements belong to handset acceptance; Rive/visual redesign remains separately deferred |
| Cloud configuration activation | Reusable setup is saved as a draft. Saving does not publish it or create host access, signing keys or provider admission. Review/save and publish in environment settings activates that configuration |

The [browser/provider contract](VAN_BROWSER_EFFECTS_AND_OWNER_FILES_2026-10-08.md)
records precise unsupported target requirements. The pre-phone collector is
[pre_phone_host_acceptance.py](../../tools/certification/pre_phone_host_acceptance.py);
its maximum result is PASS_HOST_HEALTH_ONLY, never full owner or handset
qualification. The subsequent native testing instructions are
[NATIVE_ARTEMIS_HANDOFF_PROMPT.md](../../tools/certification/NATIVE_ARTEMIS_HANDOFF_PROMPT.md).

All authorized changes are preserved in the workspace and an exact-base source
handoff with restoration verification is supplied under `/workspace/van-audit`.
The baseline commit alone does not contain these fixes. Nothing was deployed or
tested on the S24, and no credentials were embedded in the source or debug APK.
