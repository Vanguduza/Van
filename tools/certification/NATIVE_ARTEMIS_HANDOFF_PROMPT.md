# Prompt for a ChatGPT session with DIAL and native Artemis tools

Paste the following prompt into the tool-enabled session after the current VAN wiring
validation and registries are available. It requests later acceptance; no phone test was
run while preparing it.

---

Conduct VAN Android acceptance on my Samsung S24 Ultra using my existing administrative
DIAL MCP and native Artemis directly on dial-control. Use the available DIAL/desktop
Commander tools to reach native Artemis. Keep Artemis operation outside Hermes
orchestration. VAN application commands must still exercise its real Hermes backend.

My backend selection is van-trading-core; Hermes profile `van` runs on dial-control.
The S24 Ultra is `RFCX2054F5W`, model `SM_S928B`. Its USB cable is attached to my Windows
PC, where I reported it authorized by ADB. My Windows SSH alias is `dial-control`.
Wireless debugging was enabled but never paired. Verify fresh observations rather than
assuming any of these reported states remain current.

First inspect the actual available tools and reuse my connected account and existing
admin authority. Apply the DIAL operator skill if available. Do not ask me to enable a
connector that is already available, request credentials in chat, assume the separate
public diagnostic client represents my MCP authorization, or invent tool names.
If an actual tool policy rejects an operation, report that exact operation and stated
reason and continue the unaffected work.

Read the current checkout's `docs/audit/VAN_WIRING_CLOSURE_2026-10-07.md`, its final source
manifest and validation receipt, and these registries:

- `registries/owner_features.json`
- `registries/owner_screens.json`
- `registries/owner_endpoints.json`
- `registries/owner_endpoint_schemas.json`

Verify exact source/artifact hashes before testing. The baseline repository commit alone
does not include the uncommitted implementation patch. Never test an older installed
app and attribute it to current source. The local debug build/receipts are not a signed,
provisioned owner release. Use the release-profile, release-inspection and signed
installer provisioning tools to prepare or independently verify the actual tested app.
Do not add host, port, credential or certificate-entry screens. Confirm the app connects
from installer-supplied trust and hardware identity without owner configuration.

Establish the smallest private ADB route through existing tools. The USB transport belongs
to Windows. If it needs forwarding, use the existing SSH connection to a dedicated,
verified-free dial-control loopback port forwarding Windows `127.0.0.1:5037`. Inspect
effective SSH forwarding/listener policy and verify the actual loopback-only bind. Never
expose an ADB server publicly or replace the shared host ADB endpoint. If no Windows
execution tool exists, finish host preflight and provide only the minimal Windows command
needed to start that measured private forward. No wireless pairing is needed for USB.

Freeze one exact endpoint for every native Artemis, adbutils, ADB subprocess, install and
evidence process: `ADB_HOST`, `ADB_PORT`, `ADB_SERVER_SOCKET` and
`ARTEMIS_ADB_ENDPOINT_ID` must identify the same dedicated loopback bridge. Use a dedicated
Artemis profile and trace directory, preserving existing tasks and securely bound provider
settings. Do not change HOME or copy credential files into evidence.

Strictly verify `adb -H <host> -P <port> devices -l`, exact authorized serial, live model,
Android version, page size and package identity before any UI task. An unknown,
unauthorized, disconnected, mismatched or ambiguous device must not trigger fallback to
another phone. Keep the native Artemis source/pin and applicable DDS hardening patch;
inspect the installed tool schema/CLI before invoking it. The reviewed Artemis source pin
is `google/artemis@371aa6df56880643da57b30da936e9812fb0ec66`; its recorded path is a source
expectation, not proof of an installed executable.

Use native `mobile_diagnose` with fixes disabled, `mobile_get_device_state`,
`mobile_run_task`, `mobile_manage_task` and `mobile_inspect_trace` when exposed. For tasks,
bind `device_serial="RFCX2054F5W"`, `locked_app_package="com.dial.van"`, `model="Pro"`
and final verification. Alternatively use the discovered native CLI's standalone mode,
exact device, locked app and isolated trace path. Poll actual returned task/trace IDs and
inspect terminal traces. An accepted task, screenshot or autonomous success statement
does not establish a passed feature.

Generate the acceptance matrix from the current registry's functions, screens, authority
gates and required happy/error/recovery states. Preserve explicitly unsupported functions
as unsupported; do not turn them into passed or deployment-only cases. In particular,
custody handover does not authorize arbitrary browser mutation, and policy permission for
ANALYSE/Oracle/VEKL file actions is not an executable producer.

Exercise every applicable implemented owner function through the Android UI and real
backend. Include provisioning/renewal, Home and navigation, commands and sessions,
decisions/A4 review, missions and intervention, memory/corrections, connected providers,
projects, reminders, automation, trading views/ticket confirmation, voice/overlay,
permissions and browser video/control/pause/resume/keyboard/file-picker/upload/download/
clipboard. Join UI evidence to the actual endpoint request, canonical command/action/run
and independent effect readback. Browser tests require both isolated producers, measured
control fencing, real frames and actual bytes; backend metadata alone is insufficient.

Cover outages, malformed/error responses, lost replies, duplicate submission, background/
foreground transitions, rotation, process death, restart, transport loss/recovery, stale
frames/generations, denied/revoked permissions, expired/revoked bindings, wrong TLS trust,
approval refusal and cancellation. Check that unknown effects remain unknown and uncertain
mutations are not retried. Use isolated test records, owner-controlled recipient addresses
and demo trading data; do not place live orders, move money or send messages to third
parties. Genuine system/biometric consent must come from me when required; do not bypass it
or mark an unattended approval test as passed.

For each case, return actual source and APK hashes, serial and frozen ADB endpoint,
native trace ID, start/end timestamps, terminal native status, screenshots/hierarchy or
Logcat references, endpoint/command/action/run IDs, independent before/after observations,
cleanup state and an outcome of PASSED, FAILED, BLOCKED, UNSUPPORTED or NOT_RUN with a
concrete reason. Redact credentials, private mail content and biometric material. Keep
raw private evidence where appropriate and provide a sanitized bundle.

Bring back a JSON summary and readable report: exact tested versions, per-feature/state
results, coverage gaps, reproducible failures, real evidence references and remaining
deployment/device requirements. Separate local fixtures, host checks and physical phone
results. Do not convert earlier Hermes-produced or candidate-plan receipts into native
Artemis execution evidence.
