package com.dial.van.voice

/**
 * Whether VAN can listen for its name, and why not when it cannot.
 *
 * P1-VOICE-001 originally found an interface-only wake path with no KWS runtime and no
 * production constructor. The repository now exact-pins sherpa-onnx and constructs a real
 * two-stage KWS pipeline from a checksum-admitted app-private bundle. The trained model is
 * still a deployment artefact, so this policy remains the fail-closed owner-facing truth
 * when that bundle is absent, substituted, truncated, or cannot initialize.
 *
 * A keyword-spotting model is a trained artefact, not code. It is owner supply in the same
 * way `van.riv` is, and this file treats it the same way `VanVisualRuntime` treats the
 * artboard: decide from what is actually on disk, name the reason in words an owner can act
 * on, and fail closed rather than pretending.
 *
 * What this makes true that was not: the absence is *reported*. `VanApplication` constructs
 * the wake path on boot, the model state reaches the degraded-subsystem store, and the owner
 * sees "wake word unavailable — no model installed" instead of a wake word that silently
 * never fires.
 *
 * Pure Kotlin, so the decision is executed in `android/verification` rather than reasoned
 * about. The file loading itself lives in the Android layer.
 */
enum class WakeModelState {
    /** A usable model is installed. */
    READY,

    /** No model file at all. The expected state until the owner installs one. */
    ABSENT,

    /** A file exists but is too small or too large to be a real model. */
    UNUSABLE,

    /** The file is present and its digest does not match what the manifest declares. */
    DIGEST_MISMATCH,
}

data class WakeModelStatus(
    val state: WakeModelState,
    val phrase: String,
    val sizeBytes: Long?,
    val sha256: String?,
) {
    val ready: Boolean get() = state == WakeModelState.READY

    /** One sentence for the owner. Never an enum name, never a file path. */
    val sentence: String
        get() = when (state) {
            WakeModelState.READY -> "Listening for \"$phrase\""
            WakeModelState.ABSENT ->
                "I cannot listen for my name yet — no wake word model is installed"
            WakeModelState.UNUSABLE ->
                "The wake word model is not usable, so I am not listening for my name"
            WakeModelState.DIGEST_MISMATCH ->
                "The wake word model is not the one VAN expects, so I am not using it"
        }
}

object WakeModelPolicy {

    /** The phrase the model is trained on. Stated here so nothing else has to guess it. */
    const val PHRASE = "Hey Van"

    /** Below this a file cannot be a trained model; it is a placeholder or a truncation. */
    const val MIN_MODEL_BYTES = 64L * 1024L

    /** Above this it is not a phone-sized keyword spotter and something is wrong. */
    const val MAX_MODEL_BYTES = 64L * 1024L * 1024L

    /**
     * Classify what is on disk.
     *
     * [expectedSha256] is the digest the release manifest declares. Null means the
     * deployment has not pinned one, and the digest is then not checked — which is stated
     * rather than silently treated as a pass, because a model VAN cannot verify is a model
     * that decides when VAN starts listening.
     */
    fun classify(
        sizeBytes: Long?,
        sha256: String? = null,
        expectedSha256: String? = null,
    ): WakeModelStatus {
        val state = when {
            sizeBytes == null -> WakeModelState.ABSENT
            sizeBytes < MIN_MODEL_BYTES || sizeBytes > MAX_MODEL_BYTES -> WakeModelState.UNUSABLE
            expectedSha256 != null && !expectedSha256.equals(sha256, ignoreCase = true) ->
                WakeModelState.DIGEST_MISMATCH
            else -> WakeModelState.READY
        }
        return WakeModelStatus(state = state, phrase = PHRASE, sizeBytes = sizeBytes, sha256 = sha256)
    }
}
