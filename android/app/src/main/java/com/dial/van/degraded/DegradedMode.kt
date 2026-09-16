package com.dial.van.degraded

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

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

/** Observable subsystem truth shared by every VAN surface. */
class DegradedModeStore {
    private val _state = MutableStateFlow(DegradedMode.healthy())
    val state: StateFlow<DegradedMode> = _state.asStateFlow()

    fun snapshot(): DegradedMode = _state.value

    fun update(transform: (DegradedMode) -> DegradedMode) {
        _state.update { current ->
            transform(current).copy(updatedAtEpochMs = System.currentTimeMillis())
        }
    }

    fun applyGoogleMesh(configuredCapabilities: Int, totalCapabilities: Int, principalRegistered: Boolean) {
        if (principalRegistered && configuredCapabilities > 0) {
            update { mode ->
                val detail = "google_mesh configured=$configuredCapabilities/$totalCapabilities"
                val subs = mode.subsystems.map { sub ->
                    if (sub.id == "google") {
                        sub.copy(status = SubsystemStatus.WORKING, detail = detail, restoreAction = RestoreAction.NONE)
                    } else {
                        sub
                    }
                }
                val stillBroken = subs.any { it.status == SubsystemStatus.BROKEN }
                mode.copy(
                    active = stillBroken,
                    reason = if (stillBroken) mode.reason else "All subsystems nominal",
                    subsystems = subs,
                )
            }
        } else {
            markBroken(
                "google",
                "google_mesh unverified (configured=$configuredCapabilities/$totalCapabilities, principal=$principalRegistered)",
                RestoreAction.RETRY_CONNECTION,
            )
        }
    }

    fun markBroken(id: String, detail: String, restore: RestoreAction) {
        update { mode ->
            val subs = mode.subsystems.map { sub ->
                if (sub.id == id) sub.copy(status = SubsystemStatus.BROKEN, detail = detail, restoreAction = restore)
                else sub
            }
            mode.copy(active = true, reason = "$id unavailable", subsystems = subs)
        }
    }

    fun markWorking(id: String) {
        update { mode ->
            val subs = mode.subsystems.map { sub ->
                if (sub.id == id) sub.copy(status = SubsystemStatus.WORKING, restoreAction = RestoreAction.NONE)
                else sub
            }
            val stillBroken = subs.any { it.status == SubsystemStatus.BROKEN }
            mode.copy(
                active = stillBroken,
                reason = if (stillBroken) mode.reason else "All subsystems nominal",
                subsystems = subs,
            )
        }
    }
}
