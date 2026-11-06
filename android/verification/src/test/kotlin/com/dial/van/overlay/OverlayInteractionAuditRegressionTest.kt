package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class OverlayInteractionAuditRegressionTest {
    @Test fun sameDraftTwoTapOrImeCallbacksRecordOnlyOneOwnerMessage() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("run this"); var calls = 0
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED, g.submit("run this", lease, false) { calls++; true })
        assertEquals(OverlaySubmissionGuard.Result.DUPLICATE, g.submit("run this", lease, false) { calls++; true })
        assertEquals(1, calls)
    }
    @Test fun draftEditedBeforeOldCallbackCannotSubmitPreviousText() {
        val g = OverlaySubmissionGuard(); val stale = g.observe("old")
        g.observe("new")
        assertEquals(OverlaySubmissionGuard.Result.STALE, g.submit("old", stale, false) { error("must not submit") })
    }
    @Test fun sameTextCanBeDeliberatelySentAgainAfterClearAndRetype() {
        val g = OverlaySubmissionGuard(); val first = g.observe("hello")
        g.submit("hello", first, false) { true }; g.observe("")
        val second = g.observe("hello")
        assertTrue(second > first)
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED, g.submit("hello", second, false) { true })
    }
    @Test fun busyCannotConsumeOrDiscardAnEditedDraft() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("keep this")
        assertEquals(OverlaySubmissionGuard.Result.BUSY, g.submit("keep this", lease, true) { error("must not submit") })
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED, g.submit("keep this", lease, false) { true })
    }
    @Test fun whitespaceDraftHasNoEffect() {
        val g = OverlaySubmissionGuard(); val lease = g.observe(" \n\t")
        assertEquals(OverlaySubmissionGuard.Result.EMPTY, g.submit(" \n\t", lease, false) { error("must not submit") })
    }
    @Test fun onlyTrimmedActualTextReachesTheExistingCommandOwner() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("  exact question \n")
        var observed = ""
        g.submit("  exact question \n", lease, false) { observed = it; true }
        assertEquals("exact question", observed)
    }
    @Test fun synchronousRecordingFailureLeavesDraftRetryableButDoesNotAutoRetry() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("ask")
        var calls = 0
        assertEquals(OverlaySubmissionGuard.Result.NOT_RECORDED, g.submit("ask", lease, false) { calls++; false })
        assertEquals(1, calls)
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED, g.submit("ask", lease, false) { calls++; true })
        assertEquals(2, calls)
    }
    @Test fun synchronousExceptionReleasesOnlyTheLocalDraftLease() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("ask")
        assertFailsWith<IllegalStateException> { g.submit("ask", lease, false) { error("before local record") } }
        assertEquals(OverlaySubmissionGuard.Result.LOCALLY_RECORDED, g.submit("ask", lease, false) { true })
    }
    @Test fun unchangedCompositionDoesNotGrantAnotherSubmission() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("ask")
        g.submit("ask", lease, false) { true }
        repeat(100) { assertEquals(lease, g.observe("ask")) }
        assertEquals(OverlaySubmissionGuard.Result.DUPLICATE, g.submit("ask", lease, false) { true })
    }
    @Test fun differentLeaseCannotClaimTheCurrentText() {
        val g = OverlaySubmissionGuard(); val lease = g.observe("ask")
        assertEquals(OverlaySubmissionGuard.Result.STALE, g.submit("ask", lease + 1, false) { error("not observed") })
    }
    @Test fun boundedAccessibleMovesReachTheSameSafeEdgesAsDrag() {
        val screen = OverlayScreen(1080, 2400, 16, 70, 1064, 2320)
        val size = OverlaySize(184, 184)
        val left = OverlayAccessibleMovement.target(OverlayPlacement(20, 80), size, screen, OverlayMoveDirection.LEFT, 144, null)
        assertEquals(16, left.x)
        val right = OverlayAccessibleMovement.target(OverlayPlacement(1000, 80), size, screen, OverlayMoveDirection.RIGHT, 144, null)
        assertEquals(880, right.x)
        val up = OverlayAccessibleMovement.target(OverlayPlacement(100, 80), size, screen, OverlayMoveDirection.UP, 144, null)
        assertEquals(70, up.y)
    }
    @Test fun accessibleMoveRespectsTheKeyboardWithoutTriggeringDismiss() {
        val screen = OverlayScreen(1080, 2400, 0, 70, 1080, 2320)
        val result = OverlayAccessibleMovement.target(OverlayPlacement(500, 1300), OverlaySize(320, 292), screen, OverlayMoveDirection.DOWN, 500, 1600)
        assertTrue(result.y + 292 <= 1600)
        assertEquals(500, result.x)
    }
    @Test fun accessibleMovementDoesNotOverflowOnExtremeCoordinates() {
        val screen = OverlayScreen(400, 800)
        for (direction in OverlayMoveDirection.entries) {
            val result = OverlayAccessibleMovement.target(OverlayPlacement(Int.MAX_VALUE, Int.MAX_VALUE), OverlaySize(184, 184), screen, direction, Int.MAX_VALUE, null)
            assertTrue(result.x in 0..216); assertTrue(result.y in 0..616)
        }
    }
    @Test fun largeWorkboardOnTinyScreenStaysAtReachableSafeOrigin() {
        val screen = OverlayScreen(200, 250, 10, 20, 190, 220)
        val result = OverlayAccessibleMovement.target(OverlayPlacement(500, 500), OverlaySize(380, 520), screen, OverlayMoveDirection.DOWN, 48, 100)
        assertEquals(OverlayPlacement(10, 20), result)
    }
    @Test fun keyboardBackThenBoardBackNeverMeansCancelProviderWork() {
        assertEquals(OverlayDismissStep.HIDE_KEYBOARD, OverlayUsabilityPolicy.dismiss(true, true))
        assertEquals(OverlayDismissStep.RETURN_TO_CHARACTER, OverlayUsabilityPolicy.dismiss(true, false))
        assertEquals(OverlayDismissStep.NONE, OverlayUsabilityPolicy.dismiss(false, true))
    }
    @Test fun stoppedVoiceLabelNeverClaimsTaskCancellation() {
        val text = OverlayUsabilityPolicy.voiceStatus(false, false, false)
        assertEquals("Microphone off", text)
        assertFalse(text.contains("cancel", true))
    }
}
