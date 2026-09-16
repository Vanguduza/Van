package com.dial.van.degraded

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/**
 * Application-scoped observable subsystem truth.
 *
 * Kept separate from [DegradedMode] so the pure model remains compilable by the JVM visual-evidence
 * module without Android/coroutine runtime concerns leaking into renderer-neutral sources.
 */
class DegradedModeStore {
    private val _state = MutableStateFlow(DegradedMode.healthy())
    val state: StateFlow<DegradedMode> = _state.asStateFlow()

    fun snapshot(): DegradedMode = _state.value

    fun update(transform: (DegradedMode) -> DegradedMode) {
        _state.update { current ->
            transform(current).copy(updatedAtEpochMs = System.currentTimeMillis())
        }
    }

    fun applyGoogleMesh(
        configuredCapabilities: Int,
        totalCapabilities: Int,
        principalRegistered: Boolean,
    ) {
        if (principalRegistered && configuredCapabilities > 0) {
            update { mode ->
                val detail = "google_mesh configured=$configuredCapabilities/$totalCapabilities"
                val subs = mode.subsystems.map { sub ->
                    if (sub.id == "google") {
                        sub.copy(
                            status = SubsystemStatus.WORKING,
                            detail = detail,
                            restoreAction = RestoreAction.NONE,
                        )
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
                if (sub.id == id) {
                    sub.copy(status = SubsystemStatus.BROKEN, detail = detail, restoreAction = restore)
                } else {
                    sub
                }
            }
            mode.copy(active = true, reason = "$id unavailable", subsystems = subs)
        }
    }

    fun markWorking(id: String) {
        update { mode ->
            val subs = mode.subsystems.map { sub ->
                if (sub.id == id) {
                    sub.copy(status = SubsystemStatus.WORKING, restoreAction = RestoreAction.NONE)
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
    }
}
