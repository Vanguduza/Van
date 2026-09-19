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
        kotlin.include("com/dial/van/status/**", "com/dial/van/mission/MissionModels.kt")
    }
}

tasks.test {
    useJUnitPlatform()
    testLogging { events("passed", "failed", "skipped") }
}
