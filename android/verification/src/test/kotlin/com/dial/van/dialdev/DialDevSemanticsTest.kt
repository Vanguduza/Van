package com.dial.van.dialdev

import com.dial.van.design.MissionStatus
import com.dial.van.design.StatusSemantics
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * VAN-DEV-004 / DNA V3 — `VAN-DEVCC-R1` §4, row by row. If DIAL's table changes, this test is
 * where the change has to be made on purpose.
 */
class DialDevSemanticsTest {

    private data class Row(val state: DialDevState, val mission: MissionStatus?, val role: String, val caption: String)

    private val ctx = DialDevCaptionContext(firstBlocker = "HOT-DU-008 lease", harness = "claude-code", model = "opus", external = "Netcup DNS")

    /** §4, verbatim. */
    private val table = listOf(
        Row(DialDevState.NOT_APPLICABLE, null, StatusSemantics.ROLE_DISABLED, "Not applicable"),
        Row(DialDevState.BLOCKED, MissionStatus.WAITING, StatusSemantics.ROLE_DETERIORATING, "Blocked · HOT-DU-008 lease"),
        Row(DialDevState.READY, MissionStatus.WAITING, StatusSemantics.ROLE_MONITOR, "Ready"),
        Row(DialDevState.RUNNING, MissionStatus.RUNNING, StatusSemantics.ROLE_ENGAGED, "Running · claude-code/opus"),
        Row(DialDevState.WAITING_OWNER, MissionStatus.WAITING, StatusSemantics.ROLE_EVENT_RISK, "Needs you"),
        Row(DialDevState.WAITING_EXTERNAL, MissionStatus.WAITING_EXTERNAL, StatusSemantics.ROLE_HYPOTHESIS, "Waiting · Netcup DNS"),
        Row(DialDevState.VERIFYING, MissionStatus.RUNNING, StatusSemantics.ROLE_COGNITION, "Verifying"),
        Row(DialDevState.PASS, MissionStatus.DONE, StatusSemantics.ROLE_FAVOURABLE, "Passed · evidence admitted"),
        Row(DialDevState.FAIL, MissionStatus.FAILED, StatusSemantics.ROLE_CRITICAL, "Failed"),
        Row(DialDevState.INVALIDATED, MissionStatus.FAILED, StatusSemantics.ROLE_DETERIORATING, "Invalidated · plan changed"),
        Row(DialDevState.SUPERSEDED, MissionStatus.DONE, StatusSemantics.ROLE_DISABLED, "Superseded"),
        Row(DialDevState.COMPLETION_CANDIDATE, MissionStatus.RUNNING, StatusSemantics.ROLE_COGNITION, "Claimed done · verifying"),
    )

    @Test
    fun `every row of the section 4 table maps exactly`() {
        for (row in table) {
            val p = DialDevSemantics.present(row.state, ctx)
            assertEquals(row.mission, p.missionStatus, "${row.state} mission status")
            assertEquals(row.role, p.role, "${row.state} role")
            assertEquals(row.caption, p.caption, "${row.state} caption")
        }
    }

    @Test
    fun `the table covers every DIAL state this build knows, and every role is a DNA role`() {
        assertEquals(DialDevState.entries.toSet(), table.map { it.state }.toSet())
        for (state in DialDevState.entries) {
            assertTrue(DialDevSemantics.present(state).role in StatusSemantics.ALL_ROLES, "$state has a non-DNA role")
        }
    }

    @Test
    fun `only NOT_APPLICABLE is hidden from lists`() {
        for (state in DialDevState.entries) {
            assertEquals(state != DialDevState.NOT_APPLICABLE, DialDevSemantics.present(state).visibleInLists, "$state")
        }
    }

    @Test
    fun `a completion candidate never renders as passed`() {
        for (raw in listOf("RUNNING", "VERIFYING", "READY", "COMPLETION_CANDIDATE")) {
            val p = DialDevSemantics.presentRaw(raw, completionCandidate = true)
            assertEquals(DialDevState.COMPLETION_CANDIDATE, p.known?.state, raw)
            assertEquals("Claimed done · verifying", p.caption)
            assertNotEquals(StatusSemantics.ROLE_FAVOURABLE, p.role)
            assertNotEquals(MissionStatus.DONE, p.known?.missionStatus)
            assertFalse(p.caption.contains("Passed"))
        }
    }

    @Test
    fun `only the projection's own PASS reads passed, whatever the candidate flag says`() {
        val admitted = DialDevSemantics.presentRaw("PASS", completionCandidate = true)
        assertEquals(DialDevState.PASS, admitted.known?.state)
        assertEquals("Passed · evidence admitted", admitted.caption)
        val passCaptions = DialDevState.entries.filter { DialDevSemantics.present(it).caption.startsWith("Passed") }
        assertEquals(listOf(DialDevState.PASS), passCaptions)
    }

    @Test
    fun `a terminal or blocked state is not relabelled by the candidate flag`() {
        for (raw in listOf("BLOCKED", "FAIL", "INVALIDATED", "SUPERSEDED", "WAITING_OWNER")) {
            assertEquals(DialDevState.parse(raw), DialDevSemantics.effectiveState(raw, completionCandidate = true), raw)
        }
    }

    @Test
    fun `an unknown state is shown as itself in the disabled role, not guessed`() {
        val p = DialDevSemantics.presentRaw("QUANTUM_LIMBO")
        assertNull(p.known)
        assertEquals(StatusSemantics.ROLE_DISABLED, p.role)
        assertEquals("Unknown state · QUANTUM_LIMBO", p.caption)
        assertTrue(p.visibleInLists)
        assertEquals("Unknown state · not reported", DialDevSemantics.presentRaw(null).caption)
    }

    @Test
    fun `captions drop a detail DIAL did not send rather than inventing one`() {
        assertEquals("Blocked", DialDevSemantics.present(DialDevState.BLOCKED).caption)
        assertEquals("Running", DialDevSemantics.present(DialDevState.RUNNING).caption)
        assertEquals("Running · codex", DialDevSemantics.present(DialDevState.RUNNING, DialDevCaptionContext(harness = "codex")).caption)
        assertEquals("Waiting", DialDevSemantics.present(DialDevState.WAITING_EXTERNAL).caption)
    }

    @Test
    fun `state parsing is case- and space-tolerant but exact on the name`() {
        assertEquals(DialDevState.WAITING_OWNER, DialDevState.parse(" waiting_owner "))
        assertNull(DialDevState.parse("WAITING"))
        assertNull(DialDevState.parse(""))
    }

    @Test
    fun `the smaller vocabularies map onto DNA roles, and unknown words onto disabled`() {
        for (v in DialDevHealth.entries) assertTrue(DialDevRoles.health(v) in StatusSemantics.ALL_ROLES)
        for (v in DialDevLadder.entries) assertTrue(DialDevRoles.ladder(v) in StatusSemantics.ALL_ROLES)
        for (v in DialDevSeverity.entries) assertTrue(DialDevRoles.severity(v) in StatusSemantics.ALL_ROLES)
        for (v in DialDevAdmission.entries) assertTrue(DialDevRoles.admission(v) in StatusSemantics.ALL_ROLES)
        for (v in DialDevResult.entries) assertTrue(DialDevRoles.result(v) in StatusSemantics.ALL_ROLES)
        // Only INTEGRATED is the favourable end of the ladder; a candidate is not admitted evidence.
        assertEquals(listOf(DialDevLadder.INTEGRATED), DialDevLadder.entries.filter { DialDevRoles.ladder(it) == StatusSemantics.ROLE_FAVOURABLE })
        assertNotEquals(StatusSemantics.ROLE_FAVOURABLE, DialDevRoles.admission(DialDevAdmission.CANDIDATE))
        assertEquals(StatusSemantics.ROLE_DISABLED, DialDevRoles.roleOrDisabled(DialDevHealth.parse("sideways"), DialDevRoles::health))
        assertEquals(StatusSemantics.ROLE_DISABLED, DialDevRoles.forAnyState("sideways"))
        assertEquals(StatusSemantics.ROLE_COGNITION, DialDevRoles.forAnyState("COMPLETION_CANDIDATE"))
    }

    @Test
    fun `progress events map onto DNA roles, and a completion candidate event is never favourable`() {
        for (e in DialDevProgressEvent.entries) assertTrue(DialDevRoles.progress(e) in StatusSemantics.ALL_ROLES, "$e")
        assertEquals(StatusSemantics.ROLE_COGNITION, DialDevRoles.progress(DialDevProgressEvent.COMPLETION_CANDIDATE))
        assertTrue(DialDevProgressEvent.entries.none { DialDevRoles.progress(it) == StatusSemantics.ROLE_FAVOURABLE })
        assertEquals(StatusSemantics.ROLE_DISABLED, DialDevRoles.roleOrDisabled(DialDevProgressEvent.parse("TELEPORTED"), DialDevRoles::progress))
    }
}
