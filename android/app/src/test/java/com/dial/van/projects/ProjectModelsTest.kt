package com.dial.van.projects

import com.dial.van.memory.MemoryReadModel
import com.dial.van.mission.MissionSummary
import org.json.JSONArray
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class ProjectModelsTest {

    private fun mission(
        id: String,
        projectId: String? = "van",
        state: String = "RUNNING",
        isTerminal: Boolean = false,
        updatedAtMs: Long = 1_000L,
    ) = MissionSummary(
        missionId = id,
        title = "Mission $id",
        goal = "goal",
        state = state,
        currentPhase = null,
        verificationState = "PENDING",
        needsOwner = false,
        isTerminal = isTerminal,
        projectId = projectId,
        finalOutcome = null,
        updatedAtMs = updatedAtMs,
    )

    private fun truth(
        projectId: String = "van",
        ok: Boolean = true,
        truth: JSONObject = JSONObject(),
        updatedAtUnix: Long? = 5_000L,
    ): ProjectTruthSnapshot {
        val json = JSONObject().put("ok", ok).put("project_id", projectId).put("truth_sha", "sha1").put("truth", truth)
        if (updatedAtUnix != null) json.put("updated_at_unix", updatedAtUnix)
        return ProjectTruthParsing.parse(projectId, json)
    }

    private fun attentionItem(
        id: String,
        severity: String,
        projectId: String? = "van",
        source: String = "",
        createdAtUnix: Long = 1L,
    ) = JSONObject()
        .put("id", id)
        .put("title", "item $id")
        .put("severity", severity)
        .put("source", source)
        .put("created_at_unix", createdAtUnix)
        .apply { put("project_id", projectId ?: JSONObject.NULL) }

    // ---- ProjectTruthParsing -----------------------------------------------------------

    @Test
    fun `truth parsing flattens only scalar top-level keys`() {
        val nested = JSONObject().put("branch", "main").put("stack", "kotlin")
            .put("blockers", JSONArray().put("a")) // arrays are not flattened, same as the importer
            .put("nested", JSONObject().put("x", 1))
        val snapshot = ProjectTruthParsing.parse("van", JSONObject().put("ok", true).put("truth", nested))
        assertEquals(mapOf("branch" to "main", "stack" to "kotlin"), snapshot.truth)
    }

    @Test
    fun `truth parsing reads ok, shas and updated_at`() {
        val snapshot = truth(ok = true, updatedAtUnix = 42L)
        assertTrue(snapshot.ok)
        assertEquals("sha1", snapshot.truthSha)
        assertEquals(42L, snapshot.updatedAtUnixSec)
    }

    @Test
    fun `truth parsing without updated_at reads null rather than zero`() {
        val json = JSONObject().put("ok", false).put("error", "truth_missing")
        val snapshot = ProjectTruthParsing.parse("van", json)
        assertEquals(null, snapshot.updatedAtUnixSec)
        assertEquals("truth_missing", snapshot.error)
        assertFalse(snapshot.ok)
    }

    // ---- ProjectHealthModel -------------------------------------------------------------

    @Test
    fun `missionsForProject filters by project id only`() {
        val all = listOf(mission("m1", projectId = "van"), mission("m2", projectId = "dial"))
        assertEquals(listOf("m1"), ProjectHealthModel.missionsForProject(all, "van").map { it.missionId })
    }

    @Test
    fun `health is BLOCKED when a mission is blocked, even with current truth and no running work`() {
        val missions = listOf(mission("m1", state = "BLOCKED_POLICY", isTerminal = true))
        val health = ProjectHealthModel.health(truth(), missions, blockerAttentionCount = 0)
        assertEquals(ProjectHealth.BLOCKED, health)
    }

    @Test
    fun `health is BLOCKED from attention alone, with no blocked mission`() {
        val health = ProjectHealthModel.health(truth(), emptyList(), blockerAttentionCount = 1)
        assertEquals(ProjectHealth.BLOCKED, health)
    }

    @Test
    fun `health is UNKNOWN when truth was never loaded and nothing is blocked`() {
        val health = ProjectHealthModel.health(null, emptyList(), blockerAttentionCount = 0)
        assertEquals(ProjectHealth.UNKNOWN, health)
    }

    @Test
    fun `health is STALE_TRUTH when truth loaded but not ok`() {
        val health = ProjectHealthModel.health(truth(ok = false), emptyList(), blockerAttentionCount = 0)
        assertEquals(ProjectHealth.STALE_TRUTH, health)
    }

    @Test
    fun `health is AT_RISK when a mission failed or was unverifiable`() {
        val missions = listOf(mission("m1", state = "FAILED", isTerminal = true))
        assertEquals(ProjectHealth.AT_RISK, ProjectHealthModel.health(truth(), missions, 0))
    }

    @Test
    fun `health is ACTIVE with running work and QUIET with none, otherwise`() {
        val running = listOf(mission("m1", state = "RUNNING"))
        assertEquals(ProjectHealth.ACTIVE, ProjectHealthModel.health(truth(), running, 0))
        assertEquals(ProjectHealth.QUIET, ProjectHealthModel.health(truth(), emptyList(), 0))
    }

    @Test
    fun `phase prefers a truth key over deriving from missions`() {
        val truthWithPhase = truth(truth = JSONObject().put("Phase", "Beta"))
        assertEquals("Beta", ProjectHealthModel.phase(truthWithPhase, emptyList()))
    }

    @Test
    fun `phase falls back to mission activity when truth has no phase-shaped key`() {
        val bareTruth = truth(truth = JSONObject().put("branch", "main"))
        assertEquals("In progress", ProjectHealthModel.phase(bareTruth, listOf(mission("m1", state = "RUNNING"))))
        assertEquals("Idle", ProjectHealthModel.phase(bareTruth, emptyList()))
    }

    @Test
    fun `lastChangeAtMs is the newest of truth, missions and facts`() {
        val t = truth(updatedAtUnix = 1L) // 1000 ms
        val missions = listOf(mission("m1", updatedAtMs = 5_000L))
        val facts = MemoryReadModel.parseExportFacts(
            JSONObject().put(
                "stores",
                JSONObject().put(
                    "owner_facts",
                    JSONObject().put(
                        "records",
                        JSONArray().put(
                            JSONObject().put("fact_id", "f1").put("subject", "van").put("predicate", "branch")
                                .put("value", "main").put("authority", "PROJECT_TRUTH").put("source_trust", "TRUSTED_OWNER_FILE")
                                .put("scope", "project:van").put("valid_from_ms", 9_000L).put("observed_at_ms", 9_000L)
                                .put("confidence_permille", 1000).put("valid_until_ms", JSONObject.NULL),
                        ),
                    ),
                ),
            ),
        )
        assertEquals(9_000L, ProjectHealthModel.lastChangeAtMs(t, missions, facts))
    }

    // ---- matching helpers ---------------------------------------------------------------

    @Test
    fun `attentionMatchesProject prefers the explicit column over source text`() {
        val explicit = attentionItem("a1", "BLOCKER", projectId = "van")
        assertTrue(attentionMatchesProject(explicit, "van"))
        assertFalse(attentionMatchesProject(explicit, "dial"))

        val bySource = attentionItem("a2", "INFO", projectId = null, source = "notification:com.van.app")
        assertTrue(attentionMatchesProject(bySource, "van"))
    }

    @Test
    fun `decisionMentionsProject matches id or display name in title, body or source`() {
        val byId = JSONObject().put("title", "van needs a review").put("body", "").put("source", "")
        assertTrue(decisionMentionsProject(byId, "van"))

        val byName = JSONObject().put("title", "Ship the VAN release").put("body", "").put("source", "")
        assertTrue(decisionMentionsProject(byName, "van", projectName = "VAN"))

        val unrelated = JSONObject().put("title", "unrelated").put("body", "nothing here").put("source", "")
        assertFalse(decisionMentionsProject(unrelated, "van", projectName = "VAN Product"))
    }

    // ---- ProjectSummaryBuilder / ProjectDetailBuilder ------------------------------------

    @Test
    fun `ProjectSummaryBuilder integrates missions, attention and facts for one project`() {
        val missions = listOf(mission("m1", projectId = "van", state = "RUNNING"), mission("m2", projectId = "dial"))
        val attention = listOf(attentionItem("a1", "BLOCKER", projectId = "van"))
        val summary = ProjectSummaryBuilder.build("van", truth(), missions, attention, emptyList())
        assertEquals(ProjectHealth.BLOCKED, summary.health)
        assertEquals(1, summary.runningMissionsCount)
        assertEquals(1, summary.blockersCount)
    }

    @Test
    fun `ProjectDetailBuilder sorts next actions by severity then recency and isolates blockers`() {
        val attention = listOf(
            attentionItem("info1", "INFO", createdAtUnix = 5L),
            attentionItem("urgent1", "URGENT", createdAtUnix = 1L),
            attentionItem("blocker1", "BLOCKER", createdAtUnix = 3L),
        )
        val detail = ProjectDetailBuilder.build("van", truth(), emptyList(), attention, emptyList(), emptyList())
        assertEquals(listOf("urgent1", "blocker1", "info1"), detail.nextActions.map { it.optString("id") })
        assertEquals(listOf("urgent1", "blocker1"), detail.blockerAttention.map { it.optString("id") })
    }

    @Test
    fun `ProjectDetailBuilder scopes relevant facts to the project scope or subject`() {
        val export = JSONObject().put(
            "stores",
            JSONObject().put(
                "owner_facts",
                JSONObject().put(
                    "records",
                    JSONArray()
                        .put(
                            JSONObject().put("fact_id", "f1").put("subject", "van").put("predicate", "branch")
                                .put("value", "main").put("authority", "PROJECT_TRUTH").put("source_trust", "TRUSTED_OWNER_FILE")
                                .put("scope", "project:van").put("valid_from_ms", 1L).put("observed_at_ms", 1L)
                                .put("confidence_permille", 1000).put("valid_until_ms", JSONObject.NULL),
                        )
                        .put(
                            JSONObject().put("fact_id", "f2").put("subject", "OWNER").put("predicate", "coffee_order")
                                .put("value", "flat white").put("authority", "CANONICAL_OWNER").put("source_trust", "OWNER_EXPLICIT")
                                .put("scope", "global").put("valid_from_ms", 1L).put("observed_at_ms", 1L)
                                .put("confidence_permille", 1000).put("valid_until_ms", JSONObject.NULL),
                        ),
                ),
            ),
        )
        val facts = MemoryReadModel.parseExportFacts(export)
        val detail = ProjectDetailBuilder.build("van", truth(), emptyList(), emptyList(), emptyList(), facts)
        assertEquals(listOf("f1"), detail.relevantFacts.map { it.factId })
    }
}
