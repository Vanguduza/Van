Resume VAN live acceptance through the actual connected DIAL MCP and Commander, using native Artemis directly on dial-control outside Hermes engineering orchestration. Work from **Vanguduza/Van exact clean application SHA `dfc1557ab99ad8d41cf84714e1bb671e89b045e6`** and verify the actual branch/object identity. Read the attached machine handoff, R7 source review and the original qualification report. The handoff preserves every earlier source/diagnostic receipt and grants no admission or live PASS.

CORE_ONLY_V2 places gateway, product Hermes profile `van` and direct phone mTLS HTTPS/WSS ingress on **van-trading-core**. Direct native Artemis/development runs on **dial-control**. Oracle Admin is excluded. The release/installer supplies Android route and trust; the owner enters no host, token, CA or model configuration in the app.

The current registry supplies **42 feature groups, 105 source functions, 78 surfaces, 432 endpoints and 251 schema components**. Its native candidate matrix contains **826 cases**: 420 feature states/recovery, 238 function cases (210 happy/error plus 28 explicit recovery), 156 surface cases and 12 cross-cutting cases. **Physical execution is 0/826.** Source fixtures and imported consistency checks are not actual native discovery or handset evidence.

Local qualification is supplied in `VAN_FINAL_QUALIFICATION_REVIEW_dfc1557a_2026-10-09.json` (SHA256 `6e4dc2a139281816ba4cdd196e7b8cf4e6494474b04f20d480c24c3bc281d104`). Use the report's exact per-suite execution/input scopes and retained failure/skip diagnostics; no overlap is summed and no prior whole-suite result is relabelled. This runtime child corrects Chromium encoded-dot scope semantics and fresh direct CDP ownership for pseudo-element geometry. Source checks and debug build results do not establish production signing, host/provider/kernel readiness or phone acceptance.

1. Discover the real DIAL/Commander/native schemas and actual owner execution route. Recover this exact source object. Locate existing protected production file paths read-only through the actual hosts before asking the owner. Preserve PKI, owner data, installed signer/state, pairing identities, sibling MCP entries, browser profiles and trading. Credentials and pairing codes remain protected ephemeral inputs, outside chat and exported artifacts.

2. Close the repository admission gates. Reuse an independently verified exact owner framework adoption if one already exists. Otherwise [PR94](https://github.com/Vanguduza/Van/pull/94), exact `296d647d8755b6036ddb6bc66a5526b78db07029`, is the separate framework-only first-adoption proposal. Quote and link [tools/ci/README.md:162](https://github.com/Vanguduza/Van/blob/296d647d8755b6036ddb6bc66a5526b78db07029/tools/ci/README.md#L162) if confirmation is needed. Framework adoption is not blanket approval of the 28 records or application history. Perform separate trusted application authorization intake/merge/deployment admission using the actual trusted-base checker; preserve uncovered findings and unchanged enforcement baselines.

3. Bind the existing production keystore/alias/signer, device CA/owner records, connectivity signing/public verification anchors, protected CORE_ONLY_V2 profile, genuine scoped ingress/deployment authority, database/encryption keys, local Hermes runtime/profile and per-profile browser state. Produce backups/rollback and an independently qualified deployment. Verify dedicated public IPv4 TLS HTTPS/WSS CA/SAN and no-client-certificate/auth/scope refusals, actual VNIC NSG/security-list/routing and ordered native firewall/IPv6 evidence, local product Hermes/session/browser/automation effects, both browser profile proxy/UID/kernel fences, and each required hosted provider's real admission/readback/refusal canaries. Unbound providers remain BLOCKED. Uncertain effects retain their original identity without resend. Trading stays demo-only and NEVER_ROUTABLE.

4. Build and verify the genuine owner-signed arm64 release APK/packet at this selected SHA, including embedded source, gateway route, CA/key anchors and actual signer identity. Follow `tools/release/README.md`. A merge that changes the accepted SHA requires a corresponding exact-source rebuild; retain prior APKs as historical.

5. Join actual original G0-G4 receipts at matching source/APK/config/profile/host identities into **PRE_PHONE_PASS**. `LOCAL_PREFLIGHT_PASS`, gateway GREEN, compiler PREPARED_NOT_DEPLOYED, packet validity and `PASS_HOST_HEALTH_ONLY` are subsets; the host collector keeps `device_provisioning_permitted=false`. **No handset installation, provisioning, launch, interaction, profile enrollment or audio capture until the full non-phone gate passes.** Continue independent read-only work while any dependent gate is blocked and report its exact missing binding.

6. After PRE_PHONE_PASS, refresh the current private paired TLS wireless ADB endpoint. The historical `10.66.66.2:35749` was refused and is stale. Use the same actual ADB server for Artemis, adbutils and subprocesses. Preserve original stdout and require fresh `get-state=device`, raw `ro.serialno=RFCX2054F5W` and raw `ro.product.model=SM-S928B`; the sanitized `SM_S928B` descriptor is insufficient. Recheck after reboot/network/endpoint changes. Preserve installed signer/state, provision the real signed packet and independently observe SESSION_ADMITTED.

7. Export actual installed native schemas and runtime root; regenerate the exact-source matrix using exposed mobile_run_task, mobile_manage_task, mobile_inspect_trace, mobile_get_device_state and mobile_diagnose contracts. Diagnosis fixes stay disabled unless separately admitted. Native-call preparation grants no execution/admission and native plans cannot dispatch through the legacy DDS/Hermes adapter. Execute all 826 happy/refusal/error/recovery cases with independent bounded effects: consent/permissions, network loss, process death/reboot, request recovery, resident deep links, browser scope/CDP ownership, voice/acoustics and private speaker enrollment/erasure. The owner privately handles OS/OAuth/biometric/audio consent. Missing controls FAIL; unavailable prerequisites BLOCKED; ambiguous or unobserved effects remain UNKNOWN.

Return PASS/FAIL/BLOCKED/PARTIAL/OUTCOME_UNKNOWN totals with physical execution separate, plus original redacted bounded independently collected artifacts: exact source/deployed config/profile/APK/signer; host/transport/raw device/schema observations; plan/input hashes; native task/trace/case/action/request/session IDs; per-step screenshots/logcat/traces/timestamps; independent backend/product Hermes/provider effect and refusal/no-effect readbacks; byte lengths/SHA256 and producer/session/epoch correlations; cleanup/rollback evidence. Preserve raw observations privately. Never author observations from expected values, export credentials/keys/audio/embeddings/private owner contents, resend uncertain effects or infer owner-goal PASS from a successful process.

Resolve every selector below from actual protected operator inputs before its phase; empty or unknown bindings are BLOCKED. Phone-effect commands are post-PRE_PHONE_PASS only.

`exact_source`

```sh
export VAN_RELEASE_SOURCE_SHA=dfc1557ab99ad8d41cf84714e1bb671e89b045e6
git cat-file -e "$VAN_RELEASE_SOURCE_SHA^{commit}"
test "$(git rev-parse HEAD)" = "$VAN_RELEASE_SOURCE_SHA"
test -z "$(git status --porcelain --untracked-files=all)"
```

`project_truth_review`

```sh
python tools/ci/project_truth_ledger.py verify-pr --base "$VAN_TRUSTED_BASE_REF" --head "$VAN_RELEASE_SOURCE_SHA" --json
```

`profile_compile`

```sh
python tools/runtime/prepare_owner_core_deployment.py --profile "$VAN_PROTECTED_OWNER_CORE_PROFILE" --output "$VAN_PREPARED_CORE_DIR"
```

`host_preflight`

```sh
python tools/runtime/preflight_owner_core.py   --profile-env "$VAN_CORE_CONFIG_ROOT/owner-core.env"   --gateway-env "$VAN_CORE_CONFIG_ROOT/gateway.env"   --google-env "$VAN_CORE_CONFIG_ROOT/google-workspace.env"   --resource-dropin "$VAN_CORE_RESOURCE_DROPIN"   --repository "$VAN_RELEASE_SOURCE_ROOT" --expected-sha "$VAN_RELEASE_SOURCE_SHA"
```

`core_network_observation`

```sh
python tools/runtime/owner_core_network_observations.py   --declaration "$VAN_CORE_DECLARATION"   --expected-declaration-sha256 "$VAN_CORE_DECLARATION_SHA256"   --host-role van-trading-core --out "$VAN_EVIDENCE_DIR/core-network.json"
```

`gateway_qualification`

```sh
VAN_STATE_ROOT="$VAN_CORE_STATE_ROOT" VAN_CONFIG_ROOT="$VAN_CORE_CONFIG_ROOT" VAN_EXPECTED_REPOSITORY_SHA="$VAN_RELEASE_SOURCE_SHA" bash tools/runtime/qualify_gateway_host.sh
```

`browser_public_qualification`

```sh
VAN_BROWSER_INSTANCE=public bash deploy/van-browser-stream/qualify.sh
```

`browser_owner_qualification`

```sh
VAN_BROWSER_INSTANCE=owner bash deploy/van-browser-stream/qualify.sh
```

`host_health_observation`

```sh
python tools/certification/pre_phone_host_acceptance.py   --config-root "$VAN_CORE_CONFIG_ROOT" --state-root "$VAN_CORE_STATE_ROOT"   --android-profile "$VAN_DEPLOYMENT_PROFILE_FILE"   --expected-sha "$VAN_RELEASE_SOURCE_SHA" --out "$VAN_EVIDENCE_DIR/pre-phone-host.json"
```

`voice_and_release`

```sh
python android/tools/package_voice_assets.py --acquire
python android/tools/package_voice_assets.py --verify
(cd android && ./gradlew :app:testReleaseUnitTest :app:lintRelease :app:assembleRelease --console=plain)
python tools/release/owner_release.py packet   --apk android/app/build/outputs/apk/release/app-release.apk   --profile "$VAN_DEPLOYMENT_PROFILE_FILE" --trusted-keys "$VAN_TRUSTED_KEYS_FILE"   --build-config android/app/build/generated/source/buildConfig/release/com/dial/van/BuildConfig.java   --expected-sha "$VAN_RELEASE_SOURCE_SHA" --expected-signer "$VAN_OWNER_SIGNER_SHA256"   --apksigner "$ANDROID_HOME/build-tools/36.0.0/apksigner"   --aapt "$ANDROID_HOME/build-tools/36.0.0/aapt"   --output "$VAN_RELEASE_PACKET_DIR/release-packet.json"
```

`phone_identity_after_non_phone_pass`

```sh
adb -s "$VAN_ADMITTED_ADB_TRANSPORT" get-state
adb -s "$VAN_ADMITTED_ADB_TRANSPORT" shell getprop ro.serialno
adb -s "$VAN_ADMITTED_ADB_TRANSPORT" shell getprop ro.product.model
```

`provision_only_after_non_phone_pass`

```sh
python tools/provisioning/provision_owner_device.py   --gateway "$VAN_INSTALLER_GATEWAY_URL" --device-gateway-url "$VAN_PUBLIC_GATEWAY_URL"   --internal-token-env VAN_DEVICE_ENROLMENT_TOKEN --ca-file "$VAN_GATEWAY_CA_FILE"   --apk android/app/build/outputs/apk/release/app-release.apk   --serial "$VAN_ADMITTED_ADB_TRANSPORT" --expected-device-serial RFCX2054F5W   --expected-model SM-S928B --release-packet "$VAN_RELEASE_PACKET_DIR/release-packet.json"   --deployment-profile "$VAN_DEPLOYMENT_PROFILE_FILE" --trusted-keys "$VAN_TRUSTED_KEYS_FILE"   --expected-release-sha "$VAN_RELEASE_SOURCE_SHA" --expected-signer "$VAN_OWNER_SIGNER_SHA256"   --apksigner "$ANDROID_HOME/build-tools/36.0.0/apksigner" --aapt "$ANDROID_HOME/build-tools/36.0.0/aapt"
```

`native_prepare_actual_discovery`

```sh
python tools/certification/artemis_acceptance.py prepare   --native-schema "$VAN_ACTUAL_NATIVE_SCHEMA" --out "$VAN_EVIDENCE_DIR/native-plan.json"
```

`native_prepare_one_case`

```sh
python tools/certification/artemis_acceptance.py native-call   --plan "$VAN_EVIDENCE_DIR/native-plan.json" --native-schema "$VAN_ACTUAL_NATIVE_SCHEMA"   --case OF-HOME-001:happy --device-serial "$VAN_ADMITTED_ADB_TRANSPORT"   --device-binding "$VAN_FRESH_WIRELESS_READBACKS" --out "$VAN_EVIDENCE_DIR/native-call.json"
```

Exact repository first-adoption instruction:

> **The one-time transition.** Until this checker is on the base branch, the trusted checker is
> the previous one, which does not know commit scopes, bindings or intake commits and refuses the
> G9a intake (`INVALID_AUTHORIZATION ... authorized_paths must be a non-empty list` for the
> binding records). The first landing of this change is therefore the owner's explicit act
> (merge with the old check red, or a direct push by the integrator), once. After it, every
> change is judged by this checker from the base.
