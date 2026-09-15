plugins {
    id("org.jetbrains.kotlin.jvm")
}

/**
 * Owner-facing preview renderer for the Van character.
 *
 * The Android module cannot host this: AGP compiles against `android.jar` as the platform, so
 * `java.awt` is unavailable there. Rather than duplicating the character geometry, this module
 * compiles the *same* pure-Kotlin source files out of `app/src/main/java` and rasterizes them
 * with Java2D. Any drift in `VanScene` shows up in the previews immediately.
 */
private val sharedVisualSources = listOf(
    "visual/VanDrawOp.kt",
    "visual/VanScene.kt",
    "visual/VanStatusPalette.kt",
    "visual/VanVisualRuntime.kt",
    "visual/VanPresence.kt",
    "visual/RiveContract.kt",
    // DIAL Glass / aura design system — the preview must render the shipped tokens, not a copy.
    "visual/VanGlassTokens.kt",
    "visual/VanAuraSpec.kt",
    "visual/VanEffectBudget.kt",
    "visual/VanArtPose.kt",
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
    // Headless so the same command works over SSH and in CI.
    systemProperty("java.awt.headless", "true")
}

tasks.register<JavaExec>("extractOwnerArt") {
    group = "van"
    description = "Cuts shippable Van assets out of the owner-supplied design boards."
    mainClass.set("com.dial.van.preview.OwnerArtMainKt")
    classpath = sourceSets["main"].runtimeClasspath
    systemProperty("java.awt.headless", "true")
}

tasks.named<Test>("test") {
    systemProperty("java.awt.headless", "true")
}
