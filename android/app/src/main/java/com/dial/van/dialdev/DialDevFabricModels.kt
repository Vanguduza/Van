package com.dial.van.dialdev

import org.json.JSONObject

/**
 * VAN-DEV-007/008/010 read models: agents, Orca workspaces (diff, terminal tail), reviews,
 * memory/handoffs, research, design, CI, security, evidence and the development fabric
 * (`VAN-DEVCC-R1` §6.5–§6.11). Same rule as `DialDevModels.kt`: projection fields only.
 */

data class DevAgent(
    val actorId: String,
    val taskId: String?,
    val harness: String?,
    val model: String?,
    val host: String?,
    val objective: String?,
    val intentPaths: List<String>,
    val intentCommands: List<String>,
    val intentTests: List<String>,
    val ownedPaths: List<String>,
    val nextAction: String?,
    val heartbeatAgeMs: Long?,
    val blockers: List<String>,
)

/** Two actors whose declared intents touch the same paths. Display-only; leases prevent overlap. */
data class DevOverlap(val actors: List<String>, val paths: List<String>, val derived: Boolean)

data class DevAgents(val agents: List<DevAgent>, val overlaps: List<DevOverlap>)

data class DevDiffStats(val files: Int?, val additions: Int?, val deletions: Int?)

data class DevWorkspace(
    val workspaceId: String,
    val taskId: String?,
    val harness: String?,
    val model: String?,
    val host: String?,
    val branch: String?,
    val worktree: String?,
    val status: String?,
    val leaseId: String?,
    val lastActivity: String?,
    val testState: String?,
    val diffStats: DevDiffStats?,
    val lastCheckpoint: String?,
    val terminalState: String?,
    val evidence: List<DevEvidenceRef>,
    val projectedActions: List<ProjectedAction>,
    val consequences: Map<String, String>,
    val uncommittedFiles: Int?,
    val intent: String?,
    val nextAction: String?,
)

data class DevDiffFile(val path: String, val status: String?, val additions: Int?, val deletions: Int?)

/**
 * §5: the file list comes first; a file's hunks are split out of the unified diff only when the
 * owner opens that file. [truncated] means DIAL sent paths only because the diff was above its
 * size bound — VAN says so rather than showing a partial diff as if it were whole.
 */
data class DevDiff(val files: List<DevDiffFile>, val unified: String?, val truncated: Boolean) {
    fun hunksFor(path: String): String? = unified?.let { UnifiedDiff.split(it)[path] }
}

object UnifiedDiff {
    /** Splits a unified diff into per-file sections keyed by the post-image path. */
    fun split(unified: String): Map<String, String> {
        val out = LinkedHashMap<String, StringBuilder>()
        var current: StringBuilder? = null
        for (line in unified.lineSequence()) {
            if (line.startsWith("diff --git ")) {
                val path = line.substringAfter(" b/", missingDelimiterValue = line.substringAfterLast(' '))
                current = StringBuilder().also { out[path] = it }
            }
            current?.append(line)?.append('\n')
        }
        return out.mapValues { it.value.toString().trimEnd('\n') }
    }
}

/** One line of a read-only terminal tail, split into plain and redacted spans. */
data class TerminalSpan(val text: String, val redacted: Boolean)

data class DevTerminalTail(val lines: List<List<TerminalSpan>>, val truncated: Boolean) {
    companion object {
        /** §3.2: at most 200 lines. Enforced here too, whatever arrives. */
        const val MAX_LINES = 200
        private val MARKER = Regex("""\[REDACTED[^\]]*]|«REDACTED[^»]*»|\*{3}REDACTED\*{3}""")

        /**
         * A line is a string (redactions already replaced by a marker DIAL's screening wrote)
         * or `{text, redactions: [{start, end}]}` (ranges of `text` DIAL screened). Either way
         * the redacted span is shown *as* redacted; VAN never reconstructs what was removed.
         */
        fun spans(text: String, ranges: List<IntRange>): List<TerminalSpan> {
            if (ranges.isNotEmpty()) {
                val out = mutableListOf<TerminalSpan>()
                var cursor = 0
                for (r in ranges.sortedBy { it.first }) {
                    val start = r.first.coerceIn(cursor, text.length)
                    val end = (r.last + 1).coerceIn(start, text.length)
                    if (start > cursor) out += TerminalSpan(text.substring(cursor, start), false)
                    out += TerminalSpan("[REDACTED]", true)
                    cursor = end
                }
                if (cursor < text.length) out += TerminalSpan(text.substring(cursor), false)
                return out
            }
            val out = mutableListOf<TerminalSpan>()
            var cursor = 0
            for (m in MARKER.findAll(text)) {
                if (m.range.first > cursor) out += TerminalSpan(text.substring(cursor, m.range.first), false)
                out += TerminalSpan(m.value, true)
                cursor = m.range.last + 1
            }
            if (cursor < text.length || out.isEmpty()) out += TerminalSpan(text.substring(cursor), false)
            return out
        }
    }
}

data class DevFinding(val id: String?, val title: String, val severity: String?, val state: String?, val detail: String?)

data class DevReview(
    val reviewId: String,
    val checkpoint: String?,
    val authorHarness: String?,
    val reviewerHarness: String?,
    val blockingFindings: List<DevFinding>,
    val claimsVerified: Int?,
    val claimsRejected: Int?,
    val recommendation: String?,
)

data class DevLabelled(val title: String, val state: String?, val detail: String?)

data class DevMemory(
    val sharedMemoryCursor: String?,
    val latestCheckpoint: String?,
    val activeHandoff: String?,
    val openVikingCursor: String?,
    val openVikingHealth: String?,
    val candidatesAwaitingAdmission: List<DevLabelled>,
    val recentAdmitted: List<DevLabelled>,
    val contextFreshnessMs: Long?,
)

data class DevResearch(
    val activations: List<DevLabelled>,
    val forecast: List<DevLabelled>,
    val jobs: List<DevLabelled>,
    val traceRefs: List<String>,
)

data class DevDesign(
    val coverage: String?,
    val candidates: List<DevLabelled>,
    val visualAuthority: String?,
    val experienceAuthority: String?,
    val changeRequests: List<DevLabelled>,
)

data class DevCiRun(val branch: String?, val sha: String?, val result: String?, val evidenceRef: String?, val observedAt: String?)

data class DevSecurity(
    val findings: List<DevFinding>,
    val specialistReview: String?,
    val mutationSuite: String?,
)

data class DevEvidence(
    val ref: String,
    val kind: String?,
    val checkpointSha: String?,
    val command: String?,
    val result: String?,
    val reproducedBy: String?,
    val admission: String?,
    val authority: String?,
    val observedAt: String?,
)

data class DevCapability(val name: String, val ladder: String?, val version: String?, val pin: String?, val lastProbe: String?)

data class DevInfrastructure(
    val capabilities: List<DevCapability>,
    val orcaVersion: String?,
    val orcaDrift: String?,
    val orcaDaemonScope: String?,
    val orcaBind: String?,
    val managerSlots: List<DevLabelled>,
    val oracleGate: String?,
    val oracleFailedChecks: List<String>,
    val health: List<DevHealthItem>,
)

object DialDevFabricParse {

    fun agents(data: JSONObject, observedAt: String?): DevAgents {
        val agents = (data.optJSONArray("agents") ?: data.optJSONArray("items")).objects().mapNotNull { a ->
            val id = a.str("actor_id") ?: a.str("actor") ?: return@mapNotNull null
            val intent = a.optJSONObject("intent")
            DevAgent(
                actorId = id,
                taskId = a.str("task_id"),
                harness = a.str("harness"),
                model = a.str("model"),
                host = a.str("host"),
                objective = a.str("objective"),
                intentPaths = intent?.optJSONArray("paths").strings(),
                intentCommands = intent?.optJSONArray("commands").strings(),
                intentTests = intent?.optJSONArray("tests").strings(),
                ownedPaths = a.optJSONArray("owned_paths").strings(),
                nextAction = a.str("next_action"),
                heartbeatAgeMs = a.longOrNull("heartbeat_age_ms") ?: DialDevParse.ageBetween(a.str("heartbeat") ?: a.str("last_heartbeat"), observedAt),
                blockers = a.optJSONArray("blockers").strings(),
            )
        }
        val reported = data.optJSONArray("overlap_warnings").objects().map { w ->
            DevOverlap(w.optJSONArray("actors").strings(), w.optJSONArray("paths").strings(), derived = false)
        }
        return DevAgents(agents, reported.ifEmpty { derivedOverlaps(agents) })
    }

    /**
     * §6.5: overlap warnings when declared intents approach each other — two actors whose
     * intended paths are equal or nest. Derived from the projection's own intent fields and
     * labelled as derived; the lease system, not this list, is what prevents real overlap.
     */
    fun derivedOverlaps(agents: List<DevAgent>): List<DevOverlap> {
        val out = mutableListOf<DevOverlap>()
        for (i in agents.indices) for (j in i + 1 until agents.size) {
            val a = agents[i]
            val b = agents[j]
            val shared = a.intentPaths.flatMap { pa -> b.intentPaths.filter { pb -> nests(pa, pb) }.map { pb -> if (pa.length <= pb.length) pa else pb } }.distinct()
            if (shared.isNotEmpty()) out += DevOverlap(listOf(a.actorId, b.actorId), shared, derived = true)
        }
        return out
    }

    private fun nests(a: String, b: String): Boolean {
        val x = a.trimEnd('/')
        val y = b.trimEnd('/')
        return x == y || y.startsWith("$x/") || x.startsWith("$y/")
    }

    fun workspaces(data: JSONObject): List<DevWorkspace> =
        (data.optJSONArray("workspaces") ?: data.optJSONArray("items")).objects().mapNotNull(::workspace)

    fun workspace(json: JSONObject): DevWorkspace? {
        val w = json.optJSONObject("workspace") ?: json
        val id = w.str("workspace_id") ?: w.str("id") ?: return null
        val stats = w.optJSONObject("diff_stats")
        val lease = w.opt("lease")
        val consequences = w.optJSONObject("consequences")
        return DevWorkspace(
            workspaceId = id,
            taskId = w.str("task_id"),
            harness = w.str("harness"),
            model = w.str("model"),
            host = w.str("host"),
            branch = w.str("branch"),
            worktree = w.str("worktree"),
            status = w.str("status") ?: w.str("state"),
            leaseId = (lease as? JSONObject)?.let { it.str("lease_id") ?: it.str("id") } ?: (lease as? String)?.takeIf { it.isNotBlank() },
            lastActivity = w.str("last_activity"),
            testState = w.str("test_state"),
            diffStats = stats?.let { DevDiffStats(it.intOrNull("files"), it.intOrNull("additions"), it.intOrNull("deletions")) },
            lastCheckpoint = w.str("last_checkpoint"),
            terminalState = w.str("terminal_state"),
            evidence = w.optJSONArray("evidence").objects().mapNotNull(DialDevParse::evidenceRef),
            projectedActions = DialDevActionReducer.parseProjected(json),
            consequences = consequences?.let { c -> c.keys().asSequence().associateWith { c.optString(it) } }.orEmpty(),
            uncommittedFiles = w.intOrNull("uncommitted_files"),
            intent = w.str("intent"),
            nextAction = w.str("next_action") ?: w.str("planned_next_action"),
        )
    }

    fun diff(data: JSONObject): DevDiff = DevDiff(
        files = data.optJSONArray("files").objects().mapNotNull { f ->
            val path = f.str("path") ?: return@mapNotNull null
            DevDiffFile(path, f.str("status"), f.intOrNull("additions"), f.intOrNull("deletions"))
        },
        unified = data.str("diff") ?: data.str("unified"),
        truncated = data.optBoolean("truncated", false) || data.optBoolean("paths_only", false),
    )

    fun terminalTail(data: JSONObject): DevTerminalTail {
        val array = data.optJSONArray("lines")
        val lines = buildList {
            if (array != null) for (i in 0 until array.length()) {
                when (val item = array.opt(i)) {
                    is String -> add(DevTerminalTail.spans(item, emptyList()))
                    is JSONObject -> {
                        val ranges = item.optJSONArray("redactions").objects().mapNotNull { r ->
                            val start = r.intOrNull("start") ?: return@mapNotNull null
                            val end = r.intOrNull("end") ?: return@mapNotNull null
                            if (end <= start) null else start until end
                        }
                        add(DevTerminalTail.spans(item.optString("text"), ranges))
                    }
                    else -> Unit
                }
            }
        }
        val bounded = lines.takeLast(DevTerminalTail.MAX_LINES)
        return DevTerminalTail(bounded, truncated = data.optBoolean("truncated", false) || bounded.size < lines.size)
    }

    fun reviews(data: JSONObject): List<DevReview> =
        (data.optJSONArray("reviews") ?: data.optJSONArray("items")).objects().mapNotNull { r ->
            val id = r.str("review_id") ?: r.str("id") ?: return@mapNotNull null
            DevReview(
                reviewId = id,
                checkpoint = r.str("checkpoint"),
                authorHarness = r.str("author_harness") ?: r.str("author"),
                reviewerHarness = r.str("reviewer_harness") ?: r.str("reviewer"),
                blockingFindings = r.optJSONArray("blocking_findings").objects().mapNotNull(::finding),
                claimsVerified = r.intOrNull("claims_verified"),
                claimsRejected = r.intOrNull("claims_rejected"),
                recommendation = r.str("recommendation"),
            )
        }

    fun finding(f: JSONObject): DevFinding? {
        val title = f.str("title") ?: f.str("summary") ?: return null
        return DevFinding(f.str("id"), title, f.str("severity"), f.str("state"), f.str("detail"))
    }

    fun memory(data: JSONObject): DevMemory {
        val ov = data.optJSONObject("openviking")
        return DevMemory(
            sharedMemoryCursor = data.str("shared_memory_cursor"),
            latestCheckpoint = data.str("latest_checkpoint"),
            activeHandoff = data.str("active_handoff") ?: data.optJSONObject("active_handoff")?.str("summary"),
            openVikingCursor = ov?.str("cursor") ?: data.str("openviking_cursor"),
            openVikingHealth = ov?.str("health") ?: data.str("openviking_health"),
            candidatesAwaitingAdmission = labelled(data, "candidates_awaiting_admission"),
            recentAdmitted = labelled(data, "recent_admitted"),
            contextFreshnessMs = data.longOrNull("context_freshness_ms"),
        )
    }

    fun research(data: JSONObject) = DevResearch(
        activations = labelled(data, "activations"),
        forecast = labelled(data, "forecast"),
        jobs = labelled(data, "jobs"),
        traceRefs = data.optJSONArray("trace_refs").strings(),
    )

    fun design(data: JSONObject): DevDesign {
        val coverage = data.optJSONObject("coverage")
        val authority = data.optJSONObject("authority")
        return DevDesign(
            coverage = coverage?.let { c ->
                val covered = c.intOrNull("covered")
                val total = c.intOrNull("total") ?: c.intOrNull("screens")
                if (covered != null && total != null) "$covered of $total screen×feature cells covered" else null
            } ?: data.str("coverage"),
            candidates = labelled(data, "candidates"),
            visualAuthority = authority?.str("visual") ?: data.str("visual_authority"),
            experienceAuthority = authority?.str("experience") ?: data.str("experience_authority"),
            changeRequests = labelled(data, "change_requests"),
        )
    }

    fun ci(data: JSONObject): List<DevCiRun> =
        (data.optJSONArray("runs") ?: data.optJSONArray("items")).objects().map { r ->
            DevCiRun(r.str("branch"), r.str("sha"), r.str("result"), r.str("evidence_ref"), r.str("observed_at"))
        }

    fun security(data: JSONObject) = DevSecurity(
        findings = data.optJSONArray("findings").objects().mapNotNull(::finding),
        specialistReview = data.stateOf("specialist_review"),
        mutationSuite = data.stateOf("mutation_suite"),
    )

    fun evidence(data: JSONObject): DevEvidence? {
        val e = data.optJSONObject("evidence") ?: data
        val ref = e.str("ref") ?: e.str("evidence_ref") ?: return null
        return DevEvidence(
            ref = ref,
            kind = e.str("kind"),
            checkpointSha = e.str("checkpoint_sha"),
            command = e.str("command"),
            result = e.str("result"),
            reproducedBy = e.str("reproduced_by"),
            admission = e.str("admission_state") ?: e.str("admission"),
            authority = e.str("authority"),
            observedAt = e.str("observed_at"),
        )
    }

    fun infrastructure(data: JSONObject): DevInfrastructure {
        val orca = data.optJSONObject("orca")
        val gate = data.opt("oracle_gate")
        return DevInfrastructure(
            capabilities = data.optJSONArray("capabilities").objects().mapNotNull { c ->
                val name = c.str("name") ?: c.str("tool") ?: return@mapNotNull null
                DevCapability(name, c.str("ladder_state") ?: c.str("ladder"), c.str("version"), c.str("pin"), c.str("last_probe"))
            },
            orcaVersion = orca?.str("version"),
            orcaDrift = orca?.str("drift"),
            orcaDaemonScope = orca?.str("daemon_scope"),
            orcaBind = orca?.str("bind"),
            managerSlots = labelled(data, "manager_chain").ifEmpty { labelled(data, "manager_slots") },
            oracleGate = (gate as? JSONObject)?.let { it.str("state") } ?: (gate as? String),
            oracleFailedChecks = (gate as? JSONObject)?.optJSONArray("failed_checks").strings(),
            health = listOf("hermes", "spmrf", "openviking", "vekl", "artemis").mapNotNull { key ->
                val v = data.opt(key)
                when (v) {
                    is JSONObject -> DevHealthItem(key, v.str("state") ?: v.str("health") ?: v.str("status"), v.str("detail"))
                    is String -> DevHealthItem(key, v, null)
                    else -> null
                }
            },
        )
    }

    /** `[{title|name|id, state|status, detail}]` or `["text", …]` → labelled rows. */
    fun labelled(data: JSONObject, key: String): List<DevLabelled> {
        val array = data.optJSONArray(key) ?: return emptyList()
        return buildList {
            for (i in 0 until array.length()) {
                when (val item = array.opt(i)) {
                    is String -> if (item.isNotBlank()) add(DevLabelled(item, null, null))
                    is JSONObject -> {
                        val title = item.str("title") ?: item.str("name") ?: item.str("slot") ?: item.str("task_id")
                            ?: item.str("id") ?: item.str("packet") ?: continue
                        add(
                            DevLabelled(
                                title,
                                item.str("state") ?: item.str("status") ?: item.str("qualification"),
                                item.str("detail") ?: item.str("summary") ?: item.str("knowledge") ?: item.str("activation_id"),
                            ),
                        )
                    }
                    else -> Unit
                }
            }
        }
    }
}

/**
 * §5: a destructive action's consequence, stated from projection data. DIAL's own sentence
 * wins when it sent one (`consequences.REVOKE_TASK`); otherwise the sentence is assembled only
 * from fields the projection reported, and says plainly which of them it did not report.
 */
object DialDevConsequence {
    fun revoke(taskId: String, leaseId: String?, uncommittedFiles: Int?, fromProjection: String?): String {
        fromProjection?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        val lease = leaseId?.let { "Revokes lease $it" } ?: "Revokes the task's lease (DIAL did not report its id)"
        val files = when {
            uncommittedFiles == null -> "DIAL did not report how many uncommitted files the worktree holds"
            uncommittedFiles == 0 -> "the worktree reports no uncommitted files"
            uncommittedFiles == 1 -> "1 uncommitted file in the worktree will be quarantined"
            else -> "$uncommittedFiles uncommitted files in the worktree will be quarantined"
        }
        return "$lease and stops $taskId's terminal; $files. DIAL decides whether this applies."
    }

    fun reject(prompt: String?, fromProjection: String?): String {
        fromProjection?.trim()?.takeIf { it.isNotEmpty() }?.let { return it }
        val subject = prompt?.trim()?.takeIf { it.isNotEmpty() } ?: "this owner decision"
        return "Rejects $subject. DIAL records the rejection with your reason; the work waiting on it stays blocked."
    }
}

/** `GET /v1/dial-dev/events` (SSE): `{projection_revision, changed: [...]}` per event. */
data class DialDevChange(val projectionRevision: String?, val changed: Set<String>)

object DialDevSse {
    /**
     * Folds SSE lines into events. `data:` lines accumulate until a blank line dispatches them
     * (the SSE framing rule); comments (`:`) and other fields are ignored. Pure so the framing
     * is executed on the JVM rather than trusted.
     */
    class Parser {
        private val data = StringBuilder()

        fun feed(line: String): DialDevChange? {
            if (line.isEmpty()) {
                if (data.isEmpty()) return null
                val payload = data.toString()
                data.setLength(0)
                return parse(payload)
            }
            if (line.startsWith(":")) return null
            if (line.startsWith("data:")) {
                if (data.isNotEmpty()) data.append('\n')
                data.append(line.removePrefix("data:").removePrefix(" "))
            }
            return null
        }
    }

    fun parse(payload: String): DialDevChange? {
        val json = try {
            JSONObject(payload)
        } catch (_: org.json.JSONException) {
            return null
        }
        return DialDevChange(json.str("projection_revision"), json.optJSONArray("changed").strings().map { it.lowercase() }.toSet())
    }

    /** Whether a screen reading [sections] must refetch for [change]. An empty `changed` means "everything". */
    fun affects(change: DialDevChange, sections: Set<String>): Boolean =
        change.changed.isEmpty() || change.changed.any { it in sections }
}
