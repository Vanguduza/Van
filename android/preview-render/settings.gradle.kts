/*
 * A standalone entry point for the JVM preview renderer.
 *
 * `android/settings.gradle` includes `:app`, whose configuration needs the Android Gradle
 * Plugin, and AGP cannot be fetched in every environment this repository is checked out
 * into. That made the evidence renderer unbuildable wherever the Android toolchain was
 * unavailable — which is how the committed visual evidence came to be two authority
 * revisions stale (P1-VIS-002) without anyone noticing.
 *
 * This settings file includes only `:visual-preview`, which is a pure Kotlin/JVM module. It
 * points at the same project directory, so there is one module and one build script, not a
 * copy. The main Android build is unchanged.
 */
pluginManagement {
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
    plugins {
        id("org.jetbrains.kotlin.jvm") version "1.9.24"
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "van-preview-render"
include(":visual-preview")
project(":visual-preview").projectDir = file("../visual-preview")
