package com.dial.van.projects

import com.dial.van.design.StatusSemantics
import com.dial.van.memory.MemoryFact
import com.dial.van.mission.MissionSummary
import org.json.JSONObject

/**
 * DNA §4 destination 6 (Projects): "health, phase, current work, blockers, decisions, next
 * actions." Pure Kotlin — no Android, no Compose — same reasoning as
 * `com.dial.van.memory.MemoryReadModel`: which health a project reads as is a decision a
 * JVM test can assert, not something only visible by opening the app.
 *
 * `GET /v1/projects` returns bare ids (`registries/projects.json`'s own shape —
 * `backend/van_gateway/projects/router.py::known_projects`) and neither `/v1/missions` nor
 * `/v1/decisions` carries a `project_id` filter param, so every grouping here is done
 * client-side over the full lists the gateway already returns, mirroring
 * `ProjectRouter.decompose_cross_project`'s own substring approach for the one signal
 * (`decisions`) that has no `project_id` column to match on at all.
 */

/** `GET /v1/projects/{id}/truth`, typed. `backend/van_gateway/projects/router.py::load_truth`. */
data class ProjectTruthSnapshot(
    val projectId: String,
    val ok: Boolean,
    val truthSha: String?,
    val repoSha: String?,
    /** Top-level scalar keys only — `context/authoring.py::ProjectTruthImporter` imports
     *  exactly these as PROJECT_TRUTH facts, so this mirrors what actually becomes a fact. */
    val truth: Map<String, String>,
    val updatedAtUnixSec: Long?,
    val error: String?,
)

object ProjectTruthParsing {
    fun parse(projectId: String, json: JSONObject): ProjectTruthSnapshot {
        val truthObj = json.optJSONObject("truth")
        val flat = linkedMapOf<String, String>()
        if (truthObj != null) {
            val keys = truthObj.keys()
            while (keys.hasNext()) {
                val key = keys.next()
                val value = truthObj.opt(key)
                if (value is String || value is Number || value is Boolean) {
                    flat[key] = value.toString()
                }
            }
        }
        return ProjectTruthSnapshot(
            projectId = projectId,
            ok = json.optBoolean("ok", false),
            truthSha = json.optString("truth_sha").ifBlank { null },
            repoSha = json.optString("repo_sha").ifBlank { null },
            truth = flat,
            updatedAtUnixSec = if (json.has("updated_at_unix") && !json.isNull("updated_at_unix")) {
                json.optLong("updated_at_unix")
            } else {
                null
            },
            error = json.optString("error").ifBlank { null },
        )
    }
}

enum class ProjectHealth { BLOCKED, AT_RISK, STALE_TRUTH, ACTIVE, QUIET, UNKNOWN }

object ProjectHealthPalette {
    /** DNA §2 "never colour alone" — the enum name is the chip label; this is only the role. */
    fun roleFor(health: ProjectHealth): String = when (health) {
        ProjectHealth.BLOCKED -> StatusSemantics.ROLE_CRITICAL
        ProjectHealth.AT_RISK -> StatusSemantics.ROLE_EVENT_RISK
        ProjectHealth.STALE_TRUTH -> StatusSemantics.ROLE_EVENT_RISK
        ProjectHealth.ACTIVE -> StatusSemantics.ROLE_ENGAGED
        ProjectHealth.QUIET -> StatusSemantics.ROLE_MONITOR
        ProjectHealth.UNKNOWN -> StatusSemantics.ROLE_DISABLED
    }
}

/** Attention triage severities that count as a blocker on a project's health (DNA §4). */
private val BLOCKING_SEVERITIES = setOf("BLOCKER", "URGENT")
private val BLOCKED_MISSION_STATES = setOf("BLOCKED_POLICY", "BLOCKED_UNSAFE")
private val AT_RISK_MISSION_STATES = setOf("FAILED", "UNVERIFIABLE")

/**
 * Whether an `/v1/attention` row (as a raw [JSONObject] — the shape `.objectList()` in
 * `com.dial.van.command.CommandCentreComponents` already turns a `JSONArray` into) is about
 * [projectId]. Prefers the row's own `project_id` column
 * (`backend/van_gateway/models.py::AttentionItem`); falls back to a case-insensitive
 * substring of `source`, since some producers (e.g. phone notifications) never set it.
 */
fun attentionMatchesProject(item: JSONObject, projectId: String): Boolean {
    val explicit = item.optString("project_id")
    if (explicit.isNotBlank()) return explicit == projectId
    val source = item.optString("source")
    return source.isNotBlank() && source.contains(projectId, ignoreCase = true)
}

/**
 * Whether a `/v1/decisions` row is about [projectId]. The `decisions` table
 * (`storage/db.py`) has no `project_id` column at all, so this is the same keyword
 * decomposition `ProjectRouter.decompose_cross_project` already uses for cross-project
 * text — matched against the id and, when known, the project's own display name.
 */
fun decisionMentionsProject(item: JSONObject, projectId: String, projectName: String? = null): Boolean {
    val haystack = listOf(item.optString("title"), item.optString("body"), item.optString("source"))
        .joinToString(" ") { it }
        .lowercase()
    if (haystack.contains(projectId.lowercase())) return true
    val name = projectName?.lowercase()?.trim()
    return !name.isNullOrEmpty() && haystack.contains(name)
}

private fun severityRank(severity: String): Int = when (severity) {
    "URGENT" -> 0
    "BLOCKER" -> 1
    "FOLLOW_UP" -> 2
    "INFO" -> 3
    else -> 4
}

/** The per-project health arithmetic: DNA §4 "health derived from truth + missions". */
object ProjectHealthModel {

    fun missionsForProject(all: List<MissionSummary>, projectId: String): List<MissionSummary> =
        all.filter { it.projectId == projectId }

    fun runningMissions(missions: List<MissionSummary>): List<MissionSummary> =
        missions.filter { it.isActive }

    fun blockedMissions(missions: List<MissionSummary>): List<MissionSummary> =
        missions.filter { it.state in BLOCKED_MISSION_STATES }

    fun atRiskMissions(missions: List<MissionSummary>): List<MissionSummary> =
        missions.filter { it.state in AT_RISK_MISSION_STATES }

    /** The newest signal across truth, this project's missions and its facts, in epoch ms. */
    fun lastChangeAtMs(
        truth: ProjectTruthSnapshot?,
        missions: List<MissionSummary>,
        facts: List<MemoryFact>,
    ): Long? {
        val candidates = buildList {
            truth?.updatedAtUnixSec?.let { add(it * 1000L) }
            missions.forEach { add(it.updatedAtMs) }
            facts.forEach { add(it.validFromMs) }
        }
        return candidates.maxOrNull()
    }

    /**
     * Truth's own scalar keys are unstructured per-project (each project's own truth
     * document decides its keys — `context/authoring.py`'s importer takes whatever scalar
     * top-level keys the file has). The handful of names a truth file conventionally uses
     * for its own stage are tried first; a project whose truth is unstructured falls back
     * to "is anything running" rather than claiming a phase nothing stated.
     */
    private val PHASE_KEYS = listOf("phase", "stage", "milestone", "status")

    fun phase(truth: ProjectTruthSnapshot?, missions: List<MissionSummary>): String {
        val fromTruth = truth?.truth?.entries
            ?.firstOrNull { (key, value) -> key.lowercase() in PHASE_KEYS && value.isNotBlank() }
            ?.value
        if (!fromTruth.isNullOrBlank()) return fromTruth
        return if (missions.any { it.isActive }) "In progress" else "Idle"
    }

    /**
     * BLOCKED beats everything: a blocked mission or an open BLOCKER/URGENT attention item
     * is the fact the owner most needs, even over stale truth. UNKNOWN (truth never loaded)
     * and STALE_TRUTH (loaded but not current) are kept apart, because "VAN has never seen
     * this project's truth" and "VAN's copy is out of date" call for different owner action.
     */
    fun health(
        truth: ProjectTruthSnapshot?,
        missions: List<MissionSummary>,
        blockerAttentionCount: Int,
    ): ProjectHealth {
        if (blockedMissions(missions).isNotEmpty() || blockerAttentionCount > 0) return ProjectHealth.BLOCKED
        if (truth == null) return ProjectHealth.UNKNOWN
        if (!truth.ok) return ProjectHealth.STALE_TRUTH
        if (atRiskMissions(missions).isNotEmpty()) return ProjectHealth.AT_RISK
        return if (runningMissions(missions).isNotEmpty()) ProjectHealth.ACTIVE else ProjectHealth.QUIET
    }
}

/** What the Projects list shows for one project (DNA §4: "health ... and phase"). */
data class ProjectSummary(
    val projectId: String,
    val health: ProjectHealth,
    val phase: String,
    val runningMissionsCount: Int,
    val blockersCount: Int,
    val lastChangeAtMs: Long?,
)

object ProjectSummaryBuilder {
    fun build(
        projectId: String,
        truth: ProjectTruthSnapshot?,
        allMissions: List<MissionSummary>,
        attention: List<JSONObject>,
        facts: List<MemoryFact>,
    ): ProjectSummary {
        val missions = ProjectHealthModel.missionsForProject(allMissions, projectId)
        val blockerAttention = attention.count {
            it.optString("severity") in BLOCKING_SEVERITIES && attentionMatchesProject(it, projectId)
        }
        return ProjectSummary(
            projectId = projectId,
            health = ProjectHealthModel.health(truth, missions, blockerAttention),
            phase = ProjectHealthModel.phase(truth, missions),
            runningMissionsCount = ProjectHealthModel.runningMissions(missions).size,
            blockersCount = ProjectHealthModel.blockedMissions(missions).size + blockerAttention,
            lastChangeAtMs = ProjectHealthModel.lastChangeAtMs(truth, missions, facts),
        )
    }
}

/** What Project Detail shows (DNA §4: "current work, blockers, decisions, next actions"). */
data class ProjectDetailModel(
    val projectId: String,
    val health: ProjectHealth,
    val phase: String,
    val truth: ProjectTruthSnapshot?,
    val currentWork: List<MissionSummary>,
    val blockedMissions: List<MissionSummary>,
    val blockerAttention: List<JSONObject>,
    val recentChanges: List<MissionSummary>,
    val decisions: List<JSONObject>,
    val nextActions: List<JSONObject>,
    val relevantFacts: List<MemoryFact>,
)

object ProjectDetailBuilder {
    const val RECENT_CHANGES_LIMIT = 12

    /** A project-scoped fact's `scope` (`command/context_requirements.py`'s own convention). */
    fun scopeFor(projectId: String): String = "project:$projectId"

    fun build(
        projectId: String,
        truth: ProjectTruthSnapshot?,
        allMissions: List<MissionSummary>,
        attention: List<JSONObject>,
        decisions: List<JSONObject>,
        facts: List<MemoryFact>,
        projectName: String? = null,
    ): ProjectDetailModel {
        val missions = ProjectHealthModel.missionsForProject(allMissions, projectId)
        val nextActions = attention
            .filter { attentionMatchesProject(it, projectId) }
            .sortedWith(
                compareBy(
                    { severityRank(it.optString("severity")) },
                    { -it.optLong("created_at_unix", 0L) },
                ),
            )
        val blockerAttention = nextActions.filter { it.optString("severity") in BLOCKING_SEVERITIES }
        val scope = scopeFor(projectId)
        val relevantFacts = facts.filter { it.scope == scope || it.subject == projectId }
        val relevantDecisions = decisions.filter { decisionMentionsProject(it, projectId, projectName) }
        return ProjectDetailModel(
            projectId = projectId,
            health = ProjectHealthModel.health(truth, missions, blockerAttention.size),
            phase = ProjectHealthModel.phase(truth, missions),
            truth = truth,
            currentWork = ProjectHealthModel.runningMissions(missions),
            blockedMissions = ProjectHealthModel.blockedMissions(missions),
            blockerAttention = blockerAttention,
            recentChanges = missions.sortedByDescending { it.updatedAtMs }.take(RECENT_CHANGES_LIMIT),
            decisions = relevantDecisions,
            nextActions = nextActions,
            relevantFacts = relevantFacts,
        )
    }
}
