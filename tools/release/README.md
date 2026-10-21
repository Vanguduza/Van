# Owner release and installation packet

The owner release uses the existing signing identity, a qualified `CORE_ONLY_V2`
deployment profile and the public connectivity verification keys. The app receives
its gateway URL and CA at build time and its signed enrollment payload through the
installer. It has no host, port, model, token or CA configuration form.

`owner_release.py packet` verifies the APK signature, owner signer, package, arm64
ABI and native alignment. It checks the generated `BuildConfig.java` source SHA,
gateway and public trust inputs against the selected release inputs. It also reads
`assets/van-build-provenance.json` **inside the signed APK** and checks those same
inputs there. The installer checks this asset again independently. A detached new
BuildConfig or a relabelled packet cannot qualify a stale APK.

The metadata contains the source SHA, application ID, gateway URL and hashes of the
public CA and public verification keys. It contains no private credential. These
checks bind the artifact's declared build inputs; they do not authenticate the build
producer or establish deployment, live service connectivity or handset acceptance.
Those fields remain false in the packet.

## Required existing inputs

Use the exact clean source SHA selected for qualification. Obtain these bindings
through the existing protected operator configuration or the `van-owner-release`
GitHub environment, without generating replacement owner identities:

| Input | Selector |
|---|---|
| Current admitted core deployment profile | `VAN_DEPLOYMENT_PROFILE_FILE`, pointing to the compiler's `android-owner-core.properties` |
| Existing owner APK keystore and alias | Ignored `android/keystore.properties`, with existing `storeFile`, `storePassword`, `keyAlias`, `keyPassword` |
| Independently admitted owner signer fingerprint | `VAN_OWNER_SIGNER_SHA256` |
| Public connectivity verification keys | `VAN_CONNECTIVITY_TRUSTED_KEYS`, and the matching protected operator-selected file passed as `--trusted-keys` |
| Gateway's existing public CA | Operator-selected file passed to provisioning as `--ca-file` |
| Narrow installer credential | Environment-bound `VAN_DEVICE_ENROLMENT_TOKEN` |
| Exact admitted handset | `RFCX2054F5W`, expected physical `ro.product.model` value `SM-S928B`; wireless ADB additionally requires fresh physical identity/model readbacks |

The CI restoration command requires `VAN_OWNER_RELEASE_INPUT_DIR`,
`VAN_OWNER_KEYSTORE_BASE64`, `VAN_OWNER_KEYSTORE_PASSWORD`, `VAN_OWNER_KEY_ALIAS`,
`VAN_OWNER_KEY_PASSWORD`, `VAN_OWNER_SIGNER_SHA256`, `VAN_OWNER_CORE_PROFILE_BASE64`
and `VAN_CONNECTIVITY_TRUSTED_KEYS`. Its fresh private directory must be outside
the checkout. Private keystore material is removed by the workflow's final cleanup.
Missing bindings are a refusal; a debug build cannot replace them.

## Prepare and verify before the handset

The owner-core compiler and live host qualification are described in
[`deploy/van-owner-core/README.md`](../../deploy/van-owner-core/README.md).
Prepare from the actual admitted operator profile, preserve existing owner state,
and qualify the selected core runtime and direct public mTLS route before installing
an APK. `PREPARED_NOT_DEPLOYED` compiler output is not a live receipt.

The commands below use non-secret selector variables already bound by the operator.
`VAN_RELEASE_SOURCE_SHA` must be the exact clean, qualified commit, rather than a
mutable branch name. `VAN_TRUSTED_KEYS_FILE`, `VAN_RELEASE_PACKET_DIR` and the
Android tool paths identify the actual selected files and output directory.

```sh
python android/tools/package_voice_assets.py --acquire
python android/tools/package_voice_assets.py --verify
cd android
./gradlew :app:testReleaseUnitTest :app:lintRelease :app:assembleRelease --console=plain
cd ..
python tools/release/owner_release.py packet \
  --apk android/app/build/outputs/apk/release/app-release.apk \
  --profile "$VAN_DEPLOYMENT_PROFILE_FILE" \
  --trusted-keys "$VAN_TRUSTED_KEYS_FILE" \
  --build-config android/app/build/generated/source/buildConfig/release/com/dial/van/BuildConfig.java \
  --expected-sha "$VAN_RELEASE_SOURCE_SHA" \
  --expected-signer "$VAN_OWNER_SIGNER_SHA256" \
  --apksigner "$ANDROID_HOME/build-tools/36.0.0/apksigner" \
  --aapt "$ANDROID_HOME/build-tools/36.0.0/aapt" \
  --output "$VAN_RELEASE_PACKET_DIR/release-packet.json"
```

Voice acquisition checks the source-locked official archives and every selected
model file. Do not bypass a changed archive or missing model by removing
verification. An independently verified existing staging directory can be supplied
through the packager's `--staged` mode. Neither mode creates a speaker profile or
owner enrollment.

## Handset phase after live prerequisites pass

Through the existing direct Artemis/Commander device route, select the currently
admitted ADB transport with fresh readbacks. The physical serial and model must
match the S24; an old wireless IP:port is insufficient.

The `SM_S928B` descriptor printed by `adb devices -l` cannot replace the required
fresh `ro.product.model` readback. Preserve its original stdout; do not infer or
normalize it into a handset observation.

Bind `VAN_DEVICE_ENROLMENT_TOKEN` through the operator environment and invoke:

```sh
python tools/provisioning/provision_owner_device.py \
  --gateway "$VAN_INSTALLER_GATEWAY_URL" \
  --device-gateway-url "$VAN_PUBLIC_GATEWAY_URL" \
  --internal-token-env VAN_DEVICE_ENROLMENT_TOKEN \
  --ca-file "$VAN_GATEWAY_CA_FILE" \
  --apk android/app/build/outputs/apk/release/app-release.apk \
  --serial "$VAN_ADMITTED_ADB_TRANSPORT" \
  --expected-device-serial RFCX2054F5W \
  --expected-model SM-S928B \
  --release-packet "$VAN_RELEASE_PACKET_DIR/release-packet.json" \
  --deployment-profile "$VAN_DEPLOYMENT_PROFILE_FILE" \
  --trusted-keys "$VAN_TRUSTED_KEYS_FILE" \
  --expected-release-sha "$VAN_RELEASE_SOURCE_SHA" \
  --expected-signer "$VAN_OWNER_SIGNER_SHA256" \
  --apksigner "$ANDROID_HOME/build-tools/36.0.0/apksigner" \
  --aapt "$ANDROID_HOME/build-tools/36.0.0/aapt"
```

The installer verifies artifact bindings before effects, checks the handset,
installs before minting the short-lived payload, verifies its gateway signature,
and waits for the actual gateway `SESSION_ADMITTED` receipt. This receipt covers
transport admission. Run the current direct Artemis acceptance matrix afterward
for owner interactions, error recovery, permissions and independent effects.
