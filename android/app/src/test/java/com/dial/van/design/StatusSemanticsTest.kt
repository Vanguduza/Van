package com.dial.van.design

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StatusSemanticsTest {

    @Test
    fun `every thesis state maps to a valid role`() {
        for (state in ThesisState.values()) {
            assertTrue(StatusSemantics.forThesisState(state) in StatusSemantics.ALL_ROLES)
        }
    }

    @Test
    fun `confirmed thesis reads favourable, invalidated reads critical`() {
        assertEquals(StatusSemantics.ROLE_FAVOURABLE, StatusSemantics.forThesisState(ThesisState.CONFIRMED))
        assertEquals(StatusSemantics.ROLE_CRITICAL, StatusSemantics.forThesisState(ThesisState.INVALIDATED))
    }

    @Test
    fun `urgent attention reads critical`() {
        assertEquals(StatusSemantics.ROLE_CRITICAL, StatusSemantics.forAttentionSeverity(AttentionSeverity.URGENT))
    }

    @Test
    fun `every mission status maps to a valid role`() {
        for (status in MissionStatus.values()) {
            assertTrue(StatusSemantics.forMissionStatus(status) in StatusSemantics.ALL_ROLES)
        }
    }
}
