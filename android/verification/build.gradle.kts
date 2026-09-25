/*
 * A Kotlin/JVM harness that compiles and executes the app's *pure* decision logic.
 *
 * The Android Gradle Plugin cannot be fetched in every environment the repository is
 * checked out into, so `:app:testDebugUnitTest` is not always runnable. The logic most
 * worth testing — how a gateway status becomes something the owner reads (P0-EXEC-003,
 * P2-COH-001) — has no Android dependencies, so it does not need the Android toolchain to
 * be exercised.
 *
 * `main` deliberately points at the app's real source directory rather than a copy. This
 * harness compiles the same files the app compiles; if one of them grows an Android
 * import, this build fails, which is the signal that the logic has stopped being pure and
 * the file list below needs revisiting.
 *
 * It does NOT stand in for the Android build. It proves these files compile and behave;
 * it proves nothing about the app as a whole.
 */
plugins {
    kotlin("jvm") version "2.0.21"
    // Rev 1.5 §20.14 — `QueuedCommand` is the canonical queue's record and carries the
    // session outbox's policy metadata. It is pure Kotlin apart from `@Serializable`, and
    // that annotation is the whole reason this plugin is here: without it the record
    // cannot be compiled in the harness, and the mapping that has to survive a process
    // death would be the one thing nothing executes.
    kotlin("plugin.serialization") version "2.0.21"
}

repositories {
    mavenCentral()
}

dependencies {
    // Android ships its own org.json; this is the same API, so the mission read models
    // compile and run here unchanged. It is a stand-in for the platform class, not an
    // extra dependency of the app.
    implementation("org.json:json:20240303")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
    // Pure JVM, and the app's own `StateFlow` type. Added so that state a screen collects
    // can be held in a file this harness executes rather than in a composable's
    // `remember` — which is where the event history lived, and why it only existed while
    // one screen was open.
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.8.1")
    testImplementation(kotlin("test"))
}

sourceSets {
    named("main") {
        kotlin.setSrcDirs(emptyList<String>())
        kotlin.srcDir("../app/src/main/java")
        // AccountOnboarding.kt is deliberately absent: it references UI models that pull
        // in the Compose graph, so it is not standalone. Its one security-relevant rule —
        // which actions need owner approval — is held to the gateway's by
        // backend/tests/test_account_approval_contract.py instead.
        kotlin.include(
            "com/dial/van/status/**",
            "com/dial/van/mission/MissionModels.kt",
            // Gate 6 — the pure half of the visual runtime. These files have no Android and
            // no Compose imports, which is exactly why the logic that was wrong in them
            // (a restarting animation clock, an unproduced frame-budget signal, an aura
            // family unreachable from live state, a body gap expressed as a proportion) can
            // be executed here rather than only reasoned about.
            "com/dial/van/visual/RiveContract.kt",
            "com/dial/van/visual/VanAnimationClock.kt",
            "com/dial/van/visual/VanAuraPlan.kt",
            "com/dial/van/visual/VanAuraSpec.kt",
            "com/dial/van/visual/VanBodyExclusionProfile.kt",
            "com/dial/van/visual/VanBodyLayout.kt",
            "com/dial/van/visual/VanFlameAura.kt",
            "com/dial/van/visual/VanSilhouette.kt",
            "com/dial/van/visual/VanCharacterMotion.kt",
            "com/dial/van/visual/VanDrawOp.kt",
            "com/dial/van/visual/VanEffectBudget.kt",
            // GAP-F-012 — the event-to-embodiment decision functions, and the total-map
            // registry that proves every VanDurableState/VanFiniteAction has a producer.
            "com/dial/van/visual/VanEmbodimentReducer.kt",
            "com/dial/van/visual/VanEmbodimentProducers.kt",
            // §2/§6 — overlay/action motion timing, kept pure so the durations that decide
            // when VanLiveVisualState.action() auto-clears are exercised on the JVM.
            "com/dial/van/visual/VanMotionMap.kt",
            // GAP-F-014 — the renderer decision as an owner-facing fact, and the bridge
            // that lets `visual/` publish it without depending on `degraded/`.
            "com/dial/van/visual/VanRendererStatus.kt",
            "com/dial/van/visual/DegradedBridge.kt",
            "com/dial/van/visual/VanFieldGeometry.kt",
            "com/dial/van/visual/VanFrameBudget.kt",
            "com/dial/van/visual/VanGlassTokens.kt",
            "com/dial/van/visual/VanPalette.kt",
            "com/dial/van/visual/VanPresence.kt",
            "com/dial/van/visual/VanPresenceFrame.kt",
            "com/dial/van/visual/VanScene.kt",
            "com/dial/van/visual/VanStatePriority.kt",
            "com/dial/van/visual/VanStatusPalette.kt",
            "com/dial/van/visual/VanTradeSemantic.kt",
            "com/dial/van/visual/VanVisualRuntime.kt",
            "com/dial/van/visual/VanWindFieldMotion.kt",
            // Gate 12 — P3-PERF-003. The whole-runtime envelope: pure arithmetic over
            // readings, and the only thing in this repository that can be executed for it.
            // Whether it keeps a real phone cool is Gate 14's measurement, not this file's.
            "com/dial/van/runtime/VanResourceEnvelope.kt",
            "com/dial/van/degraded/DegradedMode.kt",
            "com/dial/van/degraded/SubsystemSignals.kt",
            // GAP-F-010 — the gateway's structured /health.degraded[] mapped onto subsystem
            // rows, and the store that reconciles them into DegradedMode.subsystems. Both are
            // free of Android imports (org.json + kotlinx.coroutines only), same reasoning as
            // every other pure file in this list.
            "com/dial/van/degraded/GatewayDegradedMapping.kt",
            "com/dial/van/degraded/DegradedModeStore.kt",
            "com/dial/van/overlay/OverlayTheme.kt",
            "com/dial/van/overlay/EdgeDocking.kt",
            "com/dial/van/overlay/OverlayVisibilityPolicy.kt",
            "com/dial/van/overlay/OverlayDragController.kt",
            "com/dial/van/overlay/VanOverlayController.kt",
            "com/dial/van/overlay/VanOverlayInteraction.kt",
            // Replaces CommandModule.kt/CommandCentreNav.kt (P3-AND-009's flat 17-module
            // grid) — the typed DNA §4 route registry and the pure nav model built on it:
            // process-death restoration, legacy-intent/deep-link resolution, and the
            // one-level "back" rule.
            "com/dial/van/command/nav/VanRoute.kt",
            "com/dial/van/command/nav/VanNavModel.kt",
            // Jev owner-control read models are pure Kotlin + org.json and must remain testable without Android.
            "com/dial/van/command/jev/JevModels.kt",
            // GAP-F-011 — whether a dispatched command's thread still needs polling, and
            // what GET /v1/commands/{id} becomes once it answers.
            "com/dial/van/command/work/ConversationReducer.kt",
            "com/dial/van/events/EventStream.kt",
            // One history for the app, rather than one per screen. Pure because the
            // cursor is an interface, so the merge of a socket page and a polled one
            // is executed rather than reasoned about.
            "com/dial/van/events/VanEventStreamStore.kt",
            "com/dial/van/share/ShareIntake.kt",
            "com/dial/van/onboarding/OnboardingPlan.kt",
            "com/dial/van/gateway/GatewayRetry.kt",
            "com/dial/van/gateway/ReplayTrigger.kt",
            "com/dial/van/telemetry/DeviceTelemetry.kt",
            "com/dial/van/telemetry/BrowserStreamTelemetry.kt",
            "com/dial/van/telemetry/SessionTelemetry.kt",
            "com/dial/van/trading/TradingFormat.kt",
            "com/dial/van/trading/ChartViewport.kt",
            // GAP-F-003/GAP-F-005 — the trading UI rebuild's own pure layer. TradingModels.kt
            // and TradeBook.kt are included so TradingReadModels.kt's package-internal helpers
            // (`str`/`num`/`arr`/...) and `TradeConfidence`/`ConfidenceBand` resolve; their one
            // external dependency, `com.dial.van.visual.VanTradeSignals`, is already in this
            // list via VanTradeSemantic.kt above. ChartGeometry.kt now builds its grid/time
            // ticks through `design/charts/ChartAxes` (already listed), so it moves here too —
            // same reasoning as Gate 6: no Android import, so it is executed rather than only
            // reasoned about.
            "com/dial/van/trading/TradingModels.kt",
            "com/dial/van/trading/TradeBook.kt",
            "com/dial/van/trading/ChartGeometry.kt",
            "com/dial/van/trading/TradingReadModels.kt",
            "com/dial/van/voice/VoiceRecognitionModels.kt",
            "com/dial/van/voice/WakeModelAsset.kt",
            // Rev 1.5 §21 — the offline voice edge's decisions. Every case that matters
            // here is one that cannot be produced on demand: a bundle with a TTS voice and
            // no ASR model, an answer that arrives at 3am, a reconnect halfway through a
            // sentence, VAN hearing its own voice and interrupting itself.
            "com/dial/van/voice/VoiceAssetManifest.kt",
            "com/dial/van/voice/VoiceTurn.kt",
            "com/dial/van/voice/SpeechQueue.kt",
            // GAP-F-013 — the device-side cue timing model and the pure lookup
            // TtsOutputManager drives it with.
            "com/dial/van/voice/SpeechCueTiming.kt",
            "com/dial/van/voice/LocalTtsRouter.kt",
            "com/dial/van/voice/VoiceAudioPolicy.kt",
            // Written before this checkpoint and never executed: it is pure, it decides
            // what VAN believes the owner said, and nothing ran it. That combination is
            // the shape this programme keeps finding.
            "com/dial/van/voice/VoiceSecondPass.kt",
            // Rev 1.5 — the Remote Browser's pure half. Every interesting case in these
            // files is a failure that cannot be produced on demand against a real network
            // or a real phone: a reordered gesture, a manifest replayed at a device that
            // has moved on, two carriers that share one road. They have no Android imports
            // so they can be executed here rather than only reasoned about.
            "com/dial/van/browser/BrowserInputProtocol.kt",
            "com/dial/van/browser/BrowserWindow.kt",
            "com/dial/van/browser/BrowserOmnibox.kt",
            "com/dial/van/browser/BrowserTabs.kt",
            "com/dial/van/browser/BrowserShortcuts.kt",
            "com/dial/van/browser/BrowserVisualState.kt",
            "com/dial/van/browser/BrowserUpload.kt",
            "com/dial/van/browser/BrowserProcessRecovery.kt",
            "com/dial/van/browser/BrowserModels.kt",
            "com/dial/van/connectivity/ConnectivityManifest.kt",
            "com/dial/van/connectivity/ProvisioningPayload.kt",
            "com/dial/van/session/SessionEnvelope.kt",
            "com/dial/van/session/TransportSupervisor.kt",
            "com/dial/van/session/WarmStandby.kt",
            "com/dial/van/session/DurableOutbox.kt",
            // §20.15 — the exact projection the Tasks screen uses when it asks the owner
            // whether stale/live-context work may be sent after reconnect.
            "com/dial/van/session/ReconfirmationSurface.kt",
            "com/dial/van/session/OutboxPersistence.kt",
            "com/dial/van/session/SessionOutboxStore.kt",
            // The production adapter itself, not a re-implementation of it. It depends on
            // `OutboxRecordStore` rather than on the encrypted queue, so the thing CI
            // compiles and the thing these tests execute are the same file — which is the
            // only arrangement in which "one atomic write" is a property rather than a
            // claim about a file nothing runs.
            "com/dial/van/session/EncryptedSessionOutboxStore.kt",
            "com/dial/van/session/SessionReconciliation.kt",
            // The decision a catch block used to make silently: whether a command
            // whose dispatch failed may be held, and what the owner is told.
            "com/dial/van/session/OfflineSubmission.kt",
            // The two shapes the Gateway sends down the session socket. The client
            // recognised neither, which is invisible in a source diff and in any
            // test that only runs one side.
            "com/dial/van/session/SessionDownstream.kt",
            // The canonical queue's record. Android owns the encryption and the disk;
            // this file is the shape those bytes take, and §20.14's metadata rides on it.
            "com/dial/van/queue/CommandQueueModels.kt",
            // The two byte formats the gateway also implements. They are here because the
            // drift they are exposed to is invisible in a source diff: two canonicalizers
            // that agree on every ASCII document and disagree on one accented character.
            "com/dial/van/security/DeviceProofCanonical.kt",
            "com/dial/van/security/VanCanonicalJson.kt",
            // The Android design system's pure half (docs/design/VAN_PRODUCT_DESIGN_DNA.md).
            // Screen-state reduction, density-tier and motion arithmetic, the domain→colour-role
            // mapping and the chart-axis math have no Compose or Android imports, so — same
            // reasoning as Gate 6 above — they are executed here rather than only reasoned
            // about. The Compose-facing wrapper (`VanTokens.kt` and `design/components/**`)
            // is not included: it cannot compile without the Android Gradle Plugin.
            "com/dial/van/design/ScreenState.kt",
            "com/dial/van/design/DensityTier.kt",
            "com/dial/van/design/MotionSpec.kt",
            "com/dial/van/design/StatusSemantics.kt",
            "com/dial/van/design/LiveBadgeFormat.kt",
            "com/dial/van/design/charts/ChartAxes.kt",
            // DNA §4 destinations 5/6 (Memory, Projects): the read models that turn
            // `/v1/context/export`, `/v1/context/conflicts`, `/v1/projects/{id}/truth`,
            // `/v1/missions`, `/v1/attention` and `/v1/decisions` into what those two
            // screens show. Depend only on org.json and the other pure files already in
            // this list (`com/dial/van/mission/MissionModels.kt`,
            // `com/dial/van/design/StatusSemantics.kt`).
            "com/dial/van/memory/MemoryModels.kt",
            "com/dial/van/projects/ProjectModels.kt",
        )
    }
}

tasks.test {
    useJUnitPlatform()
    testLogging { events("passed", "failed", "skipped") }
}
