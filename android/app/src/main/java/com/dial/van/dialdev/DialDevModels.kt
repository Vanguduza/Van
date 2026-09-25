package com.dial.van.dialdev

import org.json.JSONObject
import java.time.Duration
import java.time.Instant
import java.time.format.DateTimeParseException

/**
 * VAN-DEV-005/006 read models: what `GET /v1/dial-dev/projects`, `…/projects/{p}/home`,
 * `…/stage-plan`, `…/tasks?view=`, `…/graph` and `…/tasks/{taskId}` become on screen.
 *
 * Every field is read from the projection's `data`; a field DIAL did not send is null or
 * empty, never a friendly default (a "0 running" VAN invented is a fake status). Field names
 * follow `VAN-DEVCC-R1` §3.2 and the Rev 1 §16.3 TODO record; where DIAL may reasonably use
 * either of two spellings the parser accepts both, and says so.
 */

/** §16.3 views, in the order the segmented control shows them. */
enum class DevTaskView(val wire: String, val label: String) {
    NOW("now", "Now"),
    NEXT("next", "Next"),
    IN_PROGRESS("in_progress", "In progress"),
    NEEDS_ME("needs_me", "Needs me"),
    BLOCKED("blocked", "Blocked"),
    REVIEW("review", "Review"),
    FAILED("failed", "Failed"),
    COMPLETED("completed", "Completed"),
    ALL("all", "All"),
    ;

    companion object {
        val DEFAULT = NOW
        fun parse(raw: String?): DevTaskView = entries.firstOrNull { it.wire == raw?.trim()?.lowercase() } ?: DEFAULT
    }
}

data class DevProject(
    val projectId: String,
    val name: String?,
    val classification: String?,
    val forensicBuildReady: String?,
    val currentStage: String?,
)

data class DevTaskRow(
    val taskId: String,
    val title: String,
    val du: String?,
    val stage: String?,
    val rawState: String?,
    val completionCandidate: Boolean,
    val whyNow: String?,
    val harness: String?,
    val model: String?,
    val host: String?,
    val heartbeatAgeMs: Long?,
    val firstBlocker: String?,
    val waitingOn: String?,
    val nextAction: String?,
) {
    val presentation: DialDevSemantics.RawPresentation
        get() = DialDevSemantics.presentRaw(
            rawState,
            completionCandidate,
            DialDevCaptionContext(firstBlocker = firstBlocker, harness = harness, model = model, external = waitingOn),
        )
}

data class DevHealthItem(val subsystem: String, val rawState: String?, val detail: String?)

data class DevNeedsYou(val title: String, val severity: String?, val taskId: String?, val deepLink: String?)

data class DevEvidenceRef(
    val ref: String,
    val kind: String?,
    val result: String?,
    val admission: String?,
    val observedAt: String?,
)

data class DevHome(
    val project: DevProject?,
    val forensicBuildReady: String?,
    val oracleGate: String?,
    val runtimeSlots: String?,
    val counts: Map<String, Int?>,
    val now: List<DevTaskRow>,
    val needsYou: List<DevNeedsYou>,
    val latestCheckpoint: String?,
    val latestEvidence: List<DevEvidenceRef>,
    val health: List<DevHealthItem>,
) {
    companion object {
        /** §6.1's tile order. A count DIAL did not send stays null and shows as "—". */
        val COUNT_KEYS = listOf("ready" to "Ready", "running" to "Running", "blocked" to "Blocked", "needs_you" to "Needs you", "in_review" to "In review")
    }
}

data class DevStage(
    val stageId: String,
    val title: String?,
    val applicable: Boolean?,
    val rawState: String?,
    val dependencies: List<String>,
    val requiredEvidenceCount: Int?,
    val externalBlockers: List<String>,
    val ownerActions: List<String>,
    val artifacts: List<String>,
    val evidence: List<String>,
)

data class DevStagePlan(
    val stages: List<DevStage>,
    val planFingerprint: String?,
    val stagePlanRevision: String?,
    val recompiling: Boolean,
)

data class DevGraphNode(val taskId: String, val title: String?, val rawState: String?, val stage: String?, val critical: Boolean)

/** An edge `from → to`: `from` must finish before `to` can start. */
data class DevGraphEdge(val from: String, val to: String)

data class DevGraph(val nodes: List<DevGraphNode>, val edges: List<DevGraphEdge>) {
    fun dependenciesOf(taskId: String): List<String> = edges.filter { it.to == taskId }.map { it.from }
    fun dependentsOf(taskId: String): List<String> = edges.filter { it.from == taskId }.map { it.to }

    /**
     * List-first navigation (§5): every node, critical path first, then by stage and id — so
     * TalkBack reaches every node through a plain list without needing the canvas.
     */
    fun accessibleOrder(): List<DevGraphNode> =
        nodes.sortedWith(compareBy<DevGraphNode>({ !it.critical }, { it.stage ?: "" }, { it.taskId }))
}

data class DevTimelineEvent(val event: String, val at: String?, val actor: String?, val detail: String?)

data class DevCheckResult(val check: String, val result: String?)

data class DevOwnerAction(val kind: String?, val decisionId: String?, val prompt: String?, val consequence: String?)

data class DevTaskDetail(
    val row: DevTaskRow,
    val projectId: String?,
    val objective: String?,
    val executor: String?,
    val workspaceId: String?,
    val worktree: String?,
    val leaseId: String?,
    val startedAt: String?,
    val lastHeartbeat: String?,
    val expectedPostcondition: String?,
    val dependencies: List<String>,
    val blockers: List<String>,
    val requiredChecks: List<String>,
    val results: List<DevCheckResult>,
    val reviewer: String?,
    val ownerAction: DevOwnerAction?,
    val evidence: List<DevEvidenceRef>,
    val timeline: List<DevTimelineEvent>,
    val intent: String?,
    val androidVerification: Boolean,
    val uncommittedFiles: Int?,
    val consequences: Map<String, String>,
    val projectedActions: List<ProjectedAction>,
)

object DialDevParse {

    fun projects(data: JSONObject): List<DevProject> =
        (data.optJSONArray("projects") ?: data.optJSONArray("items")).objects().mapNotNull(::project)

    fun project(json: JSONObject): DevProject? {
        val id = json.str("project_id") ?: json.str("id") ?: return null
        return DevProject(
            projectId = id,
            name = json.str("name") ?: json.str("title"),
            classification = json.str("classification"),
            forensicBuildReady = json.stateOf("forensic_build_ready"),
            currentStage = json.str("current_stage"),
        )
    }

    fun home(data: JSONObject, observedAt: String?): DevHome {
        val readiness = data.optJSONObject("readiness") ?: data
        val countsJson = data.optJSONObject("counts")
        val latest = data.optJSONObject("latest")
        return DevHome(
            project = data.optJSONObject("project")?.let(::project),
            forensicBuildReady = readiness.stateOf("forensic_build_ready"),
            oracleGate = readiness.stateOf("oracle_gate"),
            runtimeSlots = readiness.optJSONObject("runtime_slots")?.let { slots ->
                val used = slots.intOrNull("used") ?: slots.intOrNull("active")
                val total = slots.intOrNull("total") ?: slots.intOrNull("capacity")
                if (used != null && total != null) "$used/$total" else null
            } ?: readiness.str("runtime_slots"),
            counts = DevHome.COUNT_KEYS.associate { (key, _) -> key to countsJson?.intOrNull(key) },
            now = data.optJSONArray("now").objects().mapNotNull { task(it, observedAt) }.take(5),
            needsYou = data.optJSONArray("needs_you").objects().mapNotNull { item ->
                val title = item.str("title") ?: return@mapNotNull null
                DevNeedsYou(title, item.str("severity"), item.str("task_id"), item.str("deep_link"))
            }.take(3),
            latestCheckpoint = latest?.let { it.str("checkpoint") ?: it.optJSONObject("checkpoint")?.let { cp -> cp.str("sha") ?: cp.str("id") } },
            latestEvidence = latest?.optJSONArray("evidence").objects().mapNotNull(::evidenceRef),
            health = data.optJSONArray("health").objects().mapNotNull { item ->
                val name = item.str("subsystem") ?: item.str("name") ?: return@mapNotNull null
                DevHealthItem(name, item.str("state") ?: item.str("status"), item.str("detail"))
            },
        )
    }

    fun stagePlan(data: JSONObject, sources: Map<String, String>): DevStagePlan = DevStagePlan(
        stages = data.optJSONArray("stages").objects().mapNotNull { stage ->
            val id = stage.str("stage_id") ?: stage.str("id") ?: return@mapNotNull null
            DevStage(
                stageId = id,
                title = stage.str("title"),
                applicable = if (stage.has("applicable")) stage.optBoolean("applicable") else null,
                rawState = stage.str("state"),
                dependencies = stage.optJSONArray("dependencies").strings(),
                requiredEvidenceCount = stage.intOrNull("required_evidence_count")
                    ?: stage.optJSONArray("required_evidence")?.length(),
                externalBlockers = stage.optJSONArray("external_blockers").strings(),
                ownerActions = stage.optJSONArray("owner_actions").strings(),
                artifacts = stage.optJSONArray("artifacts").strings(),
                evidence = stage.optJSONArray("evidence").strings(),
            )
        },
        planFingerprint = data.str("plan_fingerprint"),
        stagePlanRevision = data.str("stage_plan_revision") ?: sources["stage_plan_revision"],
        recompiling = data.optBoolean("recompiling", false),
    )

    fun tasks(data: JSONObject, observedAt: String?): List<DevTaskRow> =
        (data.optJSONArray("tasks") ?: data.optJSONArray("items")).objects().mapNotNull { task(it, observedAt) }

    fun task(json: JSONObject, observedAt: String?): DevTaskRow? {
        val id = json.str("task_id") ?: return null
        val blockers = blockerTexts(json)
        return DevTaskRow(
            taskId = id,
            title = json.str("title") ?: id,
            du = json.str("du"),
            stage = json.str("stage"),
            rawState = json.str("state"),
            completionCandidate = json.optBoolean("completion_candidate", false),
            whyNow = json.str("why_now"),
            harness = json.str("harness"),
            model = json.str("model"),
            host = json.str("host"),
            heartbeatAgeMs = json.longOrNull("heartbeat_age_ms") ?: ageBetween(json.str("last_heartbeat"), observedAt),
            firstBlocker = blockers.firstOrNull(),
            waitingOn = json.str("waiting_on") ?: json.str("external"),
            nextAction = json.str("planned_next_action") ?: json.str("next_action"),
        )
    }

    fun graph(data: JSONObject): DevGraph {
        val critical = data.optJSONArray("critical_path").strings().toSet()
        val nodes = data.optJSONArray("nodes").objects().mapNotNull { node ->
            val id = node.str("task_id") ?: node.str("id") ?: return@mapNotNull null
            DevGraphNode(id, node.str("title"), node.str("state"), node.str("stage"), node.optBoolean("critical", false) || id in critical)
        }
        val edges = data.optJSONArray("edges").objects().mapNotNull { edge ->
            val from = edge.str("from") ?: edge.str("depends_on") ?: return@mapNotNull null
            val to = edge.str("to") ?: edge.str("task_id") ?: return@mapNotNull null
            DevGraphEdge(from, to)
        }
        return DevGraph(nodes, edges)
    }

    fun taskDetail(data: JSONObject, observedAt: String?): DevTaskDetail? {
        val t = data.optJSONObject("task") ?: data
        val row = task(t, observedAt) ?: return null
        val verification = t.optJSONObject("verification")
        val lease = t.opt("lease")
        val owner = t.optJSONObject("owner_action")
        val android = t.opt("android_verification")
        val consequences = t.optJSONObject("consequences")
        return DevTaskDetail(
            row = row,
            projectId = t.str("project") ?: t.str("project_id"),
            objective = t.str("objective"),
            executor = t.str("assigned_executor"),
            workspaceId = t.str("orca_workspace") ?: t.optJSONObject("workspace")?.str("workspace_id"),
            worktree = t.str("worktree"),
            leaseId = (lease as? JSONObject)?.let { it.str("lease_id") ?: it.str("id") } ?: (lease as? String)?.takeIf { it.isNotBlank() },
            startedAt = t.str("started_at"),
            lastHeartbeat = t.str("last_heartbeat"),
            expectedPostcondition = t.str("expected_postcondition"),
            dependencies = t.optJSONArray("dependencies").strings(),
            blockers = blockerTexts(t),
            requiredChecks = verification?.optJSONArray("required_checks").strings(),
            results = verification?.optJSONArray("results").objects().mapNotNull { r ->
                val check = r.str("check") ?: r.str("name") ?: return@mapNotNull null
                DevCheckResult(check, r.str("result"))
            },
            reviewer = verification?.str("reviewer"),
            ownerAction = owner?.let { DevOwnerAction(it.str("kind"), it.str("decision_id"), it.str("prompt"), it.str("consequence")) },
            evidence = t.optJSONArray("evidence").objects().mapNotNull(::evidenceRef),
            timeline = (t.optJSONArray("timeline") ?: t.optJSONArray("progress_events")).objects().mapNotNull { e ->
                val name = e.str("event") ?: e.str("type") ?: return@mapNotNull null
                DevTimelineEvent(name, e.str("at"), e.str("actor"), e.str("detail"))
            },
            intent = t.str("intent") ?: t.optJSONObject("intent")?.let { intent ->
                intent.optJSONArray("paths").strings().joinToString(", ").ifBlank { null }
            },
            // True only when DIAL reports an Android verification for this task (§6.4): the
            // `work/artemis` link is shown on that fact alone, never inferred from the stage.
            androidVerification = when (android) {
                is Boolean -> android
                is JSONObject -> true
                is String -> android.isNotBlank()
                else -> false
            },
            uncommittedFiles = t.intOrNull("uncommitted_files")
                ?: t.optJSONObject("workspace")?.intOrNull("uncommitted_files"),
            consequences = consequences?.let { c -> c.keys().asSequence().associateWith { c.optString(it) } }.orEmpty(),
            projectedActions = DialDevActionReducer.parseProjected(data),
        )
    }

    fun evidenceRef(json: JSONObject): DevEvidenceRef? {
        val ref = json.str("ref") ?: json.str("evidence_ref") ?: json.str("id") ?: return null
        return DevEvidenceRef(ref, json.str("kind"), json.str("result"), json.str("admission_state") ?: json.str("admission"), json.str("observed_at"))
    }

    private fun blockerTexts(json: JSONObject): List<String> {
        val array = json.optJSONArray("blockers") ?: return listOfNotNull(json.str("blocker"))
        return buildList {
            for (i in 0 until array.length()) {
                when (val b = array.opt(i)) {
                    is String -> if (b.isNotBlank()) add(b)
                    is JSONObject -> (b.str("summary") ?: b.str("title") ?: b.str("reason"))?.let(::add)
                    else -> Unit
                }
            }
        }
    }

    /** Heartbeat age measured on DIAL's clock (observed_at − last_heartbeat), never the phone's. */
    fun ageBetween(earlier: String?, later: String?): Long? {
        val a = instant(earlier) ?: return null
        val b = instant(later) ?: return null
        return Duration.between(a, b).toMillis().coerceAtLeast(0L)
    }

    private fun instant(raw: String?): Instant? = raw?.let {
        try {
            Instant.parse(it)
        } catch (_: DateTimeParseException) {
            null
        }
    }
}

/** "12s", "4m", "3h", "2d" — an age an owner can read at a glance. */
object DialDevFormat {
    fun age(ms: Long?): String {
        if (ms == null || ms < 0) return "—"
        val s = ms / 1000
        return when {
            s < 60 -> "${s}s"
            s < 3600 -> "${s / 60}m"
            s < 86_400 -> "${s / 3600}h"
            else -> "${s / 86_400}d"
        }
    }

    fun count(value: Int?): String = value?.toString() ?: "—"

    fun shortSha(value: String?): String = value?.let { if (it.length > 12) it.take(12) else it } ?: "—"
}

internal fun JSONObject.str(key: String): String? =
    if (isNull(key)) null else optString(key).trim().takeIf { it.isNotEmpty() }

internal fun JSONObject.intOrNull(key: String): Int? =
    if (!has(key) || isNull(key)) null else (opt(key) as? Number)?.toInt() ?: optString(key).toIntOrNull()

internal fun JSONObject.longOrNull(key: String): Long? =
    if (!has(key) || isNull(key)) null else (opt(key) as? Number)?.toLong() ?: optString(key).toLongOrNull()

/** A readiness field that may be a word (`"READY"`), a boolean, or `{state: …}`. */
internal fun JSONObject.stateOf(key: String): String? = when (val v = opt(key)) {
    is Boolean -> if (v) "READY" else "NOT_READY"
    is JSONObject -> v.str("state") ?: v.str("status")
    is String -> v.trim().takeIf { it.isNotEmpty() }
    else -> null
}
