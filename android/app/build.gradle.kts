plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.serialization")
}

import java.util.Properties

val vanGatewayBaseUrl = providers.gradleProperty("VAN_GATEWAY_BASE_URL")
    .orElse(providers.environmentVariable("VAN_GATEWAY_BASE_URL"))
    .orElse("")
    .get()
    .trim()
val escapedVanGatewayBaseUrl = vanGatewayBaseUrl
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")

/*
 * ADR-RB-027 — the keys this build will accept a signed connectivity manifest from,
 * as newline-separated `kid=PEM` pairs.
 *
 * Compiled in rather than fetched, because a trust anchor delivered over the network is
 * not a trust anchor. Empty is the honest default and means this build applies no
 * manifest at all: it keeps the endpoint it was provisioned with rather than accepting
 * the first one something hands it.
 */
val vanConnectivityTrustedKeys = providers.gradleProperty("VAN_CONNECTIVITY_TRUSTED_KEYS")
    .orElse(providers.environmentVariable("VAN_CONNECTIVITY_TRUSTED_KEYS"))
    .orElse("")
    .get()
    .trim()
val escapedVanConnectivityTrustedKeys = vanConnectivityTrustedKeys
    .replace("\\", "\\\\")
    .replace("\"", "\\\"")
    .replace("\n", "\\n")

android {
    namespace = "com.dial.van"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.dial.van"
        // P1-VOICE-002 / closure blueprint owner decision 1 — raised from 26.
        //
        // Below API 31 there is no `SpeechRecognizer.createOnDeviceSpeechRecognizer`, so
        // `VoiceRecognitionPolicy` resolves to SHERPA_PRIMARY_REQUIRED, and no Sherpa runtime
        // ships. Keeping minSdk 26 meant shipping a VAN that on some supported devices could
        // never hear its owner, and failing honestly at runtime is not the same as being
        // usable. Owner decision 2 declines to build Sherpa; this is the other half of that.
        //
        // Reverse by lowering this and shipping a Sherpa model and engine; the policy branch
        // for API <= 30 is retained and tested for exactly that day.
        minSdk = 31
        targetSdk = 36
        versionCode = 5
        versionName = "0.5.0-dev"
        buildConfigField("String", "VAN_GATEWAY_BASE_URL", "\"$escapedVanGatewayBaseUrl\"")
        buildConfigField(
            "String",
            "VAN_CONNECTIVITY_TRUSTED_KEYS",
            "\"$escapedVanConnectivityTrustedKeys\"",
        )

        /*
         * §0D.3 / §32 — one ABI, because there is one device.
         *
         * The WebRTC AAR carries four native ABIs and about 35 MB of them can never
         * execute on the only handset the production build is bound to. This is a size
         * decision, and it is also a reversible one: the filter is the single place to
         * change when a second device is admitted under its own decision.
         */
        ndk {
            abiFilters += "arm64-v8a"
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    val keystorePropertiesFile = rootProject.file("keystore.properties")
    val keystoreProperties = Properties()
    if (keystorePropertiesFile.exists()) {
        keystorePropertiesFile.inputStream().use { keystoreProperties.load(it) }
    }

    signingConfigs {
        create("release") {
            if (keystorePropertiesFile.exists()) {
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            if (keystorePropertiesFile.exists()) {
                signingConfig = signingConfigs.getByName("release")
            }
        }
        debug {
            isMinifyEnabled = false
        }
    }

    // Fail closed: never ship an unsigned production APK/AAB.
    // Check when the task graph is ready so dependent minify/package steps also abort early.
    gradle.taskGraph.whenReady {
        val releaseRequested = allTasks.any { task ->
            val n = task.name
            n == "assembleRelease" || n == "bundleRelease" || n.endsWith(":assembleRelease") || n.endsWith(":bundleRelease")
        }
        if (releaseRequested) {
            if (!vanGatewayBaseUrl.startsWith("https://")) {
                throw GradleException(
                    "Release gateway configuration refused: VAN_GATEWAY_BASE_URL must be a stable HTTPS URL.",
                )
            }
            if (!keystorePropertiesFile.exists()) {
                throw GradleException(
                    "Release signing refused: android/keystore.properties missing. " +
                        "Copy android/keystore.properties.example and supply a production keystore.",
                )
            }
            val storePath = keystoreProperties["storeFile"] as String?
            if (storePath.isNullOrBlank() || !file(storePath).exists()) {
                throw GradleException("Release signing refused: storeFile missing or not found ($storePath)")
            }

            /*
             * RB-111 / §0D.3 — a release signed by the debug key is not a bound build.
             *
             * §0D.3's binding is "this installed package + this app signing identity +
             * this hardware Keystore key + this Gateway owner-device slot". Android
             * generates a debug keystore per machine, so a release signed with one is
             * signed by whichever machine built it — the identity is not stable, and two
             * builds of the same application id cannot even replace one another. The
             * owner's first sideload failed with exactly that dialog (P2-AND-016).
             *
             * Checked by name rather than by fingerprint because the fingerprint is not
             * knowable here: what is knowable is that `androiddebugkey` and
             * `debug.keystore` are never a production identity.
             */
            val alias = (keystoreProperties["keyAlias"] as String?).orEmpty().trim()
            if (alias.isEmpty() || alias == "androiddebugkey") {
                throw GradleException(
                    "Release signing refused: keyAlias is the Android debug alias, which " +
                        "is generated per machine and cannot be the owner-device binding " +
                        "identity (Rev 1.5 §0D.3).",
                )
            }
            if (storePath.trim().endsWith("debug.keystore")) {
                throw GradleException(
                    "Release signing refused: storeFile is a debug keystore (Rev 1.5 §0D.3).",
                )
            }

            /*
             * RB-121 / §0D.2 — a release build with no trust anchor can never be set up.
             *
             * §0D.2 removed every field the owner could type an endpoint into, so the
             * only way into a production VAN is a signed connectivity manifest or an
             * ADR-RB-026 provisioning payload — and both are verified against keys
             * compiled in here. Empty is the honest default for a debug build and is a
             * dead APK for a release one: it would install, open, and sit on "waiting for
             * the installer" forever, with nothing anywhere saying why.
             *
             * The format is checked, not just the presence. A truncated argument that
             * carried no PEM would parse to no keys at all, which is the same dead build
             * with a value that looks configured.
             */
            val anchors = vanConnectivityTrustedKeys.split("\n")
                .map { it.trim() }
                .filter { it.contains('=') && it.substringAfter('=').contains("BEGIN PUBLIC KEY") }
            if (anchors.isEmpty()) {
                throw GradleException(
                    "Release connectivity configuration refused: " +
                        "VAN_CONNECTIVITY_TRUSTED_KEYS must carry at least one " +
                        "`kid=PEM` anchor, or this build can never be provisioned " +
                        "(Rev 1.5 §0D.2, ADR-RB-026/027).",
                )
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.14"
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
    // P3-AND-007 — SavedStateHandle is what carries owner state across process death,
    // which for a resident assistant is the overnight case, not an edge case.
    implementation("androidx.lifecycle:lifecycle-viewmodel-savedstate:2.8.4")
    implementation("androidx.lifecycle:lifecycle-service:2.8.4")
    implementation("androidx.activity:activity-compose:1.9.1")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.navigation:navigation-compose:2.7.7")

    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")

    implementation("app.rive:rive-android:9.6.5")

    /*
     * Rev 1.5 §32 — the Remote Browser's two admitted dependencies.
     *
     * Both are pinned by exact version and recorded with a digest computed from the
     * artefact itself in `registries/remote_browser_dependencies.json`; the adoption
     * decision is `docs/decisions/VAN-ADOPT-REMOTE-BROWSER-STREAMING-001.yaml`.
     *
     * okhttp is 4.12.0 rather than the 5.5.0 the blueprint named: 5.x ships Kotlin 2.1
     * metadata and this project builds with the Kotlin 1.9.24 plugin, so admitting it
     * would have failed the build on first use. The registry records the rejection and
     * the condition for revisiting it.
     */
    implementation("io.github.webrtc-sdk:android:150.7871.01")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlin:kotlin-test-junit:1.9.24")
    testImplementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.6.3")
    // The mockable android.jar stubs org.json and every call throws
    // "Method ... not mocked", so any local unit test over a parsed gateway
    // payload dies on construction. This puts the reference implementation on
    // the unit-test classpath ahead of the stub; the device still uses
    // Android's own org.json at runtime.
    testImplementation("org.json:json:20240303")
}

/*
 * P1-VOICE-002 — a release must not be able to ship a supported API level on which VAN
 * cannot hear.
 *
 * `VoiceRecognitionPolicy` maps an API level to a recognition backend. Two of those backends
 * need a Sherpa runtime that this build does not contain. Before the raise to minSdk 31 the
 * policy resolved every device below 31 to one of them, so the APK was installable on phones
 * where voice capture could never work — and the only signal was an error code at the moment
 * the owner first spoke.
 *
 * This asserts the invariant at build time by reading both of the things it checks from
 * their canonical homes: minSdk from `defaultConfig`, and the on-device floor from the
 * policy's own source. Neither is mirrored into a constant here, so lowering minSdk without
 * shipping Sherpa, or adding an API branch that resolves to a runtime this build does not
 * contain, stops the build rather than the owner.
 */
val voiceRuntimeGuard = tasks.register("assertVoiceRuntimeIsShippable") {
    val policySource = layout.projectDirectory
        .file("src/main/java/com/dial/van/voice/VoiceRecognitionModels.kt").asFile
    // P1-VOICE-003 — read from the configuration this guards rather than mirrored.
    //
    // This was `val minSdkValue = 31`, a second constant that drifts silently: lowering
    // defaultConfig.minSdk back to 26 without touching it left the guard passing while the
    // build it guards became unshippable. A separate verification test parses the Gradle
    // declaration and would have caught it, but the assembly guard — the one that stops a
    // release — would not have. One source of truth, and this is it.
    val minSdkValue = requireNotNull(android.defaultConfig.minSdk) {
        "defaultConfig.minSdk is unset, so the voice runtime guard has nothing to check"
    }
    val hasSherpaRuntime = configurations.findByName("implementation")
        ?.allDependencies
        ?.any { it.name.contains("sherpa", ignoreCase = true) } ?: false
    inputs.file(policySource)
    inputs.property("minSdk", minSdkValue)
    inputs.property("hasSherpaRuntime", hasSherpaRuntime)
    outputs.upToDateWhen { true }
    doLast {
        if (hasSherpaRuntime) return@doLast
        val text = policySource.readText()
        // The lowest API level the policy resolves to an on-device Android recognizer.
        val onDeviceFloor = Regex("""apiLevel >= (\d+) && onDeviceAvailable""")
            .findAll(text).map { it.groupValues[1].toInt() }.minOrNull()
            ?: error("VoiceRecognitionPolicy no longer declares an on-device branch")
        if (minSdkValue < onDeviceFloor) {
            error(
                "Voice runtime unshippable: minSdk $minSdkValue is below the on-device " +
                    "recognizer floor of $onDeviceFloor and no Sherpa runtime is on the " +
                    "classpath. Devices between $minSdkValue and ${onDeviceFloor - 1} would " +
                    "install VAN and never be able to speak to it. Either raise minSdk to " +
                    "$onDeviceFloor or add the Sherpa engine and model."
            )
        }
    }
}

tasks.matching { it.name.startsWith("assemble") || it.name.startsWith("bundle") }
    .configureEach { dependsOn(voiceRuntimeGuard) }
