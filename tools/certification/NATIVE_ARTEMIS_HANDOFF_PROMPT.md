# Direct native Artemis acceptance on wireless ADB

The current owner instruction selects **wireless ADB**. Use Commander and/or direct
DIAL MCP to operate native Artemis on dial-control. VAN's gateway, phone mTLS ingress
and product Hermes profile van belong on van-trading-core. Oracle Admin is excluded.
DDS development readiness is not a prerequisite for this native route.

The exact handset is Samsung S24 Ultra, physical serial RFCX2054F5W, Android model
SM-S928B, application com.dial.van. Its wireless ADB transport serial is a measured
private IPv4:port, recorded separately from its physical serial. A VPN address,
a prepared plan, or enabled wireless debugging proves no pairing.

## Connection and identity

Reuse the existing owner-authorized private route and Android wireless-debugging TLS
pairing. Keep the pairing code in a secure ephemeral input; never place it in chat,
objectives, source or evidence logs. Inspect the current connection endpoint and
pairing endpoint on the phone. Do not guess ports, enable legacy plaintext ADB,
publish ADB, alter unrelated peers, or assume mDNS crosses a VPN.

Use the actual exposed Commander/DIAL contracts. Establish a private endpoint from
dial-control, directly or through a measured loopback tunnel over existing private
estate access. Keep native Artemis, adbutils, ADB subprocesses and evidence processes
on the same observed ADB server. Do not replace a shared server or copy credential
files into evidence. Reuse the provider binding in its original scope.

Before each handset task, independently run:

- adb -s <measured-private-IP:port> get-state
- adb -s <measured-private-IP:port> shell getprop ro.serialno
- adb -s <measured-private-IP:port> shell getprop ro.product.model

Require device, RFCX2054F5W and SM-S928B, with successful commands. Recheck after
connection loss, reboot or endpoint change. Never fall back to another phone.

artemis_acceptance.py prepare --native-schema <actual-schema.json> --out <plan.json>
now defaults to wireless ADB. The plan is prepared candidate coverage, not executed
acceptance. USB remains an explicitly selected alternative, with separate evidence.

For wireless native-call, pass --device-serial <measured-private-IP:port> and
--device-binding <fresh-readbacks.json>. The binding has record kind
NATIVE_WIRELESS_ADB_IDENTITY_READBACK, device transport WIRELESS_ADB, adb_serial,
authentication ANDROID_WIRELESS_DEBUGGING_TLS_PAIRED, a timezone-aware observed_at,
and a reads array containing the exact three command argv vectors, exit codes and
stdout values above. This JSON contains no pairing code. Its five-minute consistency
check grants no pairing, admission, producer authenticity or live qualification.
The actual private paired connection and fresh live readbacks remain required.

## Source, release and execution

Inspect native tool schemas from the actual installed runtime; the reviewed source
expectation is google/artemis@371aa6df56880643da57b30da936e9812fb0ec66.
Use mobile_diagnose with fixes disabled, mobile_get_device_state, mobile_run_task,
mobile_manage_task and mobile_inspect_trace as exposed. Bind the measured ADB serial,
locked_app_package=com.dial.van, model=Pro and strict verification.
Poll actual task/trace IDs to a terminal result.

Freeze reviewed source and APK identities. A successful debug build is not an owner
release. Verify the owner signer, core deployment profile, signed provisioning,
current CA/pins and hardware/session binding before installing or attributing
physical acceptance to this source. Preserve the existing phone's signing identity,
owner PKI and state. Do not add host/token/CA entry screens.

Generate the current feature/function/surface and happy/error/recovery matrix. Use
isolated fixtures and demo trading. Join native UI steps and traces to canonical
backend/product Hermes actions and independent effects. Missing controls fail;
unavailable prerequisites remain blocked. Ambiguous effects remain unknown without
resend. Network-loss cases must preserve or independently recover the wireless
control path; candidate cases are not automatically applicable.

Actual OS/biometric consent and private speaker enrollment must come from the owner.
Keep audio, embeddings, credentials and private content out of exported evidence.
Do not infer acoustic accuracy from a process exit or schema check.

Return exact source/APK hashes, physical serial, measured transport and ADB server,
native task/trace IDs, timestamps, observed assertions, effect/readback identities,
cleanup state and per-case outcomes. Keep host checks, offline consistency and
physical execution separate. A prepared invocation never increments physical cases.
