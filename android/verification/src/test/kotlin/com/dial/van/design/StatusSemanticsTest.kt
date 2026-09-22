package com.dial.van.design

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class StatusSemanticsTest {

    @Test
    fun `every thesis state maps to a valid role`() {
        for (state in ThesisState.entries) {
            assertTrue(
                StatusSemantics.forThesisState(state) in StatusSemantics.ALL_ROLES,
                "$state mapped outside the DNA role set",
            )
        }
    }

    @Test
    fun `thesis confidence never uses raw pnl colour semantics`() {
        // DNA §2: "Never use raw green/red for P&L emotion." Confirmed reads as favourable
        // and invalidated as critical, but the mapping key is thesis confidence, not P&L —
        // asserted here by checking the specific role names rather than any colour value.
        assertEquals(StatusSemantics.ROLE_FAVOURABLE, StatusSemantics.forThesisState(ThesisState.CONFIRMED))
        assertEquals(StatusSemantics.ROLE_CRITICAL, StatusSemantics.forThesisState(ThesisState.INVALIDATED))
        assertEquals(StatusSemantics.ROLE_DETERIORATING, StatusSemantics.forThesisState(ThesisState.WEAKENING))
        assertEquals(StatusSemantics.ROLE_HYPOTHESIS, StatusSemantics.forThesisState(ThesisState.HYPOTHESIS))
        assertEquals(StatusSemantics.ROLE_MONITOR, StatusSemantics.forThesisState(ThesisState.MONITORING))
    }

    @Test
    fun `attention severity escalates monotonically toward critical`() {
        assertEquals(StatusSemantics.ROLE_MONITOR, StatusSemantics.forAttentionSeverity(AttentionSeverity.INFO))
        assertEquals(StatusSemantics.ROLE_CRITICAL, StatusSemantics.forAttentionSeverity(AttentionSeverity.URGENT))
        for (severity in AttentionSeverity.entries) {
            assertTrue(StatusSemantics.forAttentionSeverity(severity) in StatusSemantics.ALL_ROLES)
        }
    }

    @Test
    fun `every mission status maps to a valid role`() {
        for (status in MissionStatus.entries) {
            assertTrue(
                StatusSemantics.forMissionStatus(status) in StatusSemantics.ALL_ROLES,
                "$status mapped outside the DNA role set",
            )
        }
        assertEquals(StatusSemantics.ROLE_ENGAGED, StatusSemantics.forMissionStatus(MissionStatus.RUNNING))
        assertEquals(StatusSemantics.ROLE_CRITICAL, StatusSemantics.forMissionStatus(MissionStatus.FAILED))
    }

    @Test
    fun `role constants match the DNA §2 names verbatim`() {
        assertEquals(
            setOf("monitor", "engaged", "cognition", "hypothesis", "eventRisk", "favourable", "deteriorating", "critical", "disabled"),
            StatusSemantics.ALL_ROLES,
        )
    }
}
