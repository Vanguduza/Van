package com.dial.van.degraded

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject

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
        workspaceApiState: String?,
    ) {
        val workspaceReady = workspaceApiState == "READY"
        if (principalRegistered && workspaceReady) {
            update { mode ->
                val detail =
                    "google_mesh workspace_api=READY configured=$configuredCapabilities/$totalCapabilities"
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
                "google_mesh not READY (workspace_api=${workspaceApiState ?: "UNVERIFIED"}, " +
                    "configured=$configuredCapabilities/$totalCapabilities, principal=$principalRegistered)",
                RestoreAction.RETRY_CONNECTION,
            )
        }
    }

    /**
     * Write one subsystem's whole verdict.
     *
     * P3-AND-004/005. `markBroken` and `markWorking` between them could not express
     * WONT_DO, and `markWorking` dropped the detail, so a queue working offline could not
     * say "3 commands queued, waiting to send" without being called broken. Five subsystems
     * had no writer at all; this is the one they use.
     */
    fun mark(id: String, status: SubsystemStatus, detail: String, restore: RestoreAction) {
        update { mode ->
            val subs = mode.subsystems.map { sub ->
                if (sub.id == id) {
                    sub.copy(status = status, detail = detail, restoreAction = restore)
                } else {
                    sub
                }
            }
            val stillBroken = subs.any { it.status == SubsystemStatus.BROKEN }
            mode.copy(
                active = stillBroken,
                reason = if (stillBroken) {
                    subs.first { it.status == SubsystemStatus.BROKEN }.detail
                } else {
                    "All subsystems nominal"
                },
                subsystems = subs,
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

    /**
     * GAP-F-010 — `/health.degraded[]`, mapped into subsystem rows keyed by the gateway's own
     * `DegradedCode` (see [GatewayDegradedMapping]). Bound to [com.dial.van.visual.DegradedBridge]'s
     * `GatewayHealthSink` (a raw-JSON-string sink) below; this `JSONObject` overload is the one
     * to call directly with an already-parsed `/health` body.
     *
     * Reconciles rather than only adds: a code no longer present in [healthJson] clears its
     * row (a fixed id like `"hermes"` goes back to WORKING; a `gw:`-prefixed id is dropped
     * entirely), so a resolved backend fault stops showing on the device the same turn the
     * gateway stops reporting it.
     */
    fun applyGatewayHealth(healthJson: JSONObject) {
        val capabilities = GatewayDegradedMapping.parse(healthJson)
        val byMappedId = capabilities.associateBy { GatewayDegradedMapping.subsystemIdFor(it.code) }
        update { mode ->
            // Every row that is neither a fixed id this mapping owns nor one of its own
            // previously-added gw: rows: device-signal rows (overlay/queue/…) and the
            // google-mesh row, untouched by this pass.
            val untouched = mode.subsystems.filter {
                it.id !in GatewayDegradedMapping.MAPPED_FIXED_IDS &&
                    !it.id.startsWith(GatewayDegradedMapping.ID_PREFIX)
            }
            val fixedRows = GatewayDegradedMapping.MAPPED_FIXED_IDS.map { id ->
                val original = mode.subsystems.firstOrNull { it.id == id }
                val capability = byMappedId[id]
                when {
                    capability != null -> DegradedSubsystem(
                        id = id,
                        label = original?.label ?: id,
                        status = SubsystemStatus.BROKEN,
                        detail = GatewayDegradedMapping.detailFor(capability),
                        restoreAction = RestoreAction.NONE,
                    )
                    original != null -> original.copy(status = SubsystemStatus.WORKING, restoreAction = RestoreAction.NONE)
                    else -> DegradedSubsystem(id, id, SubsystemStatus.WORKING, "", RestoreAction.NONE)
                }
            }
            val gatewayOnlyRows = capabilities
                .filter { GatewayDegradedMapping.subsystemIdFor(it.code) !in GatewayDegradedMapping.MAPPED_FIXED_IDS }
                .map { capability ->
                    DegradedSubsystem(
                        id = GatewayDegradedMapping.subsystemIdFor(capability.code),
                        label = GatewayDegradedMapping.labelFor(capability.code),
                        status = SubsystemStatus.BROKEN,
                        detail = GatewayDegradedMapping.detailFor(capability),
                        restoreAction = RestoreAction.NONE,
                    )
                }
            val subsystems = untouched + fixedRows + gatewayOnlyRows
            val broken = subsystems.firstOrNull { it.status == SubsystemStatus.BROKEN }
            mode.copy(
                active = broken != null,
                reason = broken?.detail ?: "All subsystems nominal",
                subsystems = subsystems,
            )
        }
    }

    /**
     * `com.dial.van.visual.DegradedBridge.GatewayHealthSink`'s shape (`(String) -> Unit`) — the
     * bridge the embodiment worker left for exactly this: `VanApplication.onCreate` binds
     * `DegradedBridge.bindGatewayHealth(app.degradedModeStore::applyGatewayHealth)` and every
     * `/health` refresh reaches this store without `visual/` depending on `degraded/` directly.
     * Malformed JSON is ignored rather than thrown, matching [applyGatewayHealth]'s own
     * "never crash a health screen on a health payload" posture.
     */
    fun applyGatewayHealth(healthJson: String) {
        val parsed = runCatching { JSONObject(healthJson) }.getOrNull() ?: return
        applyGatewayHealth(parsed)
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
