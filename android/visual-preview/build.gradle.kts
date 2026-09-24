plugins {
    id("org.jetbrains.kotlin.jvm")
}

/**
 * Owner-facing preview renderer for the Van character.
 *
 * The Android module cannot host this: AGP compiles against `android.jar` as the platform, so
 * `java.awt` is unavailable there. Rather than duplicating the character geometry, this module
 * compiles the *same* pure-Kotlin source files out of `app/src/main/java` and rasterizes them
 * with Java2D. Any drift in `VanScene` or the living-field geometry shows up in previews.
 */
private val sharedVisualSources = listOf(
    "visual/VanDrawOp.kt",
    "visual/VanScene.kt",
    "visual/VanStatusPalette.kt",
    "visual/VanVisualRuntime.kt",
    "visual/VanPresence.kt",
    "visual/VanPresenceFrame.kt",
    "visual/RiveContract.kt",
    "visual/VanGlassTokens.kt",
    "visual/VanAuraPlan.kt",
    "visual/VanAuraSpec.kt",
    "visual/VanEffectBudget.kt",
    "visual/VanWindFieldMotion.kt",
    "visual/VanAnimationClock.kt",
    "visual/VanFrameBudget.kt",
    "visual/VanTradeSemantic.kt",
    "visual/VanBodyExclusionProfile.kt",
    "visual/VanFieldGeometry.kt",
    "visual/VanArtPose.kt",
    // GAP-F-012 — the dependency-free half of the embodiment producer registry (no JSON,
    // unlike VanEmbodimentReducer.kt, which visual-preview has no JSON library to compile).
    "visual/VanEmbodimentProducers.kt",
    "degraded/DegradedMode.kt",
    "overlay/OverlayTheme.kt",
).map { "com/dial/van/$it" }

sourceSets {
    named("main") {
        kotlin.srcDir("../app/src/main/java")
        kotlin.setIncludes(sharedVisualSources + listOf("com/dial/van/preview/**"))
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    testImplementation("junit:junit:4.13.2")
}

tasks.register<JavaExec>("renderVanPreviews") {
    group = "van"
    description = "Renders the owner-facing Van character previews into artifacts/release/preview."
    mainClass.set("com.dial.van.preview.VanPreviewMainKt")
    classpath = sourceSets["main"].runtimeClasspath
    systemProperty("java.awt.headless", "true")
}

// Legacy owner-art extraction intentionally removed: rejected bitmap poses must not be regenerated.

tasks.named<Test>("test") {
    systemProperty("java.awt.headless", "true")
    testLogging { events("passed", "failed", "skipped") }
}
