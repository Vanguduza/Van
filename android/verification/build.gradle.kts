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
}

repositories {
    mavenCentral()
}

dependencies {
    // Android ships its own org.json; this is the same API, so the mission read models
    // compile and run here unchanged. It is a stand-in for the platform class, not an
    // extra dependency of the app.
    implementation("org.json:json:20240303")
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
            "com/dial/van/visual/VanCharacterMotion.kt",
            "com/dial/van/visual/VanDrawOp.kt",
            "com/dial/van/visual/VanEffectBudget.kt",
            "com/dial/van/visual/VanFieldGeometry.kt",
            "com/dial/van/visual/VanFrameBudget.kt",
            "com/dial/van/visual/VanGlassTokens.kt",
            "com/dial/van/visual/VanPalette.kt",
            "com/dial/van/visual/VanPresence.kt",
            "com/dial/van/visual/VanPresenceFrame.kt",
            "com/dial/van/visual/VanStatusPalette.kt",
            "com/dial/van/visual/VanTradeSemantic.kt",
            "com/dial/van/visual/VanVisualRuntime.kt",
            "com/dial/van/visual/VanWindFieldMotion.kt",
            "com/dial/van/degraded/DegradedMode.kt",
            "com/dial/van/degraded/SubsystemSignals.kt",
            "com/dial/van/overlay/OverlayTheme.kt",
            "com/dial/van/overlay/EdgeDocking.kt",
            "com/dial/van/overlay/OverlayVisibilityPolicy.kt",
            "com/dial/van/overlay/VanOverlayController.kt",
            "com/dial/van/overlay/VanOverlayInteraction.kt",
            "com/dial/van/command/CommandModule.kt",
            "com/dial/van/command/CommandCentreNav.kt",
            "com/dial/van/events/EventStream.kt",
            "com/dial/van/share/ShareIntake.kt",
            "com/dial/van/onboarding/OnboardingPlan.kt",
            "com/dial/van/gateway/GatewayRetry.kt",
            "com/dial/van/gateway/ReplayTrigger.kt",
            "com/dial/van/trading/TradingFormat.kt",
            "com/dial/van/trading/ChartViewport.kt",
            "com/dial/van/voice/SpeakerVerification.kt",
            "com/dial/van/voice/WakeModelAsset.kt",
        )
    }
}

tasks.test {
    useJUnitPlatform()
    testLogging { events("passed", "failed", "skipped") }
}
