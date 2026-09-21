pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // P1-VOICE-001 — sherpa-onnx publishes its Android AAR through JitPack.
        // The dependency itself is exact-pinned below; no dynamic version is admitted.
        maven { url = uri("https://jitpack.io") }
    }
}

rootProject.name = "Van"
include(":app")
include(":visual-preview")
