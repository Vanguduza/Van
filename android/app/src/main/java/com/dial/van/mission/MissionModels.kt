package com.dial.van.mission

import org.json.JSONArray
import org.json.JSONObject

/**
 * Rev 1 §§33, 48 — the owner-facing read models.
 *
 * §48 is blunt about what these must not be: no fake helper text, no placeholder
 * counts, no static mock status. Every field here is parsed from a live gateway
 * response, and where the gateway says a thing is unknown these carry null
 * rather than a friendly default — a screen that invents "0" for a number it did
 * not receive is exactly the fake status §48 forbids.
 */

/** §33 — what Home needs to answer "is Van okay, and does it need me". */
data class HomeSnapshot(
    val needsYouCount: Int,
    val activeMissions: List<MissionSummary>,
    val waitingMissions: List<MissionSummary>,
    val openDecisions: List<DecisionSummary>,
    val degraded: List<String>,
) {
    /** §35 — the five-second question, answered from one screen. */
    val vanIsOkay: Boolean get() = degraded.isEmpty()
    val needsOwner: Boolean get() = needsYouCount > 0
}

data class MissionSummary(
    val missionId: String,
    val title: String,
    val goal: String,
    val state: String,
    val currentPhase: String?,
    val verificationState: String,
    val needsOwner: Boolean,
    val isTerminal: Boolean,
    val projectId: String?,
    val finalOutcome: String?,
    val updatedAtMs: Long,
) {
    /**
     * §48 — "mission status understandable without logs". The phrasing is
     * deliberately about the owner's situation, not the state machine's.
     */
    val ownerReadableStatus: String
        get() = when (state) {
            "CAPTURED" -> "Just asked"
            "UNDERSTOOD" -> "Working out what you meant"
            "PLANNED" -> "Planned, not started"
            "AUTHORIZED" -> "Ready to start"
            "RUNNING" -> currentPhase?.let { "Working: $it" } ?: "Working"
            "WAITING_EXTERNAL" -> "Waiting on something outside Van"
            "WAITING_FOR_OWNER" -> "Waiting for you"
            "RESUME_AUTHORIZED" -> "Picking back up"
            "VERIFYING" -> "Checking it actually worked"
            "VERIFIED_SUCCESS" -> "Done, and checked"
            // The distinction §6 insists on, carried all the way to the screen.
            "PARTIAL_SUCCESS" -> "Partly done"
            "UNVERIFIABLE" -> "Finished, but Van could not confirm it worked"
            "FAILED" -> finalOutcome ?: "Failed"
            "CANCELLED" -> "Cancelled"
            "EXPIRED" -> "Expired before it finished"
            "BLOCKED_POLICY" -> "Stopped: not allowed"
            "BLOCKED_UNSAFE" -> "Stopped: looked unsafe"
            else -> state
        }

    val isActive: Boolean
        get() = !isTerminal && state != "WAITING_FOR_OWNER"
}

data class DecisionSummary(
    val decisionId: String,
    val title: String,
    val body: String,
    val source: String,
)

data class MissionActivityItem(
    val activityId: String,
    val activityType: String,
    val capabilityId: String,
    val executor: String,
    val state: String,
    val errorClass: String?,
)

data class MissionEventItem(
    val eventId: String,
    val eventType: String,
    val actor: String,
    val severity: String,
    val summary: String,
    val evidenceRef: String?,
    val occurredAtMs: Long,
)

/** §33's Understanding surface. */
data class UnderstandingEntry(
    val assertionId: String,
    val field: String,
    val value: String,
    val state: String,
    val confidence: Double,
    val independentEpisodes: Int,
    val autonomyBearing: Boolean,
    val ownerConfirmed: Boolean,
) {
    /**
     * §64 — only CONFIRMED is actionable, and an autonomy-bearing trait that
     * VAN has merely observed must read as a question rather than a finding.
     */
    val ownerReadableState: String
        get() = when {
            state == "CONFIRMED" && ownerConfirmed -> "You confirmed this"
            state == "CONFIRMED" -> "Van is acting on this"
            state == "CANDIDATE" && autonomyBearing ->
                "Van noticed this — it will not act on it unless you confirm"
            state == "CANDIDATE" -> "Van thinks this, not yet acting on it"
            state == "OBSERVED" -> "Seen once"
            state == "CONTESTED" -> "Evidence disagrees with itself"
            state == "REJECTED" -> "You rejected this"
            else -> state
        }
}

object MissionParsing {
    fun missionSummary(json: JSONObject) = MissionSummary(
        missionId = json.getString("mission_id"),
        title = json.optString("title", ""),
        goal = json.optString("goal", ""),
        state = json.optString("state", "CAPTURED"),
        currentPhase = json.optStringOrNull("current_phase"),
        verificationState = json.optString("verification_state", "PENDING"),
        needsOwner = json.optBoolean("needs_owner", false),
        isTerminal = json.optBoolean("is_terminal", false),
        projectId = json.optStringOrNull("project_id"),
        finalOutcome = json.optStringOrNull("final_outcome"),
        updatedAtMs = json.optLong("updated_at_ms", 0L),
    )

    fun missionSummaries(array: JSONArray): List<MissionSummary> =
        (0 until array.length()).map { missionSummary(array.getJSONObject(it)) }

    fun decisionSummary(json: JSONObject) = DecisionSummary(
        decisionId = json.optString("id", json.optString("decision_id", "")),
        title = json.optString("title", ""),
        body = json.optString("body", ""),
        source = json.optString("source", ""),
    )

    fun activityItem(json: JSONObject) = MissionActivityItem(
        activityId = json.getString("activity_id"),
        activityType = json.optString("activity_type", ""),
        capabilityId = json.optString("capability_id", ""),
        executor = json.optString("executor", ""),
        state = json.optString("state", "PENDING"),
        errorClass = json.optStringOrNull("error_class"),
    )

    fun eventItem(json: JSONObject) = MissionEventItem(
        eventId = json.getString("event_id"),
        eventType = json.optString("event_type", ""),
        actor = json.optString("actor", ""),
        severity = json.optString("severity", "INFO"),
        summary = json.optString("summary", ""),
        evidenceRef = json.optStringOrNull("evidence_ref"),
        occurredAtMs = json.optLong("occurred_at_ms", 0L),
    )

    fun understandingEntries(json: JSONObject): Map<String, List<UnderstandingEntry>> {
        val fields = json.optJSONObject("fields") ?: return emptyMap()
        val out = linkedMapOf<String, List<UnderstandingEntry>>()
        for (key in fields.keys()) {
            val array = fields.getJSONArray(key)
            out[key] = (0 until array.length()).map { index ->
                val entry = array.getJSONObject(index)
                UnderstandingEntry(
                    assertionId = entry.getString("assertion_id"),
                    field = key,
                    value = entry.optString("value", ""),
                    state = entry.optString("state", "OBSERVED"),
                    confidence = entry.optDouble("confidence", 0.0),
                    independentEpisodes = entry.optInt("independent_episodes", 0),
                    autonomyBearing = entry.optBoolean("autonomy_bearing", false),
                    ownerConfirmed = entry.optBoolean("owner_confirmed", false),
                )
            }
        }
        return out
    }
}

/** JSONObject.optString returns "" for absent keys, which hides missing data. */
internal fun JSONObject.optStringOrNull(key: String): String? =
    if (isNull(key)) null else optString(key, "").ifEmpty { null }
