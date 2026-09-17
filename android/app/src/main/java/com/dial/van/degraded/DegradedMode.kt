package com.dial.van.degraded

/** Pure subsystem-health truth shared by Android runtime and JVM visual evidence. */
enum class SubsystemStatus {
    WORKING,
    BROKEN,
    WONT_DO,
}

enum class RestoreAction {
    RETRY_CONNECTION,
    OPEN_SETTINGS,
    REQUEST_PERMISSION,
    CLEAR_QUEUE,
    RESTART_OVERLAY,
    CONTACT_SUPPORT,
    NONE,
}

data class DegradedSubsystem(
    val id: String,
    val label: String,
    val status: SubsystemStatus,
    val detail: String,
    val restoreAction: RestoreAction = RestoreAction.NONE,
)

data class DegradedMode(
    val active: Boolean,
    val reason: String,
    val subsystems: List<DegradedSubsystem>,
    val updatedAtEpochMs: Long = System.currentTimeMillis(),
) {
    val brokenCount: Int = subsystems.count { it.status == SubsystemStatus.BROKEN }
    val workingCount: Int = subsystems.count { it.status == SubsystemStatus.WORKING }

    companion object {
        fun healthy(): DegradedMode {
            val subsystems = defaultSubsystems()
            val broken = subsystems.any { it.status == SubsystemStatus.BROKEN }
            return DegradedMode(
                active = broken,
                reason = if (broken) "Awaiting Google mesh evidence" else "All subsystems nominal",
                subsystems = subsystems,
            )
        }

        fun defaultSubsystems(): List<DegradedSubsystem> = listOf(
            DegradedSubsystem("hermes", "Hermes uplink", SubsystemStatus.WORKING, "Agent execution via Hermes profile van"),
            DegradedSubsystem("gateway", "Van gateway", SubsystemStatus.WORKING, "Owner-authority secure gateway"),
            DegradedSubsystem("overlay", "Floating overlay", SubsystemStatus.WORKING, "Owner assistant embodiment"),
            DegradedSubsystem("queue", "Offline command queue", SubsystemStatus.WORKING, "Encrypted local queue"),
            DegradedSubsystem("notifications", "Notification listener", SubsystemStatus.WORKING, "Context ingestion with redaction"),
            DegradedSubsystem("voice", "Voice I/O", SubsystemStatus.WORKING, "Speech input and TTS output"),
            DegradedSubsystem("biometric", "Biometric gate", SubsystemStatus.WORKING, "A4 approval gate"),
            DegradedSubsystem(
                "google",
                "Google mesh",
                SubsystemStatus.BROKEN,
                "Awaiting gateway google_mesh evidence (CONFIGURED/READY)",
                RestoreAction.RETRY_CONNECTION,
            ),
        )
    }
}
