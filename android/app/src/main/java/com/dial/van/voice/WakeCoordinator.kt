package com.dial.van.voice

import java.util.UUID
import java.util.concurrent.atomic.AtomicReference

enum class WakeCoordinatorState {
    DISARMED,
    ACK_NOT_READY,
    KWS_NOT_READY,
    MIC_PERMISSION_MISSING,
    CAPTURE_UNAVAILABLE,
    ARMED,
    WAKE_ACCEPTED,
    LISTENING_COMMAND,
    ACK_PLAYBACK_FAILED,
    YIELDED_TO_SYSTEM,
    AUTHORITY_REVOKED,
}

data class WakeCoordinatorStatus(
    val state: WakeCoordinatorState,
    val acknowledgementReady: Boolean,
    val kwsReady: Boolean,
    val captureActive: Boolean,
    val echoCancellationActive: Boolean,
    val noiseSuppressionActive: Boolean,
    val activeTurnId: String? = null,
    val lastWakeEvidence: WakeEvidence? = null,
)

/**
 * Deterministic wake lifecycle coordinator. It contains no model reasoning and grants no
 * authority. It only connects an already-provisioned local KWS pipeline to the Android edge.
 *
 * The callback contracts are intentionally injectable so the coordinator remains independent
 * of the concrete sherpa model bundle. Context warm-up must be non-blocking; Hermes remains
 * the sole agent runtime after the signed owner turn is produced.
 */
class WakeCoordinator(
    private val arbiter: VoiceAudioArbiter,
    private val pipeline: WakePipeline?,
    private val acknowledgementReady: () -> Boolean,
    private val playAcknowledgement: () -> Boolean,
    private val beginRecognition: (turnId: String) -> Unit,
    private val contextWarmup: (turnId: String) -> Unit = {},
    private val kwsReady: () -> Boolean = { pipeline != null },
    private val onStatus: (WakeCoordinatorStatus) -> Unit = {},
) {
    private val state = AtomicReference(WakeCoordinatorState.DISARMED)
    @Volatile private var activeTurnId: String? = null
    @Volatile private var lastEvidence: WakeEvidence? = null

    private val wakeRuntime: WakeRuntimeController? = pipeline?.let { configuredPipeline ->
        WakeRuntimeController(
            arbiter = arbiter,
            pipeline = configuredPipeline,
            onAccepted = ::handleAccepted,
            onUncertain = { evidence -> lastEvidence = evidence },
        )
    }

    fun arm(): Boolean {
        if (state.get() == WakeCoordinatorState.AUTHORITY_REVOKED) {
            publish(WakeCoordinatorState.AUTHORITY_REVOKED)
            return false
        }
        if (!kwsReady() || wakeRuntime == null) {
            publish(WakeCoordinatorState.KWS_NOT_READY)
            return false
        }
        if (!acknowledgementReady()) {
            publish(WakeCoordinatorState.ACK_NOT_READY)
            return false
        }
        if (!arbiter.hasRecordPermission()) {
            publish(WakeCoordinatorState.MIC_PERMISSION_MISSING)
            return false
        }
        if (!wakeRuntime.arm()) {
            publish(WakeCoordinatorState.CAPTURE_UNAVAILABLE)
            return false
        }
        activeTurnId = null
        publish(WakeCoordinatorState.ARMED)
        return true
    }

    private fun handleAccepted(evidence: WakeEvidence) {
        lastEvidence = evidence
        val turnId = UUID.randomUUID().toString()
        activeTurnId = turnId
        publish(WakeCoordinatorState.WAKE_ACCEPTED)

        // The asset has already passed readiness before arming. A playback failure is surfaced
        // as degraded evidence but must not throw away owner speech already present in pre-roll.
        val acknowledgementPlayed = runCatching { playAcknowledgement() }.getOrDefault(false)
        if (!acknowledgementPlayed) publish(WakeCoordinatorState.ACK_PLAYBACK_FAILED)

        // This callback should enqueue/cache work rather than block the audio path.
        runCatching { contextWarmup(turnId) }

        runCatching { beginRecognition(turnId) }
            .onSuccess { publish(WakeCoordinatorState.LISTENING_COMMAND) }
            .onFailure {
                activeTurnId = null
                publish(WakeCoordinatorState.CAPTURE_UNAVAILABLE)
            }
    }

    /**
     * Called after final STT/error for a wake-originated turn.
     *
     * A manual Voice button turn must never silently enable always-listening mode, so an
     * absent or mismatched wake turn is a no-op. The final-result path supplies the exact
     * turn id; error callbacks without one may finish only the currently active wake turn.
     */
    fun commandTurnFinished(turnId: String? = null, rearm: Boolean = true): Boolean {
        val active = activeTurnId ?: return false
        if (turnId != null && turnId != active) return false
        activeTurnId = null
        return if (rearm) arm() else {
            disarm(stopCapture = false)
            true
        }
    }

    /** System/telephony/privacy capture always wins over VAN. */
    fun yieldToSystemCapture() {
        wakeRuntime?.disarm(stopCapture = true)
        arbiter.yieldToSystemCapture()
        activeTurnId = null
        publish(WakeCoordinatorState.YIELDED_TO_SYSTEM)
    }

    fun resumeAfterSystemCapture(): Boolean {
        if (state.get() == WakeCoordinatorState.AUTHORITY_REVOKED) return false
        return arm()
    }

    fun disarm(stopCapture: Boolean = true) {
        wakeRuntime?.disarm(stopCapture = stopCapture)
        if (stopCapture) arbiter.stopCapture(clearPreRoll = false)
        activeTurnId = null
        publish(WakeCoordinatorState.DISARMED)
    }

    /** Revoked owner-device authority cannot leave wake-enabled command ingress active. */
    fun revokeAuthority() {
        wakeRuntime?.disarm(stopCapture = true)
        arbiter.stopCapture(clearPreRoll = true)
        activeTurnId = null
        publish(WakeCoordinatorState.AUTHORITY_REVOKED)
    }

    fun status(): WakeCoordinatorStatus = snapshot(state.get())

    private fun publish(next: WakeCoordinatorState) {
        state.set(next)
        onStatus(snapshot(next))
    }

    private fun snapshot(current: WakeCoordinatorState): WakeCoordinatorStatus = WakeCoordinatorStatus(
        state = current,
        acknowledgementReady = acknowledgementReady(),
        kwsReady = kwsReady(),
        captureActive = arbiter.isCapturing(),
        echoCancellationActive = arbiter.echoCancellationActive(),
        noiseSuppressionActive = arbiter.noiseSuppressionActive(),
        activeTurnId = activeTurnId,
        lastWakeEvidence = lastEvidence,
    )
}
