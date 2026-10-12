package com.dial.van.muse

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MuseInteractionProtocolTest {
    private fun prompt(now: Long) = MuseApprovalFence(
        approvalId = "approval-1",
        sessionId = "session-1",
        taskId = "muse-job-1",
        projectId = "van",
        actionFingerprint = "a".repeat(64),
        controlGeneration = 3L,
        revision = 5L,
        expiresAtEpochMs = now + 1000L,
        state = "AWAITING_OWNER",
        allowed = setOf(MuseDecision.ALLOW_ONCE, MuseDecision.DENY),
    )

    @Test fun exactLivePromptMayOfferAllowOnceAndDeny() {
        val now = 10_000L
        assertTrue(prompt(now).canAct(MuseDecision.ALLOW_ONCE, now, true))
        assertTrue(prompt(now).canAct(MuseDecision.DENY, now, true))
    }

    @Test fun staleOrChangedPromptRefuses() {
        val now = 10_000L
        assertFalse(prompt(now).canAct(MuseDecision.ALLOW_ONCE, now, false))
        assertFalse(prompt(now).copy(state = "RESOLVED").canAct(MuseDecision.DENY, now, true))
        assertFalse(prompt(now).copy(controlGeneration = 0L).canAct(MuseDecision.ALLOW_ONCE, now, true))
        assertFalse(prompt(now).copy(revision = 0L).canAct(MuseDecision.ALLOW_ONCE, now, true))
        assertFalse(prompt(now).copy(actionFingerprint = "not-a-digest").canAct(MuseDecision.ALLOW_ONCE, now, true))
        assertFalse(prompt(now).canAct(MuseDecision.ALLOW_ONCE, now + 1001L, true))
    }

    @Test fun onlyProviderOfferedChoiceCanBeSelected() {
        val now = 10_000L
        val denyOnly = prompt(now).copy(allowed = setOf(MuseDecision.DENY))
        assertTrue(denyOnly.canAct(MuseDecision.DENY, now, true))
        assertFalse(denyOnly.canAct(MuseDecision.ALLOW_ONCE, now, true))
    }

    @Test fun freshnessRequiresAllSourcesAndNoClockRegression() {
        val source = MuseSourceHealth(true, true, true, 1000L)
        assertTrue(source.fresh(91_000L))
        assertFalse(source.fresh(91_001L))
        assertFalse(source.fresh(999L))
        assertFalse(source.copy(watchdogGreen = false).fresh(1200L))
        assertFalse(source.copy(relayLive = false).fresh(1200L))
        assertFalse(source.copy(lastSourceAtEpochMs = null).fresh(1200L))
    }
}
