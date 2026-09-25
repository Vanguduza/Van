package com.dial.van.dialdev

import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** The read models every development screen renders (VAN-DEV-005…008, 010). */
class DialDevModelsTest {

    @Test
    fun `a task row reads the TODO record and measures heartbeat on DIAL's clock`() {
        val row = DialDevParse.task(
            JSONObject(
                """{"task_id":"HOT-DU-021","title":"Lease index","du":"HOT-DU-021","stage":"STG-07","state":"RUNNING",
                "why_now":"unblocks 3","harness":"claude-code","model":"opus","host":"dial-control",
                "last_heartbeat":"2026-09-23T16:38:00Z","blockers":[{"summary":"lease L-9"}],"planned_next_action":"run tests"}""",
            ),
            observedAt = "2026-09-23T16:40:00Z",
        )!!
        assertEquals(120_000L, row.heartbeatAgeMs)
        assertEquals("lease L-9", row.firstBlocker)
        assertEquals("Running · claude-code/opus", row.presentation.caption)
        assertEquals("run tests", row.nextAction)
    }

    @Test
    fun `a task without a heartbeat has no age, not zero`() {
        val row = DialDevParse.task(JSONObject("""{"task_id":"T","state":"READY"}"""), observedAt = null)!!
        assertNull(row.heartbeatAgeMs)
        assertEquals("—", DialDevFormat.age(row.heartbeatAgeMs))
    }

    @Test
    fun `the completion flag on a task row reads as claimed, not passed`() {
        val row = DialDevParse.task(JSONObject("""{"task_id":"T","state":"VERIFYING","completion_candidate":true}"""), null)!!
        assertEquals("Claimed done · verifying", row.presentation.caption)
    }

    @Test
    fun `home counts DIAL did not send stay null and render as a dash`() {
        val home = DialDevParse.home(JSONObject("""{"counts":{"running":2},"readiness":{"forensic_build_ready":true,"oracle_gate":{"state":"DEVELOPMENT_READY_FALLBACK"},"runtime_slots":{"used":3,"total":4}}}"""), null)
        assertEquals(2, home.counts["running"])
        assertNull(home.counts["blocked"])
        assertEquals("—", DialDevFormat.count(home.counts["blocked"]))
        assertEquals("READY", home.forensicBuildReady)
        assertEquals("DEVELOPMENT_READY_FALLBACK", home.oracleGate)
        assertEquals("3/4", home.runtimeSlots)
    }

    @Test
    fun `home keeps at most five Now rows and three Needs-you items`() {
        val now = (1..8).joinToString(",") { """{"task_id":"T$it","state":"RUNNING"}""" }
        val needs = (1..6).joinToString(",") { """{"title":"N$it","task_id":"T$it"}""" }
        val home = DialDevParse.home(JSONObject("""{"now":[$now],"needs_you":[$needs]}"""), null)
        assertEquals(5, home.now.size)
        assertEquals(3, home.needsYou.size)
    }

    @Test
    fun `the graph is navigable as a list, critical path first`() {
        val graph = DialDevParse.graph(
            JSONObject(
                """{"nodes":[{"task_id":"B","stage":"S1"},{"task_id":"A","stage":"S2"},{"task_id":"C","stage":"S1","critical":true}],
                "edges":[{"from":"C","to":"A"},{"depends_on":"B","task_id":"A"}],"critical_path":["A"]}""",
            ),
        )
        assertEquals(listOf("C", "A", "B"), graph.accessibleOrder().map { it.taskId })
        assertEquals(listOf("C", "B"), graph.dependenciesOf("A"))
        assertEquals(listOf("A"), graph.dependentsOf("C"))
        assertEquals(graph.nodes.size, graph.accessibleOrder().size, "every node is reachable through the list")
    }

    @Test
    fun `the task detail reports an Android verification only when DIAL does`() {
        val with = DialDevParse.taskDetail(JSONObject("""{"task":{"task_id":"T","android_verification":{"suite":"artemis"}}}"""), null)!!
        val without = DialDevParse.taskDetail(JSONObject("""{"task":{"task_id":"T","stage":"STG-12 android"}}"""), null)!!
        assertTrue(with.androidVerification)
        assertFalse(without.androidVerification)
    }

    @Test
    fun `a diff lists files first and splits hunks per file on demand`() {
        val unified = "diff --git a/x.kt b/x.kt\n@@ -1 +1 @@\n-a\n+b\ndiff --git a/y.kt b/y.kt\n@@ -2 +2 @@\n-c\n+d"
        val diff = DialDevFabricParse.diff(JSONObject().put("files", org.json.JSONArray("""[{"path":"x.kt","additions":1,"deletions":1},{"path":"y.kt"}]""")).put("diff", unified))
        assertEquals(listOf("x.kt", "y.kt"), diff.files.map { it.path })
        assertTrue(diff.hunksFor("x.kt")!!.contains("+b"))
        assertFalse(diff.hunksFor("x.kt")!!.contains("+d"))
        assertNull(diff.hunksFor("z.kt"))
        val pathsOnly = DialDevFabricParse.diff(JSONObject("""{"files":[{"path":"big.bin"}],"truncated":true}"""))
        assertTrue(pathsOnly.truncated)
        assertNull(pathsOnly.hunksFor("big.bin"))
    }

    @Test
    fun `a terminal tail marks redacted spans and never shows more than 200 lines`() {
        val lines = (1..250).joinToString(",") { "\"line $it\"" }
        val tail = DialDevFabricParse.terminalTail(JSONObject("""{"lines":[$lines]}"""))
        assertEquals(200, tail.lines.size)
        assertTrue(tail.truncated)
        assertEquals("line 51", tail.lines.first().single().text)

        val marked = DevTerminalTail.spans("export TOKEN=[REDACTED:api_key] done", emptyList())
        assertEquals(listOf(false, true, false), marked.map { it.redacted })
        assertEquals("[REDACTED:api_key]", marked[1].text)

        val ranged = DialDevFabricParse.terminalTail(JSONObject("""{"lines":[{"text":"key=abcdef end","redactions":[{"start":4,"end":10}]}]}"""))
        val spans = ranged.lines.single()
        assertEquals(listOf("key=", "[REDACTED]", " end"), spans.map { it.text })
        assertFalse(spans.joinToString("") { it.text }.contains("abcdef"), "a redacted range is never reconstructed")
    }

    @Test
    fun `overlap warnings are DIAL's when sent, derived and labelled otherwise`() {
        val reported = DialDevFabricParse.agents(JSONObject("""{"agents":[{"actor_id":"a"}],"overlap_warnings":[{"actors":["a","b"],"paths":["src/x"]}]}"""), null)
        assertFalse(reported.overlaps.single().derived)
        val derived = DialDevFabricParse.agents(
            JSONObject("""{"agents":[{"actor_id":"a","intent":{"paths":["src/lease"]}},{"actor_id":"b","intent":{"paths":["src/lease/index.ts"]}},{"actor_id":"c","intent":{"paths":["docs"]}}]}"""),
            null,
        )
        val overlap = derived.overlaps.single()
        assertTrue(overlap.derived)
        assertEquals(listOf("a", "b"), overlap.actors)
        assertEquals(listOf("src/lease"), overlap.paths)
    }

    @Test
    fun `sibling paths that merely share a prefix are not an overlap`() {
        val agents = DialDevFabricParse.agents(
            JSONObject("""{"agents":[{"actor_id":"a","intent":{"paths":["src/lease"]}},{"actor_id":"b","intent":{"paths":["src/leases"]}}]}"""),
            null,
        )
        assertTrue(agents.overlaps.isEmpty())
    }

    @Test
    fun `infrastructure reads the ladder, Orca, manager slots and the Oracle gate`() {
        val infra = DialDevFabricParse.infrastructure(
            JSONObject(
                """{"capabilities":[{"name":"orca","ladder_state":"LIVE_QUALIFIED","version":"1.4.210","pin":"1.4.210"}],
                "orca":{"version":"1.4.210","drift":"none","daemon_scope":"user","bind":"127.0.0.1"},
                "manager_chain":[{"slot":"sol","qualification":"QUALIFIED"}],
                "oracle_gate":{"state":"DEVELOPMENT_READY_FALLBACK","failed_checks":["prod-cert"]},
                "hermes":{"state":"HEALTHY"},"openviking":"DEGRADED"}""",
            ),
        )
        assertEquals(DialDevLadder.LIVE_QUALIFIED, DialDevLadder.parse(infra.capabilities.single().ladder))
        assertEquals("127.0.0.1", infra.orcaBind)
        assertEquals("sol", infra.managerSlots.single().title)
        assertEquals(listOf("prod-cert"), infra.oracleFailedChecks)
        assertEquals(listOf("hermes", "openviking"), infra.health.map { it.subsystem })
    }

    @Test
    fun `evidence keeps admission and the exact command`() {
        val e = DialDevFabricParse.evidence(JSONObject("""{"evidence":{"ref":"EV-1","kind":"test","command":"npm run verify","result":"PASS","admission_state":"CANDIDATE"}}"""))!!
        assertEquals("npm run verify", e.command)
        assertEquals(DialDevAdmission.CANDIDATE, DialDevAdmission.parse(e.admission))
    }

    @Test
    fun `SSE frames dispatch on the blank line and name what changed`() {
        val parser = DialDevSse.Parser()
        assertNull(parser.feed(": keepalive"))
        assertNull(parser.feed("event: projection"))
        assertNull(parser.feed("""data: {"projection_revision":"sha256:r2","changed":["Tasks","workspaces"]}"""))
        val change = parser.feed("")!!
        assertEquals("sha256:r2", change.projectionRevision)
        assertEquals(setOf("tasks", "workspaces"), change.changed)
        assertTrue(DialDevSse.affects(change, setOf("tasks")))
        assertFalse(DialDevSse.affects(change, setOf("reviews")))
        assertTrue(DialDevSse.affects(DialDevChange("r", emptySet()), setOf("reviews")), "an empty change list means refetch everything")
        assertNull(parser.feed(""), "a blank line with no data is not an event")
    }

    @Test
    fun `task views parse to the section 16_3 names and default to Now`() {
        assertEquals(DevTaskView.BLOCKED, DevTaskView.parse("blocked"))
        assertEquals(DevTaskView.NOW, DevTaskView.parse(null))
        assertEquals(DevTaskView.NOW, DevTaskView.parse("everything"))
        assertEquals(
            listOf("now", "next", "in_progress", "needs_me", "blocked", "review", "failed", "completed", "all"),
            DevTaskView.entries.map { it.wire },
        )
    }
}
