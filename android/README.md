# Van Android

Production-oriented Kotlin Android embodiment for **VAN** — DIAL's owner assistant.

Android provides overlay UI, encrypted offline command queue, notification/share ingress, voice I/O interfaces, and biometric A4 gating. **Hermes profile `van` owns agent execution.** This app does not embed a second agent loop or launch Claude/Codex/Gemini.

## Requirements

| Setting | Value |
|---------|-------|
| `applicationId` | `com.dial.van` |
| `minSdk` | 26 |
| `targetSdk` / `compileSdk` | 34 |
| UI | Jetpack Compose |

## Setup

1. Copy `local.properties.example` → `local.properties` and set `sdk.dir`.
2. JDK 17 (example: `C:\Users\Admin\Documents\dde\.tooling\jdk-17`).
3. Android SDK with platform 34 and build-tools installed.

## Build

```bat
cd android
gradlew.bat assembleDebug
gradlew.bat test
```

If `gradlew.bat` is missing, install Gradle 8.7+ and run `gradle wrapper`, or use a system Gradle from the project root:

```bat
gradle -p android assembleDebug
```

## Gradle wrapper

- Wrapper config: `gradle/wrapper/gradle-wrapper.properties` (Gradle 8.7)
- Windows launcher: `gradlew.bat`
- If the wrapper JAR was not committed, bootstrap with: `gradle wrapper --gradle-version 8.7`

## Architecture

```
overlay/          FloatingOverlayService (START_STICKY, persisted position/mode)
command/          CommandCentreActivity — Attention, Decisions, Projects, …
queue/            EncryptedCommandQueue (Keystore AES-GCM + EncryptedSharedPreferences index)
notification/     VanNotificationListenerService — redaction, policy, quiet hours
share/            ShareIntentReceiver — text/URL/files as untrusted context
voice/            VoiceInputManager, TtsOutputManager, barge-in, speech sync frames
security/         BiometricGate for A4 approvals
visual/           Rive contract enums, Canvas fallback avatar, optional van.riv
degraded/         DegradedMode subsystem model
onboarding/       Permission education flow
```

## Visual contract

Kotlin enums in `visual/RiveContract.kt` must match `../visual-authority/rive_contract.json` exactly. JVM tests in `RiveContractTest` enforce this.

Place `van.riv` in `app/src/main/assets/van.riv` to enable Rive rendering; otherwise the Canvas fallback draws the canonical silhouette (silver hair, cyan visor, cyan orb).

## Permissions (AndroidManifest)

- `SYSTEM_ALERT_WINDOW` — overlay avatar
- `FOREGROUND_SERVICE` / `FOREGROUND_SERVICE_SPECIAL_USE` — overlay service
- `POST_NOTIFICATIONS` — foreground notification
- `RECORD_AUDIO` — voice input
- `USE_BIOMETRIC` — A4 gate
- `BIND_NOTIFICATION_LISTENER_SERVICE` — notification listener (user enables in Settings)

**No AccessibilityService.**

## Security notes

- Shared/notification content is labeled untrusted; `SECRET` sensitivity suppresses enqueue.
- Offline queue default TTL: 24h; expired sensitive commands are never executed.
- Idempotency keys survive retries.

## adb

Example path: `C:\Users\Admin\AppData\Local\android-sdk\platform-tools\adb.exe`

```bat
adb install -r app\build\outputs\apk\debug\app-debug.apk
```
