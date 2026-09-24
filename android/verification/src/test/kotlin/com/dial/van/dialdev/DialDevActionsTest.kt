package com.dial.van.dialdev

import com.dial.van.design.StatusSemantics
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertIs
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/** VAN-DEV-009 — `VAN-DEVCC-R1` §3.3 / §5: typed actions, no optimistic success, STALE_VIEW. */
class DialDevActionsTest {

    private val target = DialDevActionTarget(projectId = "dial-development-system", taskId = "HOT-DU-021")

    @Test
    fun `every action carries an idempotency key and the revision it was decided against`() {
        val request = DialDevActionRequest.build(DialDevActionKind.PAUSE_TASK_SAFE, target, emptyMap(), "sha256:r1", "key-1")!!
        val body = request.toJson()
        assertEquals("PAUSE_TASK_SAFE", body.getString("action"))
        assertEquals("key-1", body.getString("idempotency_key"))
        assertEquals("sha256:r1", body.getString("expected_projection_revision"))
        assertEquals("HOT-DU-021", body.getJSONObject("target").getString("task_id"))
        assertEquals("dial-development-system", body.getJSONObject("target").getString("project_id"))
        assertFalse(body.getJSONObject("target").has("workspace_id"), "a blank target field is omitted, not sent empty")
    }

    @Test
    fun `no revision on screen means no action, which is also why nothing is queued offline`() {
        assertNull(DialDevActionRequest.build(DialDevActionKind.PAUSE_TASK_SAFE, target, emptyMap(), null, "k"))
        assertNull(DialDevActionRequest.build(DialDevActionKind.PAUSE_TASK_SAFE, target, emptyMap(), "  ", "k"))
        assertNull(DialDevActionRequest.build(DialDevActionKind.PAUSE_TASK_SAFE, target, emptyMap(), "sha256:r1", ""))
    }

    @Test
    fun `a steer needs guidance and a decision needs approve or reject`() {
        assertNull(DialDevActionRequest.build(DialDevActionKind.STEER_TASK, target, emptyMap(), "r", "k"))
        assertNotNull(DialDevActionRequest.build(DialDevActionKind.STEER_TASK, target, mapOf("guidance" to "prefer the lease fix"), "r", "k"))
        assertNull(DialDevActionRequest.build(DialDevActionKind.DECIDE, target, mapOf("decision" to "maybe"), "r", "k"))
        assertNotNull(DialDevActionRequest.build(DialDevActionKind.DECIDE, target, mapOf("decision" to "reject", "reason" to "no"), "r", "k"))
    }

    @Test
    fun `202 is ACCEPTED and pending, never done, even if the forwarder says APPLIED`() {
        val accepted = DialDevActionReducer.onResponse(202, """{"action_id":"A1","state":"ACCEPTED"}""")
        assertEquals(DialDevActionStatus.Accepted("A1"), accepted)
        assertTrue(DialDevActionReducer.isPending(accepted))
        assertEquals("Pause safely · ACCEPTED · pending", DialDevActionReducer.caption(DialDevActionKind.PAUSE_TASK_SAFE, accepted))
        assertIs<DialDevActionStatus.Accepted>(DialDevActionReducer.onResponse(202, """{"action_id":"A1","state":"APPLIED"}"""))
    }

    @Test
    fun `only the projection moves an accepted action, and only for its own id`() {
        val accepted = DialDevActionStatus.Accepted("A1")
        assertEquals(accepted, DialDevActionReducer.reconcile(accepted, listOf(ProjectedAction("A2", "APPLIED", null))))
        assertEquals(accepted, DialDevActionReducer.reconcile(accepted, listOf(ProjectedAction("A1", "ACCEPTED", null))))
        assertEquals(DialDevActionStatus.Applied("A1"), DialDevActionReducer.reconcile(accepted, listOf(ProjectedAction("A1", "APPLIED", null))))
        assertEquals(
            DialDevActionStatus.Rejected("A1", "lease already revoked"),
            DialDevActionReducer.reconcile(accepted, listOf(ProjectedAction("A1", "REJECTED", "lease already revoked"))),
        )
        assertEquals(DialDevActionStatus.Superseded("A1"), DialDevActionReducer.reconcile(accepted, listOf(ProjectedAction("A1", "SUPERSEDED", null))))
    }

    @Test
    fun `a settled action is not moved again by a later projection`() {
        val rejected = DialDevActionStatus.Rejected("A1", "no")
        assertEquals(rejected, DialDevActionReducer.reconcile(rejected, listOf(ProjectedAction("A1", "APPLIED", null))))
    }

    @Test
    fun `409 is STALE_VIEW carrying the new revision, and its retry is a new decision`() {
        val stale = DialDevActionReducer.onResponse(409, """{"error":"STALE_VIEW","projection_revision":"sha256:r2"}""")
        assertEquals(DialDevActionStatus.StaleView("sha256:r2"), stale)
        assertEquals(DialDevActionReducer.RetryMode.NEW_KEY, DialDevActionReducer.retry(stale))
        assertFalse(DialDevActionReducer.isPending(stale))
        val nested = DialDevActionReducer.onResponse(409, """{"detail":{"error":"STALE_VIEW","projection_revision":"sha256:r3"}}""")
        assertEquals(DialDevActionStatus.StaleView("sha256:r3"), nested)
    }

    @Test
    fun `an unconfirmed send retries with the same key so DIAL cannot apply it twice`() {
        assertEquals(DialDevActionReducer.RetryMode.SAME_KEY, DialDevActionReducer.retry(DialDevActionStatus.Unconfirmed("dropped")))
        assertEquals(DialDevActionReducer.RetryMode.NONE, DialDevActionReducer.retry(DialDevActionStatus.Accepted("A1")))
    }

    @Test
    fun `a rejection shows its reason inline`() {
        val rejected = DialDevActionReducer.onResponse(202, """{"action_id":"A9","state":"REJECTED","reason":"task already complete"}""")
        assertEquals("Revoke · rejected: task already complete", DialDevActionReducer.caption(DialDevActionKind.REVOKE_TASK, rejected))
        assertEquals(StatusSemantics.ROLE_CRITICAL, DialDevActionReducer.role(rejected))
    }

    @Test
    fun `no action caption ever claims a pass`() {
        val all = listOf(
            DialDevActionStatus.Submitting, DialDevActionStatus.Accepted("A"), DialDevActionStatus.Applied("A"),
            DialDevActionStatus.Rejected("A", "r"), DialDevActionStatus.Superseded("A"), DialDevActionStatus.StaleView(null),
            DialDevActionStatus.NotSent("x"), DialDevActionStatus.Unconfirmed("y"),
        )
        for (kind in DialDevActionKind.entries) for (status in all) {
            val caption = DialDevActionReducer.caption(kind, status)
            assertFalse(caption.contains("Passed", ignoreCase = true), caption)
            assertFalse(caption.contains("done", ignoreCase = true), caption)
            assertTrue(DialDevActionReducer.role(status) != StatusSemantics.ROLE_FAVOURABLE, "$status must not read favourable")
        }
    }

    @Test
    fun `revoke and reject are destructive, everything else is not`() {
        assertTrue(DialDevActionPolicy.isDestructive(DialDevActionKind.REVOKE_TASK))
        assertTrue(DialDevActionPolicy.isDestructive(DialDevActionKind.DECIDE, mapOf("decision" to "reject")))
        assertFalse(DialDevActionPolicy.isDestructive(DialDevActionKind.DECIDE, mapOf("decision" to "approve")))
        val others = DialDevActionKind.entries - setOf(DialDevActionKind.REVOKE_TASK, DialDevActionKind.DECIDE)
        for (kind in others) assertFalse(DialDevActionPolicy.isDestructive(kind), "$kind")
    }

    @Test
    fun `the projection's actions list parses and ignores rows without an id`() {
        val data = JSONObject("""{"actions":[{"action_id":"A1","state":"APPLIED"},{"state":"APPLIED"},{"action_id":"A2","state":"REJECTED","reason":"stale"}]}""")
        assertEquals(
            listOf(ProjectedAction("A1", "APPLIED", null), ProjectedAction("A2", "REJECTED", "stale")),
            DialDevActionReducer.parseProjected(data),
        )
    }

    @Test
    fun `the revoke consequence prefers DIAL's own sentence and otherwise says what it does not know`() {
        assertEquals("DIAL says X", DialDevConsequence.revoke("T1", "L-207", 3, "DIAL says X"))
        assertEquals(
            "Revokes lease L-207 and stops T1's terminal; 3 uncommitted files in the worktree will be quarantined. DIAL decides whether this applies.",
            DialDevConsequence.revoke("T1", "L-207", 3, null),
        )
        val unknown = DialDevConsequence.revoke("T1", null, null, null)
        assertTrue(unknown.contains("did not report its id"))
        assertTrue(unknown.contains("did not report how many uncommitted files"))
    }
}
