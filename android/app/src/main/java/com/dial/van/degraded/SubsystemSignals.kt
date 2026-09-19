package com.dial.van.degraded

/**
 * The five subsystems that were declared healthy and never written.
 *
 * P3-AND-004. `overlay`, `queue`, `notifications`, `voice` and `biometric` are in
 * `DegradedMode.defaultSubsystems()` and nothing anywhere called `markBroken` or
 * `markWorking` for any of them, so all five reported WORKING regardless of reality. The
 * overlay permission could be revoked, the notification listener disconnected, the
 * microphone denied and the biometric hardware absent, and VAN's own health page said
 * everything was fine. That is worse than having no health page: an owner who checks and is
 * told nothing is wrong stops checking.
 *
 * P3-AND-005 lives here too. `RestoreAction` had all seven values defined and no screen
 * rendered any of them, so the contract carried an actionable instruction the owner never
 * saw. [restoreLabel] and [restoreSentence] are what a screen puts on the button and beside
 * it.
 *
 * Pure Kotlin: the mapping from device facts to subsystem truth is the part worth testing,
 * and reading those facts off Android is not.
 */
data class SubsystemSignals(
    /** `Settings.canDrawOverlays`. False means the overlay cannot be shown at all. */
    val overlayPermissionGranted: Boolean = false,
    /** The overlay service is running right now. */
    val overlayRunning: Boolean = false,
    /** Items sitting in the encrypted queue because they could not be sent. */
    val queuedCommands: Int = 0,
    /** Consecutive failed replay attempts. */
    val queueReplayFailures: Int = 0,
    /** The notification listener is bound by the system. */
    val notificationListenerConnected: Boolean = false,
    /** `RECORD_AUDIO` is granted. */
    val microphonePermissionGranted: Boolean = false,
    /** A speech recogniser is available on this device. */
    val speechRecognitionAvailable: Boolean = false,
    /** `BiometricManager.canAuthenticate(BIOMETRIC_STRONG)` returned SUCCESS. */
    val strongBiometricAvailable: Boolean = false,
    /** The owner has enrolled at least one strong biometric. */
    val biometricEnrolled: Boolean = false,
)

/** One subsystem's resolved truth: what it is, and what the owner can do about it. */
data class SubsystemVerdict(
    val id: String,
    val status: SubsystemStatus,
    val detail: String,
    val restoreAction: RestoreAction,
)

object SubsystemHealth {

    /** Above this, a queue that is not draining is a fault rather than a moment. */
    const val QUEUE_BACKLOG_THRESHOLD = 20

    /** Consecutive replay failures before the queue counts as broken rather than waiting. */
    const val REPLAY_FAILURE_THRESHOLD = 3

    fun evaluate(signals: SubsystemSignals): List<SubsystemVerdict> = listOf(
        overlay(signals),
        queue(signals),
        notifications(signals),
        voice(signals),
        biometric(signals),
    )

    private fun overlay(s: SubsystemSignals): SubsystemVerdict = when {
        !s.overlayPermissionGranted -> SubsystemVerdict(
            "overlay", SubsystemStatus.BROKEN,
            "VAN cannot draw over other apps, so the floating assistant cannot appear",
            RestoreAction.OPEN_SETTINGS,
        )
        !s.overlayRunning -> SubsystemVerdict(
            // WONT_DO, not BROKEN: the owner is allowed to turn the overlay off, and
            // calling their choice a fault is how a health page starts lying in the other
            // direction.
            "overlay", SubsystemStatus.WONT_DO,
            "The floating assistant is not running",
            RestoreAction.RESTART_OVERLAY,
        )
        else -> SubsystemVerdict(
            "overlay", SubsystemStatus.WORKING, "Owner assistant embodiment",
            RestoreAction.NONE,
        )
    }

    private fun queue(s: SubsystemSignals): SubsystemVerdict = when {
        s.queueReplayFailures >= REPLAY_FAILURE_THRESHOLD -> SubsystemVerdict(
            "queue", SubsystemStatus.BROKEN,
            "${s.queuedCommands} command(s) are waiting and VAN cannot send them",
            RestoreAction.RETRY_CONNECTION,
        )
        s.queuedCommands >= QUEUE_BACKLOG_THRESHOLD -> SubsystemVerdict(
            "queue", SubsystemStatus.BROKEN,
            "${s.queuedCommands} commands are queued and not draining",
            RestoreAction.CLEAR_QUEUE,
        )
        s.queuedCommands > 0 -> SubsystemVerdict(
            // Not a fault. A few queued items with no failures is VAN working offline,
            // which is the feature.
            "queue", SubsystemStatus.WORKING,
            "${s.queuedCommands} command(s) queued offline, waiting to send",
            RestoreAction.NONE,
        )
        else -> SubsystemVerdict(
            "queue", SubsystemStatus.WORKING, "Encrypted local queue", RestoreAction.NONE,
        )
    }

    private fun notifications(s: SubsystemSignals): SubsystemVerdict =
        if (s.notificationListenerConnected) {
            SubsystemVerdict(
                "notifications", SubsystemStatus.WORKING,
                "Context ingestion with redaction", RestoreAction.NONE,
            )
        } else {
            SubsystemVerdict(
                "notifications", SubsystemStatus.BROKEN,
                "VAN cannot see your notifications, so it will miss context you expect it to have",
                RestoreAction.OPEN_SETTINGS,
            )
        }

    private fun voice(s: SubsystemSignals): SubsystemVerdict = when {
        !s.microphonePermissionGranted -> SubsystemVerdict(
            "voice", SubsystemStatus.BROKEN,
            "VAN cannot use the microphone, so you can only type to it",
            RestoreAction.REQUEST_PERMISSION,
        )
        !s.speechRecognitionAvailable -> SubsystemVerdict(
            "voice", SubsystemStatus.BROKEN,
            "This device has no speech recognition available",
            RestoreAction.CONTACT_SUPPORT,
        )
        else -> SubsystemVerdict(
            "voice", SubsystemStatus.WORKING, "Speech input and TTS output", RestoreAction.NONE,
        )
    }

    private fun biometric(s: SubsystemSignals): SubsystemVerdict = when {
        !s.strongBiometricAvailable -> SubsystemVerdict(
            "biometric", SubsystemStatus.BROKEN,
            "This device has no strong biometric, so VAN cannot approve sensitive actions",
            RestoreAction.CONTACT_SUPPORT,
        )
        !s.biometricEnrolled -> SubsystemVerdict(
            "biometric", SubsystemStatus.BROKEN,
            "No fingerprint or face is enrolled, so VAN cannot ask you to approve anything",
            RestoreAction.OPEN_SETTINGS,
        )
        else -> SubsystemVerdict(
            "biometric", SubsystemStatus.WORKING, "A4 approval gate", RestoreAction.NONE,
        )
    }

    // ----------------------------------------------------------- P3-AND-005

    /** The words on the button. Imperative, short enough to fit, never an enum name. */
    fun restoreLabel(action: RestoreAction): String = when (action) {
        RestoreAction.RETRY_CONNECTION -> "Try again"
        RestoreAction.OPEN_SETTINGS -> "Open settings"
        RestoreAction.REQUEST_PERMISSION -> "Give permission"
        RestoreAction.CLEAR_QUEUE -> "Clear the queue"
        RestoreAction.RESTART_OVERLAY -> "Start the assistant"
        RestoreAction.CONTACT_SUPPORT -> "Get help"
        RestoreAction.NONE -> ""
    }

    /** What pressing it will do, for the line beside the button. */
    fun restoreSentence(action: RestoreAction): String = when (action) {
        RestoreAction.RETRY_CONNECTION -> "VAN will try to reach the gateway again."
        RestoreAction.OPEN_SETTINGS -> "This opens the Android setting VAN needs you to change."
        RestoreAction.REQUEST_PERMISSION -> "VAN will ask you for the permission it is missing."
        RestoreAction.CLEAR_QUEUE -> "This discards the commands VAN could not send."
        RestoreAction.RESTART_OVERLAY -> "This starts the floating assistant again."
        RestoreAction.CONTACT_SUPPORT -> "This one is not something you can fix from here."
        RestoreAction.NONE -> ""
    }

    /** Whether there is an action to render at all. */
    fun isActionable(action: RestoreAction): Boolean = action != RestoreAction.NONE
}
