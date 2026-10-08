# VAN physical Android acceptance through Artemis

The backend target is `van-trading-core`; Hermes profile `van` and Artemis run on
`dial-control`. A separately admitted VAN HTTPS/WSS ingress must route
to the core backend and preserve its pinned end-to-end trust. The existing limited
DDS product proxy does not establish this complete VAN transport path.

The owner selected **native Artemis directly through DIAL/Commander, outside
Hermes orchestration**. Follow the [native handoff](NATIVE_ARTEMIS_HANDOFF_PROMPT.md)
using the actual discovered native schema. The S24 Ultra is USB-connected to a
Windows PC; its authorized `device` state was owner-reported, not independently
observed here. A measured private USB bridge still needs actual device admission.
No Global DIAL or Artemis tool is callable in this session. Physical tests are
deferred until wiring, deployment and release provisioning are complete.
Preparation below performs no pairing,
deployment, APK installation, phone action, provider effect or trading action.

## Existing DDS compatibility adapter

The Python `artemis_acceptance.py` invocation/import adapter is explicitly the
**legacy DDS/Hermes Android testing plane**, retained for compatibility with its
real schema. It does not implement or qualify the owner's selected native route.
The generated cases and registry functions/surfaces also supply native test goals;
native operation must use independently discovered native tools and receipts.
VAN application commands still exercise the real Hermes backend in either case.

The current DDS contract exposes `android_testing_status`, `android_diagnose`,
`android_device_state`, `android_test_run` and the asynchronous task/trace tools.
It exposes **no wireless pairing, connection or admission mutation tool**.
`android_diagnose` is not a pairing tool; probing/fixing requires an already
admitted device. An Artemis Pro objective must not bypass that boundary.

For a separately chosen wireless transport, pairing must use an existing admitted
one-use recipe and secure ephemeral code binding; a planned test grants no pairing
or host authority. For USB, follow the measured private bridge and exact serial
requirements in the native handoff. Credentials/private dialogs remain outside
objectives and retained artifacts; no public ADB listener is needed.

For the legacy DDS adapter only, call existing `android_testing_status` and require
the serial in **both** `admitted_devices` and `connected_admitted_devices`, with
Hermes control authority and admission enabled. A saved admission receipt or
Android's “wireless debugging enabled” setting alone proves neither connection
nor identity. Use `android_diagnose` with `attempt_fix:false`, `probe_device:true`
and `verify_credentials:true` only after admission, and retain current receipts.

## Prepare the source-bound plan

From the VAN repository:

```sh
python3 tools/certification/artemis_acceptance.py prepare \
  --out docs/audit/VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-07.json
```

The current registry yields **726 candidate cases**: all nine registered acceptance
states plus recovery for each of 42 capabilities (420), happy/error paths for each
of 77 source functions (154), and reachability/process restoration for all
70 surfaces (140), plus 12 explicit transport/privacy/lifecycle recovery cases.
This is planned coverage, not a claim that the frontend is
complete or that 726 device tests passed. Concrete journey fixtures, actions and
readbacks live in `artemis_scenarios.py`; expectations come from the audited
registry rather than a replacement feature list. New capabilities require an
explicit journey catalog update. Proposed screens stay proposed; missing controls
fail rather than becoming navigable test successes. Download record review/removal
is separate from actual save/upload/clipboard byte effects. Current source supplies
the byte producers and phone consumers; those cases require real bytes and exact
independent target readback. Internal browser/automation producer routes remain
service-only and never become Android calls or credentials.

The plan hashes the current registries, implementation trees and Rive assets,
Hermes MCP shim/profile registration, core deployment/compiler/preflight scripts,
gateway unit/profile configuration, preparation code and actual DDS Android
schemas. Generated receipts are excluded. Hash inclusion does not authorize any
deployment recipe. Freeze and deploy a reviewed immutable
revision, build its owner-signed APK, then regenerate the plan. Preserve both
deployment and complete input-manifest identity; a Git HEAD value alone cannot
identify an uncommitted build. Hardware attestation roots, signed provisioning
keys and device certificate trust must correspond to the deployed backend.

For an explicitly selected legacy DDS run, prepare one **actual supported**
synchronous MCP call:

```sh
python3 tools/certification/artemis_acceptance.py call \
  --plan docs/audit/VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-07.json \
  --case OF-COMMAND-001:happy --device-serial EXACT_ADMITTED_SERIAL \
  --out /tmp/van-artemis-call.json
```

This writes arguments and never invokes the tool. `--apk-path` optionally names
an already transferred, exact repository-relative APK **on the governed host**;
a cloud-workspace path is not an uploaded host artifact. It is omitted for later
cases after an independently observed installation. The payload uses only the
actual `android_test_run` fields; it does not invent pairing, fixture, request-ID,
trace-ID or verification-level arguments. Pro's strict verification is applied by
the existing synchronous broker implementation. The tool acquires its exclusive
device lease and returns terminally; run one bounded case at a time, inspect its
evidence, and stop when a prerequisite fails. Do not queue detached tasks to
simulate current-turn completion.

`run_case(call_tool, plan, case_id, bindings)` can use an existing authorized MCP
SDK's typed `call_tool` adapter. This library starts no MCP server, accepts no
remote endpoint, and performs no shell/ADB/SSH fallback. It checks current
admission, independently observed S24 hardware identity and exact safety/deployment
bindings before a single synchronous call.
Transport ambiguity produces `OUTCOME_UNKNOWN` and never restarts the task. Its
maximum tool wait follows the real schema; a controller must keep the owner
informed while an admitted call runs. If connection is unavailable, keep cases
blocked and preserve the last source-bound plan.

## Fixtures and owner privacy

Fixture names describe requirements, **not existing fixture endpoints**. Prepare
them only through a separately admitted typed acceptance recipe on isolated
services/data. Missing fixture authority is a blocker. Never take production
Hermes, gateway or provider services down for an error test. Memory erasure needs
a separate disposable owner database and exact fresh biometric A4 occurrence.
Trading changes, strategy promotions and protective halt tests need an isolated
demo sender/risk authority and demo broker account; no real order or production
halt is authorized by this suite. Google sends use a controlled acceptance
recipient/account. The owner handles biometric/OAuth interactions privately.

Offline/mobile/Wi-Fi switching can drop wireless ADB itself. Preserve a separately
governed recovery path, inspect the existing run after reconnection, and never
turn loss of device observation into a successful offline test. Voice recognition
and audible speech require actual owner-controlled microphone/audio evidence;
a text receipt cannot prove that the owner heard speech. Reboot/process-death
cases must restore concrete IDs, original outbox/session identities and visible
unknown outcomes, rather than restarting already accepted work.

## Evidence and the existing broker limitation

The current `android_test_run` sets `success:true` when its Artemis CLI exits zero.
That proves neither all assertions nor independent owner-goal verification. Its
summary includes `run_id`, source/device/objective IDs, final screenshot and
Logcat hashes. The synchronous CLI trace is **not** registered as an async
Hermes-owned `trace_id`; feeding `run_id` to `android_trace_inspect` is invalid.
Obtain per-step CLI trace artifacts using an existing authorized artifact-export
surface. If no surface exists, Oracle must add a typed export/reconciliation
recipe; without it, the case cannot qualify.

For every case retain the terminal broker summary, installed package/APK and
S24 Ultra hardware-model readback, per-step screenshot/action trace, final
screenshot/Logcat, asserted observed UI state/context, and independent backend
readback. Command/provider journeys also need actual Hermes and service receipts.
Correlate exact case, run, source/input manifest, APK and record identities. Treat
accepted/queued/running or unknown outcomes as pending, never verified success.
Error tests need independent refusal/no-effect observations, not a guessed error
from a blank page. Cancellation of the mission record does not prove a running
remote service stopped.

The local import format is a **normalization envelope**, not a claim that native
Artemis/backend schemas already contain these fields. Its `bindings` carry source,
APK, device, deployment/admission/fixture receipt references and `inputs_sha256`.
Each case carries `broker_summary`, `artifacts` (ID, kind, relative exported path,
SHA-256), assertion results and correlation IDs. Normalized backend/Hermes/service
receipts include producer, actual source receipt reference, exact identities,
independent observation and terminal postcondition. The controller must obtain
the originals through governed reads; it must never author observations from the
plan's expected values. Exported traces include action/step numbers, original
source receipt reference and screenshot digests. See the contract-test fixtures
for the envelope shape; those fixtures are intentionally synthetic and never live
qualification evidence.

For happy save/upload/clipboard cases, retain one normalized `byte_effect_readback`
with current session, target and producer epoch, original transfer receipt references,
and every declared operation's independent effect hash/length. Its `content_artifact_id`
must identify exported harmless fixture bytes (`transfer_bytes`); their actual SHA-256
must equal both `expected_sha256` and `observed_effect_sha256`. Clipboard requires
separate copy and paste evidence, each valid UTF-8 no larger than 64 KiB. The export
validator's file bound is 32 MiB; choose bounded harmless transfer fixtures accordingly.
Missing bytes, metadata-only observations, mismatched effect hashes and absent target
identity refuse consistency. This normalization still does not establish native
producer authenticity or physical qualification by itself.

```sh
python3 tools/certification/artemis_acceptance.py validate \
  --plan docs/audit/VAN_ARTEMIS_ACCEPTANCE_PLAN_2026-10-07.json \
  --receipt /tmp/governed-receipt-export.json \
  --evidence-root /tmp/governed-artifacts --out /tmp/van-validation.json
```

The validator refuses missing coverage, altered/escaping artifacts, identity
drift, unsupported controls, unknown effects and unsupported producers. It
preserves FAIL/BLOCKED/PARTIAL/OUTCOME_UNKNOWN. Even a completely consistent import
is `CONSISTENT_IMPORTED_EVIDENCE`, with `live_qualified:false` and producer
authenticity unverified. Final acceptance additionally requires fresh governed
producer readback/reconciliation and resolution of the registry's remaining
frontend gaps. Health, source tests, a successful CLI exit and preparation counts
cannot replace that final physical-device evidence.

Authoritative source references: DDS
`agent-system/orchestration/android-testing-mcp.mjs`,
`agent-system/orchestration/android-testing-plane.mjs`, and
`deploy/netcup/hermes-control/artemis/dial_artemis_mcp_bridge.py`.
