package com.dial.van.degraded

import org.json.JSONObject

/**
 * GAP-F-010 — Android did not consume the gateway's structured degraded state.
 *
 * `/health.degraded[]` is the gateway's own `DegradedCapability` list — one entry per active
 * `DegradedCode` (`TRADING_LEDGER_UNAVAILABLE`, `STORAGE_PROBLEM`, `RESEARCH_EGRESS_DENIED`,
 * `HERMES_OFFLINE`, …), each carrying `code`, `broken`, `still_works`, `will_not_do` and
 * `restore_action`. `DegradedMode.defaultSubsystems()`'s fixed nine-id vocabulary
 * (hermes/gateway/overlay/queue/notifications/voice/wake_word/biometric/google) has no
 * mapping from that list, so a gateway-side fault other than "Hermes is down" or "Google mesh
 * is unready" was invisible on the device — every backend fault collapsed into the same two
 * canned rows or nothing at all.
 *
 * This is the mapping's pure half: parsing `/health`'s `degraded` array and deciding, per
 * code, which [DegradedSubsystem] row it becomes. [DegradedModeStore.applyGatewayHealth] is
 * the writer that uses it. No Android imports — `org.json` is the same API Android ships,
 * stood in for here by the `org.json:json` artifact the harness already depends on for every
 * other JSON-shaped pure file — so this executes in `android/verification`.
 */
object GatewayDegradedMapping {

    /** A prefix for every row this mapping adds that has no existing fixed-vocabulary id. */
    const val ID_PREFIX = "gw:"

    /**
     * Backend codes that describe the *same* thing a fixed-vocabulary id already names.
     * `HERMES_OFFLINE` is the one overlap today: `DegradedMode.defaultSubsystems()` already
     * carries an `"hermes"` row (previously written by nothing), and `/health` computes
     * `HERMES_OFFLINE` from the same Hermes health check `VanApplication.refreshGatewayHealth`
     * already calls — so this updates that row in place rather than adding a second, disagreeing
     * one for the same fact.
     */
    private val CODE_TO_EXISTING_ID: Map<String, String> = mapOf(
        "HERMES_OFFLINE" to "hermes",
    )

    /** Every fixed-vocabulary id this mapping ever writes to, for the store's reconciliation pass. */
    val MAPPED_FIXED_IDS: Set<String> = CODE_TO_EXISTING_ID.values.toSet()

    data class GatewayCapability(
        val code: String,
        val broken: String,
        val stillWorks: String,
        val willNotDo: String,
        val restoreAction: String,
    )

    /**
     * Parses `/health`'s `degraded` array. Malformed input (missing key, not an array, a row
     * with no `code`) is dropped rather than thrown — GAP-F-007's rule for the gateway's own
     * `DegradedRegistry.snapshot` ("unknown codes render as a generic entry rather than
     * crashing `/health`") applies just as much to the device reading it back.
     */
    fun parse(healthJson: JSONObject): List<GatewayCapability> {
        val array = healthJson.optJSONArray("degraded") ?: return emptyList()
        return buildList {
            for (index in 0 until array.length()) {
                val row = array.optJSONObject(index) ?: continue
                val code = row.optString("code").trim()
                if (code.isEmpty()) continue
                add(
                    GatewayCapability(
                        code = code,
                        broken = row.optString("broken"),
                        stillWorks = row.optString("still_works"),
                        willNotDo = row.optString("will_not_do"),
                        restoreAction = row.optString("restore_action"),
                    ),
                )
            }
        }
    }

    /** The [DegradedSubsystem.id] a capability writes to: an existing fixed id, or a new one. */
    fun subsystemIdFor(code: String): String =
        CODE_TO_EXISTING_ID[code] ?: "$ID_PREFIX${code.lowercase()}"

    /** A label for a code with no existing fixed row — Title Case with underscores as spaces. */
    fun labelFor(code: String): String =
        code.lowercase().replace('_', ' ').replaceFirstChar { it.uppercase() }

    /**
     * The owner-facing sentence DNA §5 asks a DEGRADED state to carry: which subsystem, what
     * still works, and — since none of these rows have an on-device button (the backend's
     * `restore_action` is prose like "Configure VAN_EXA_API_KEY and enable egress", not one of
     * [RestoreAction]'s fixed device actions) — what would fix it, stated rather than implied.
     */
    fun detailFor(capability: GatewayCapability): String = buildString {
        append(capability.broken.ifBlank { "${capability.code} is active." })
        if (capability.stillWorks.isNotBlank()) append(" Still works: ${capability.stillWorks}.")
        if (capability.willNotDo.isNotBlank()) append(" Will not: ${capability.willNotDo}.")
        if (capability.restoreAction.isNotBlank()) append(" To restore: ${capability.restoreAction}.")
    }.trim()
}
