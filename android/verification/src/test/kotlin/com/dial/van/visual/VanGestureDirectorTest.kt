package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class VanGestureDirectorTest {
    private fun cue(
        id: String,
        action: VanFiniteAction?,
        source: String = "local-ui",
        emitted: Long = 1_000L,
        rev: Long? = null,
        expiry: Long? = 5_000L,
        evidence: VanCueEvidence = VanCueEvidence.LOCAL_UI,
        target: VanCueTarget? = null,
    ) = VanGestureCue(
        source = source, eventId = id, emittedAtMs = emitted, action = action,
        revision = rev, expiresAtMs = expiry, evidence = evidence, target = target,
    )

    private val target = VanCueTarget(
        leftPx = 40f, topPx = 50f, rightPx = 60f, bottomPx = 70f,
        viewportWidthPx = 100f, viewportHeightPx = 100f,
        viewportRevision = 8L, expectedRevision = 8L, ownedAndVisible = true,
    )

    @Test fun existingPanelActionIsPlayableWithoutChangingWireCode() {
        val director = VanGestureDirector()
        val decision = director.submit(cue("a", VanFiniteAction.OPEN_PANEL), VanDurableState.IDLE, 1_000)
        assertEquals(VanCueOutcome.PLAY, decision.outcome)
        assertEquals(13, decision.action?.code)
        assertEquals(VanFiniteAction.OPEN_PANEL, director.activeAt(1_100))
        assertNull(director.activeAt(2_000))
    }

    @Test fun sameEventNeverRestartsGesture() {
        val director = VanGestureDirector()
        val item = cue("same", VanFiniteAction.ACK_NOD)
        assertEquals(VanCueOutcome.PLAY, director.submit(item, VanDurableState.IDLE, 1_000).outcome)
        assertEquals(VanCueOutcome.DUPLICATE, director.submit(item, VanDurableState.IDLE, 1_040).outcome)
    }

    @Test fun concurrentSourcesKeepTheirRevisionNamespaces() {
        val director = VanGestureDirector()
        director.submit(cue("one", VanFiniteAction.HELLO_WAVE, source = "a", rev = 10), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.PLAY,
            director.submit(cue("two", VanFiniteAction.CAUTION, source = "b", rev = 1), VanDurableState.URGENT, 1_001).outcome,
        )
    }

    @Test fun oldRevisionCannotReplayAfterNewOne() {
        val director = VanGestureDirector()
        director.submit(cue("rev12", VanFiniteAction.OPEN_PANEL, rev = 12), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.STALE_REVISION,
            director.submit(cue("rev11", VanFiniteAction.CLOSE_PANEL, rev = 11), VanDurableState.IDLE, 1_500).outcome,
        )
    }

    @Test fun twoDifferentEventsAtOneRevisionAreNotTreatedAsOneEvent() {
        val director = VanGestureDirector()
        director.submit(cue("first", VanFiniteAction.OPEN_PANEL, rev = 12), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.PLAY,
            director.submit(cue("second", VanFiniteAction.CLOSE_PANEL, rev = 12), VanDurableState.IDLE, 1_300).outcome,
        )
    }

    @Test fun expiredOrFutureCuesNeverAnimate() {
        val director = VanGestureDirector()
        assertEquals(
            VanCueOutcome.EXPIRED,
            director.submit(cue("late", VanFiniteAction.HELLO_WAVE, expiry = 1_100), VanDurableState.IDLE, 1_101).outcome,
        )
        assertEquals(
            VanCueOutcome.EXPIRED,
            director.submit(cue("future", VanFiniteAction.HELLO_WAVE, emitted = 1_300), VanDurableState.IDLE, 1_000).outcome,
        )
    }

    @Test fun malformedOrMissingSourceIdentityCannotAnimate() {
        val director = VanGestureDirector()
        assertEquals(VanCueOutcome.INVALID_SOURCE, director.submit(cue("", VanFiniteAction.ACK_NOD), VanDurableState.IDLE, 1_000).outcome)
        assertEquals(VanCueOutcome.INVALID_SOURCE, director.submit(cue("x", VanFiniteAction.ACK_NOD, source = ""), VanDurableState.IDLE, 1_000).outcome)
    }

    @Test fun unverifiedSourceCannotCauseSuccessOrCelebration() {
        for (action in listOf(VanFiniteAction.CONFIRM, VanFiniteAction.CELEBRATE, VanFiniteAction.PRESENT_CARD)) {
            val director = VanGestureDirector()
            assertEquals(
                VanCueOutcome.UNVERIFIED_RESULT,
                director.submit(cue("unverified", action, evidence = VanCueEvidence.UNVERIFIED), VanDurableState.SUCCESS, 1_000).outcome,
            )
        }
    }

    @Test fun verifiedCompletionCanPresentButNotInCriticalState() {
        val director = VanGestureDirector()
        val done = cue("success", VanFiniteAction.PRESENT_CARD, evidence = VanCueEvidence.VERIFIED_SOURCE)
        assertEquals(VanCueOutcome.PLAY, director.submit(done, VanDurableState.SUCCESS, 1_000).outcome)
        assertEquals(
            VanCueOutcome.CRITICAL_STATE,
            VanGestureDirector().submit(done, VanDurableState.WAITING_FOR_OWNER, 1_000).outcome,
        )
    }

    @Test fun urgentCautionInterruptsEvenDuringWaveAnticipation() {
        val director = VanGestureDirector()
        director.submit(cue("wave", VanFiniteAction.HELLO_WAVE), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.PLAY,
            director.submit(cue("alert", VanFiniteAction.CAUTION, source = "attention"), VanDurableState.URGENT, 1_001).outcome,
        )
        assertEquals(VanFiniteAction.CAUTION, director.activeAt(1_002))
    }

    @Test fun quietGestureDoesNotOverrideCriticalAction() {
        val director = VanGestureDirector()
        director.submit(cue("alert", VanFiniteAction.CAUTION), VanDurableState.URGENT, 1_000)
        assertEquals(
            VanCueOutcome.CRITICAL_STATE,
            director.submit(cue("wave", VanFiniteAction.HELLO_WAVE), VanDurableState.URGENT, 1_300).outcome,
        )
    }

    @Test fun warningCanShrugButOfflineCannotPretendOtherwise() {
        assertEquals(
            VanCueOutcome.PLAY,
            VanGestureDirector().submit(cue("uncertain", VanFiniteAction.SHRUG), VanDurableState.WARNING, 1_000).outcome,
        )
        assertEquals(
            VanCueOutcome.CRITICAL_STATE,
            VanGestureDirector().submit(cue("off", VanFiniteAction.SHRUG), VanDurableState.OFFLINE, 1_000).outcome,
        )
    }

    @Test fun ordinaryGestureWaitsForAnExistingAnticipation() {
        val director = VanGestureDirector()
        director.submit(cue("one", VanFiniteAction.ACK_NOD), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.ANTICIPATION_HELD,
            director.submit(cue("two", VanFiniteAction.OPEN_PANEL), VanDurableState.IDLE, 1_001).outcome,
        )
    }

    @Test fun lowerPriorityGestureCannotPreemptAnImportantGesture() {
        val director = VanGestureDirector()
        director.submit(cue("point", VanFiniteAction.POINT_TARGET, target = target), VanDurableState.WORKING, 1_000)
        assertEquals(
            VanCueOutcome.LOWER_PRIORITY_HELD,
            director.submit(cue("wave", VanFiniteAction.HELLO_WAVE), VanDurableState.WORKING, 1_250).outcome,
        )
    }

    @Test fun pointingMustBeBoundToCurrentVisibleOwnedTarget() {
        for (invalid in listOf(
            null,
            target.copy(ownedAndVisible = false),
            target.copy(expectedRevision = 9L),
            target.copy(rightPx = 150f),
            target.copy(rightPx = 40f),
            target.copy(viewportWidthPx = Float.NaN),
        )) {
            assertEquals(
                VanCueOutcome.INVALID_TARGET,
                VanGestureDirector().submit(cue("point", VanFiniteAction.POINT_TARGET, target = invalid), VanDurableState.WORKING, 1_000).outcome,
            )
        }
    }

    @Test fun pointUsesNormalizedViewportCentre() {
        val d = VanGestureDirector().submit(
            cue("point", VanFiniteAction.POINT_TARGET, target = target), VanDurableState.WORKING, 1_000,
        )
        assertEquals(VanCueOutcome.PLAY, d.outcome)
        assertEquals(0f, d.attention?.first)
        assertEquals(0.20f, requireNotNull(d.attention).second, 0.00001f)
    }

    @Test fun explicitInterruptClearsWithoutChangingDurableState() {
        val director = VanGestureDirector()
        director.submit(cue("one", VanFiniteAction.HELLO_WAVE), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.CLEAR,
            director.submit(cue("interrupt", null), VanDurableState.IDLE, 1_001).outcome,
        )
        assertNull(director.activeAt(1_002))
    }

    @Test fun repeatedSameActionWithoutASecondCompletionDoesNotRestart() {
        val director = VanGestureDirector()
        director.submit(cue("ack-one", VanFiniteAction.ACK_NOD), VanDurableState.IDLE, 1_000)
        assertEquals(
            VanCueOutcome.DUPLICATE,
            director.submit(cue("ack-two", VanFiniteAction.ACK_NOD), VanDurableState.IDLE, 1_300).outcome,
        )
    }

    @Test fun directorHasBoundedHistoryAndReset() {
        val director = VanGestureDirector(recentLimit = 2)
        director.submit(cue("a", VanFiniteAction.ACK_NOD, source = "1", rev = 2), VanDurableState.IDLE, 1_000)
        director.submit(cue("b", null, source = "2", rev = 2), VanDurableState.IDLE, 1_050)
        director.submit(cue("c", null, source = "3", rev = 2), VanDurableState.IDLE, 1_100)
        director.reset()
        assertEquals(
            VanCueOutcome.PLAY,
            director.submit(cue("a", VanFiniteAction.HELLO_WAVE, source = "1", rev = 1), VanDurableState.IDLE, 1_300).outcome,
        )
    }

    @Test fun localPointerCentreAndCornersMapToValidGaze() {
        assertEquals(0f to 0f, VanPointerGaze.fromLocal(50f, 50f, 100f, 100f))
        assertEquals(-1f to -1f, VanPointerGaze.fromLocal(0f, 0f, 100f, 100f))
        assertEquals(1f to 1f, VanPointerGaze.fromLocal(100f, 100f, 100f, 100f))
    }

    @Test fun outsideLocalGestureNodeIsNotAnAuthorizedTarget() {
        assertNull(VanPointerGaze.fromLocal(-1f, 40f, 100f, 100f))
        assertNull(VanPointerGaze.fromLocal(101f, 40f, 100f, 100f))
        assertNull(VanPointerGaze.fromLocal(40f, 101f, 100f, 100f))
    }

    @Test fun badPointerSizesCannotPoisonTheAttentionInputs() {
        assertNull(VanPointerGaze.fromLocal(Float.NaN, 5f, 100f, 100f))
        assertNull(VanPointerGaze.fromLocal(50f, 50f, 0f, 100f))
        assertNull(VanPointerGaze.fromLocal(50f, 50f, Float.POSITIVE_INFINITY, 100f))
    }

    @Test fun originalWireCodesRemainUnchanged() {
        assertEquals((1..14).toList(), VanFiniteAction.entries.map { it.code })
        assertTrue(VanDurableState.entries.map { it.code } == (0..17).toList())
    }
}
