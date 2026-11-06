# VAN physical Android acceptance through native Artemis

The current source contract is **CORE_ONLY_V2**. VAN gateway, direct phone mTLS
HTTPS/WSS ingress, product Hermes profile `van` and owner-runtime MCP belong on
`van-trading-core`. Direct Artemis and development access belong on `dial-control`.
Oracle Admin is excluded from this runtime topology. The profile compiler,
release validator and native plan declare these roles; that declaration does not
prove current host deployment, network admission or release provisioning.

The owner-selected test route is **native Artemis directly through Commander/DIAL,
outside Hermes engineering orchestration**, using private wireless ADB. Product
commands still exercise the real product Hermes runtime on core. Follow the
[native handoff](NATIVE_ARTEMIS_HANDOFF_PROMPT.md). DDS development readiness is not
a prerequisite for this route. The legacy DDS/Hermes Android adapter is a separate
compatibility route, described at the end of this document.

## Prerequisites and connection

Use the exact S24 Ultra physical serial `RFCX2054F5W`, model `SM-S928B`, and package
`com.dial.van`. Its wireless transport serial is the separately measured private
IPv4:port; a physical serial is not a wireless endpoint. Reuse Android's paired TLS
wireless-debugging connection and existing private access. A previously reported
USB `device` state, an old connection port, VPN address, enabled debugging, or a
prepared plan does not establish a currently connected phone.

Read the actual exposed native schemas and runtime identity through Commander/DIAL.
Reuse existing pairing identities. Keep any required pairing code in secure ephemeral
input; never paste it into chat, objectives, files or retained evidence. Do not expose
public ADB, switch to legacy plaintext ADB, reset a shared server, or select another
handset. Native Artemis, adbutils and ADB subprocesses must use the same observed
server and connection. USB/private bridging remains an explicitly selected alternative
with separate identity and applicability evidence.

Before each native task, independently read through the selected private endpoint:

- `adb -s <measured-private-IP:port> get-state`: `device`;
- `adb -s <measured-private-IP:port> shell getprop ro.serialno`: `RFCX2054F5W`;
- `adb -s <measured-private-IP:port> shell getprop ro.product.model`: `SM-S928B`.

Require the raw `ro.product.model` value `SM-S928B`. The sanitized `SM_S928B`
descriptor shown by `adb devices -l` is not a model readback and must not replace it.
Other S24 variants do not satisfy this exact admission.

Recheck after connection loss, reboot or endpoint change. Preserve the installed phone's
state and signing identity. Before handset acceptance, independently qualify the exact
core source/deployment, direct public TLS route and CA/SAN, authentication/refusals,
local product Hermes, provider contracts, persisted owner state, existing owner APK
signer and signed provisioning packet. A debug APK or declared profile is insufficient.
The app obtains route and trust through the signed release and authorized installer;
add no host, port, token, CA or model configuration screens.

## Prepare the current source-bound matrix

Export the **actual** native MCP schema discovery and runtime root to a non-secret
schema file, then run from the exact reviewed VAN checkout:

```sh
python3 tools/certification/artemis_acceptance.py prepare \
  --native-schema /tmp/actual-native-artemis-schema.json \
  --out /tmp/van-native-artemis-plan.json
```

The current registry yields **826 candidate cases**: nine acceptance states plus
recovery for each of 42 owner features (420), happy/error paths for each of 105
source functions (210) plus their 28 explicit function-recovery contracts,
reachability/process restoration for 78 surfaces (156), and 12 cross-cutting
transport/privacy/lifecycle recovery journeys. Concrete fixtures,
actions and readbacks are in `artemis_scenarios.py`; these are required contracts,
not existing fixture endpoints or executed results. A synthetic schema used in a
source test is not actual native discovery. Current physical cases remain **0/826**
until real handset evidence is produced.

The native plan must name backend and Hermes `van-trading-core`, Artemis
`dial-control`, exact handset identity, `WIRELESS_ADB`, and no `hermes_and_artemis`
field. It has no DDS schema dependency. Missing frontend controls fail; unavailable
prerequisites remain blocked. Proposed surfaces never become navigation successes.
Preserve each source/input manifest and deployed revision. A Git HEAD alone does
not identify an uncommitted build. Regenerate the plan whenever cited implementation,
registry, deployment/release inputs or actual schema identity changes.

For one supported native case, prepare arguments with fresh wireless identity
readbacks in the format documented by the native handoff. Set
`VAN_ACCEPTANCE_ADB_ENDPOINT` to the independently measured private transport endpoint:

```sh
python3 tools/certification/artemis_acceptance.py native-call \
  --plan /tmp/van-native-artemis-plan.json \
  --native-schema /tmp/actual-native-artemis-schema.json \
  --case OF-HOME-001:happy --device-serial "$VAN_ACCEPTANCE_ADB_ENDPOINT" \
  --device-binding /tmp/fresh-wireless-readbacks.json \
  --out /tmp/van-native-call.json
```

This only prepares arguments; it performs no tool call, pairing, installation,
phone action, provider write or trading action. Use the actual `mobile_run_task`,
`mobile_manage_task`, `mobile_inspect_trace`, `mobile_get_device_state` and
`mobile_diagnose` schemas. Keep fixes disabled for diagnosis unless separately
admitted. Bind the measured transport, locked package, `model=Pro` and strict
verification only when those fields are actually supported. Poll the returned task
and trace identities to terminal results; do not guess or interchange IDs. Native
plans cannot be dispatched or imported through the legacy DDS adapter.

## Fixtures, recovery and owner privacy

Prepare bounded isolated fixtures through the existing admitted route. Never stop
production Hermes, gateway or provider services to create an error state. Memory
erasure uses disposable owner data and exact fresh biometric A4 consent. Trading,
strategy-promotion and protective-halt tests need isolated demo authority and a demo
broker; this suite grants no real trading authority. Google send cases use a controlled
acceptance recipient/account. The owner handles OS, biometric and OAuth dialogs privately.

Network switching can drop wireless ADB. Recover the original task and independently
recheck the physical identity before continuing; observation loss is not a successful
offline test. Process-death/reboot cases preserve concrete outbox/session/request IDs
and visible unknown outcomes. Do not repeat an uncertain external write. Mission
cancellation or a local fence does not prove a remote OS process stopped.

Save/upload/clipboard cases require actual harmless fixture bytes, exact session,
target, producer identity/epoch and independent effect SHA-256/length. Metadata-only
readback does not prove an effect. Provider UNKNOWN remains UNKNOWN after read-only
receipt observation; missing evidence does not prove absence or clear replacement
fences. Native browser/automation producers and attested provider claim/introspection
routes remain service-only and never become Android credentials or owner endpoints.

Voice recognition and audible speech require actual microphone/audio observations;
text or process exit cannot prove acoustic accuracy or heard speech. Private speaker
enrollment and erasure need dedicated native consent and local encrypted-profile
readbacks bound to installed APK, hardware keys and model. Keep raw audio, embeddings,
credentials and private content out of exported artifacts.

## Evidence and qualification

Retain native task/trace IDs, per-step action/screenshot traces, final screenshot,
Logcat, timestamps, installed package/APK and signer readback, physical and transport
identity, declared source/input manifests, observed assertions, and independent
backend/product Hermes/provider effects. Join exact case, action, run, request,
record and effect IDs. A zero process exit, `success:true`, prepared plan, health
response or offline evidence consistency check is insufficient for acceptance.

Refusal tests need actual refusal and independent no-effect observations. Preserve
FAIL, BLOCKED, PARTIAL and OUTCOME_UNKNOWN. Obtain original producer receipts and
trace artifacts through supported reads; never author observations from expected
values. Exported artifacts must be bounded, hash-verified and free of secrets. Final
qualification requires current producer readback and actual handset observations;
local source/contract tests never increment physical coverage.

## Legacy DDS compatibility route

`artemis_acceptance.py call`, `run_case` and `validate` retain the separately selected
legacy DDS/Hermes Android testing-plane contract. They neither implement nor qualify
native operation. That route requires its own actual `android_testing_status`,
`android_diagnose`, `android_device_state`, `android_test_run`, admission and device
connection evidence. `android_diagnose` is not a pairing tool. Its synchronous
`run_id` is not a Hermes-owned async `trace_id`, and process success is not owner-goal
verification. Offline normalized imports remain `CONSISTENT_IMPORTED_EVIDENCE`,
with `live_qualified:false`; original producer reconciliation is still required.

Its authoritative source references are DDS
`agent-system/orchestration/android-testing-mcp.mjs`,
`agent-system/orchestration/android-testing-plane.mjs`, and
`deploy/netcup/hermes-control/artemis/dial_artemis_mcp_bridge.py`.
