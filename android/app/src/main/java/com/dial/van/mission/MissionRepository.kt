package com.dial.van.mission

import com.dial.van.gateway.VanGatewayClient
import org.json.JSONArray
import org.json.JSONObject

/**
 * Rev 1 §§33, 35, 48 — the data layer behind the six owner surfaces.
 *
 * §48: "Do not produce screens disconnected from live APIs." So this is the only
 * place the surfaces get data, and it has no fallback fixtures — when the
 * gateway is unreachable a load fails visibly rather than rendering a plausible
 * empty state, because an empty Needs You that actually means "could not ask" is
 * the most dangerous screen in the app.
 *
 * §37's cross-surface continuity is why `home()` gathers everything Home needs in one
 * call rather than leaving each screen to ask separately.
 *
 * It does **not** issue those reads concurrently, and an earlier version of this comment
 * said it did. They are five sequential suspend calls, which is exactly the shape §35 warns
 * about: Home has to answer five questions in under five seconds, and five sequential round
 * trips is how that target gets missed. The claim was corrected rather than the code,
 * because nothing constructs this class — the command centre modules call VanGatewayClient
 * directly, and this is component ledger #44, NEVER_CONSTRUCTED with disposition WIRE.
 * Whoever wires it owns the §35 target, and should make these reads concurrent as part of
 * that. Quietly "fixing" the code of a class with no callers would have produced an
 * unexercised improvement and left the next person believing the latency work was done.
 */
class MissionRepository(private val client: VanGatewayClient) {

    /** §35 — everything Home needs, in one pass. */
    suspend fun home(): HomeSnapshot {
        val needs = client.needsYou()
        val active = MissionParsing.missionSummaries(client.missions(activeOnly = true))
        val waiting = MissionParsing.missionSummaries(
            needs.optJSONArray("missions") ?: JSONArray()
        )
        val decisionsArray = needs.optJSONArray("decisions") ?: JSONArray()
        val decisions = (0 until decisionsArray.length()).map {
            MissionParsing.decisionSummary(decisionsArray.getJSONObject(it))
        }
        return HomeSnapshot(
            needsYouCount = needs.optInt("count", waiting.size + decisions.size),
            // Waiting missions are not "active": they are not progressing, and
            // showing them as working would misrepresent what Van is doing.
            activeMissions = active.filter { it.isActive },
            waitingMissions = waiting,
            openDecisions = decisions,
            degraded = degradedCodes(),
        )
    }

    private suspend fun degradedCodes(): List<String> = runCatching {
        val health = client.health()
        val array = health.optJSONArray("degraded") ?: JSONArray()
        (0 until array.length()).map { array.getString(it) }
    }.getOrElse { emptyList() }

    suspend fun missions(activeOnly: Boolean = false): List<MissionSummary> =
        MissionParsing.missionSummaries(client.missions(activeOnly))

    suspend fun mission(missionId: String): JSONObject = client.mission(missionId)

    /** §34 — activities and the owner timeline for one mission. */
    suspend fun missionDetail(missionId: String): MissionDetail {
        val detail = client.mission(missionId)
        val activity = client.missionActivity(missionId)
        val activitiesArray = activity.optJSONArray("activities") ?: JSONArray()
        val eventsArray = activity.optJSONArray("events") ?: JSONArray()
        return MissionDetail(
            summary = MissionParsing.missionSummary(detail),
            activities = (0 until activitiesArray.length()).map {
                MissionParsing.activityItem(activitiesArray.getJSONObject(it))
            },
            events = (0 until eventsArray.length()).map {
                MissionParsing.eventItem(eventsArray.getJSONObject(it))
            },
            verification = detail.optJSONObject("verification"),
        )
    }

    /** §34 — the proof behind a mission, gathered by the gateway. */
    suspend fun evidence(missionId: String): JSONObject = client.missionEvidence(missionId)

    /** §33 — Needs You consolidates approvals, escalations and waiting missions. */
    suspend fun needsYou(): HomeSnapshot = home()

    suspend fun activityFeed(): List<MissionTimeline> {
        val feed = client.activityFeed()
        val missions = feed.optJSONArray("missions") ?: JSONArray()
        return (0 until missions.length()).map { index ->
            val entry = missions.getJSONObject(index)
            val events = entry.optJSONArray("events") ?: JSONArray()
            MissionTimeline(
                missionId = entry.getString("mission_id"),
                title = entry.optString("title", ""),
                state = entry.optString("state", ""),
                events = (0 until events.length()).map {
                    MissionParsing.eventItem(events.getJSONObject(it))
                },
            )
        }
    }

    suspend fun understanding(): UnderstandingView {
        val json = client.understanding()
        val adaptationAwaiting = json.optJSONArray("adaptation_awaiting_you") ?: JSONArray()
        val recentAdaptation = json.optJSONArray("recent_adaptation") ?: JSONArray()
        return UnderstandingView(
            fields = MissionParsing.understandingEntries(json),
            sharedVocabulary = json.optJSONArray("shared_vocabulary") ?: JSONArray(),
            cognitiveComplement = json.optJSONArray("cognitive_complement") ?: JSONArray(),
            recentAdaptation = recentAdaptation,
            adaptationAwaitingYou = adaptationAwaiting,
        )
    }

    suspend fun confirm(assertionId: String) = client.confirmUnderstanding(assertionId)
    suspend fun correct(assertionId: String, value: String) =
        client.correctUnderstanding(assertionId, value)
    suspend fun reject(assertionId: String) = client.rejectUnderstanding(assertionId)
    suspend fun revertAdaptation(changeId: String) = client.revertAdaptation(changeId)
    suspend fun confirmAdaptation(changeId: String) = client.confirmAdaptation(changeId)

    suspend fun cancel(missionId: String) = client.cancelMission(missionId)
    suspend fun message(missionId: String, text: String) = client.messageMission(missionId, text)
    suspend fun resolveDecision(decisionId: String, approved: Boolean) =
        client.resolveDecision(decisionId, approved)

    /** §36 — permissions, and §§30-31 — what Van may do unprompted. */
    suspend fun permissions(): JSONObject = client.permissions()
    suspend fun revokePermission(grantId: String) = client.revokePermission(grantId)
    suspend fun autonomy(): JSONObject = client.autonomy()

    /** Technical drill-downs (§48): capabilities, radar, the eval scoreboard. */
    suspend fun capabilityStatus(): JSONObject = client.capabilityStatus()
    suspend fun technologyRadar(): JSONObject = client.technologyRadar()
    suspend fun evalReport(): JSONObject = client.evalReport()
}

data class MissionDetail(
    val summary: MissionSummary,
    val activities: List<MissionActivityItem>,
    val events: List<MissionEventItem>,
    val verification: JSONObject?,
) {
    /**
     * §6 — the receipt, or its absence, stated plainly. A mission that says
     * "done" with nothing behind it should read that way on the screen too.
     */
    val verificationSummary: String
        get() {
            val record = verification ?: return when (summary.state) {
                "VERIFIED_SUCCESS" -> "Marked done, but no receipt was recorded"
                else -> "Not verified yet"
            }
            val refs = record.optJSONArray("evidence_refs")?.length() ?: 0
            return when (record.optString("status")) {
                "VERIFIED" -> "Checked against $refs piece(s) of evidence"
                "FAILED" -> "Checked, and it had not worked"
                "UNVERIFIABLE" -> "Van could not confirm this either way"
                else -> "Not verified yet"
            }
        }
}

data class MissionTimeline(
    val missionId: String,
    val title: String,
    val state: String,
    val events: List<MissionEventItem>,
)

data class UnderstandingView(
    val fields: Map<String, List<UnderstandingEntry>>,
    val sharedVocabulary: JSONArray,
    val cognitiveComplement: JSONArray,
    val recentAdaptation: JSONArray,
    val adaptationAwaitingYou: JSONArray,
) {
    /** §26 — an adaptation waiting on the owner belongs in Needs You, not buried. */
    val hasAdaptationAwaitingOwner: Boolean get() = adaptationAwaitingYou.length() > 0
}
