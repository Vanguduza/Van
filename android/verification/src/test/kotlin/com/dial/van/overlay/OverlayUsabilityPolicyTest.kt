package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class OverlayUsabilityPolicyTest {
    @Test fun keyboardDismissalDoesNotCloseTheWorkboardOrDiscardItsDraft() {
        assertEquals(OverlayDismissStep.HIDE_KEYBOARD, OverlayUsabilityPolicy.dismiss(true, true))
    }
    @Test fun secondEscapeReturnsToCharacter() {
        assertEquals(OverlayDismissStep.RETURN_TO_CHARACTER, OverlayUsabilityPolicy.dismiss(true, false))
    }
    @Test fun passiveCharacterDoesNotCaptureAnotherAppsBackKey() {
        assertEquals(OverlayDismissStep.NONE, OverlayUsabilityPolicy.dismiss(false, false))
        assertEquals(OverlayDismissStep.NONE, OverlayUsabilityPolicy.dismiss(false, true))
    }
    @Test fun blankDraftOrInFlightSubmissionCannotSubmitAgain() {
        for (value in listOf("", " ", "\n\t")) assertFalse(OverlayUsabilityPolicy.canSubmit(value, false))
        assertFalse(OverlayUsabilityPolicy.canSubmit("Keep my draft", true))
        assertTrue(OverlayUsabilityPolicy.canSubmit("A new request", false))
    }
    @Test fun micStatusComesFromActualCaptureNotTheSelectedTab() {
        assertEquals("Microphone off", OverlayUsabilityPolicy.voiceStatus(false, false, false))
        assertEquals("Microphone on — listening", OverlayUsabilityPolicy.voiceStatus(true, false, true))
        assertEquals("Processing your voice — microphone is off", OverlayUsabilityPolicy.voiceStatus(false, false, true))
        assertEquals("VAN is speaking", OverlayUsabilityPolicy.voiceStatus(false, true, false))
    }
    @Test fun micRemainsVisibleWhenSpeakingAndListeningOverlap() {
        assertEquals("Microphone on — listening", OverlayUsabilityPolicy.voiceStatus(true, true, true))
    }
    @Test fun controlsFitSmallAndLargeWindowsWithoutHardcodedRightOffsets() {
        for (width in listOf(100f, 180f, 240f, 320f, 400f, 1_200f)) {
            assertTrue(OverlayUsabilityPolicy.quickControlsWidth(width) in 1f..width)
        }
        for (height in listOf(50f, 120f, 260f, 700f)) assertTrue(OverlayUsabilityPolicy.quickControlsHeight(height) in 1f..height)
    }
    @Test fun longLastAnswerScrollsItsMeasuredBottomIntoView() {
        assertEquals(700, OverlayUsabilityPolicy.tailOverflow(0, 1_000, 300))
        assertEquals(0, OverlayUsabilityPolicy.tailOverflow(10, 120, 300))
        assertEquals(80, OverlayUsabilityPolicy.tailOverflow(180, 200, 300))
    }
    @Test fun oversizedOrInvalidTailMetricsCannotOverflowScrollArithmetic() {
        assertEquals(Int.MAX_VALUE, OverlayUsabilityPolicy.tailOverflow(Int.MAX_VALUE, Int.MAX_VALUE, -1))
        assertEquals(0, OverlayUsabilityPolicy.tailOverflow(-100, -50, 300))
    }
    @Test fun invalidMeasurementsDoNotPropagateNaNOrInfinityToCompose() {
        for (value in listOf(Float.NaN, Float.POSITIVE_INFINITY, -100f, 0f)) {
            assertTrue(OverlayUsabilityPolicy.quickControlsWidth(value).isFinite())
            assertTrue(OverlayUsabilityPolicy.quickControlsHeight(value) > 0)
        }
    }
}

class ConversationFollowPolicyTest {
    private fun seeded(): ConversationFollowPolicy = ConversationFollowPolicy().apply { content("last-500", "text", false, false) }
    @Test fun initialLongConversationOpensAtLatestWithoutAnAnimationFromTheTop() {
        assertEquals(ConversationScrollIntent.IMMEDIATE, ConversationFollowPolicy().content("message-500", "long", false, false))
    }
    @Test fun emptyConversationHasNoInvalidScrollTarget() {
        val p = ConversationFollowPolicy(); assertEquals(ConversationScrollIntent.NONE, p.content(null, null, false, false)); assertFalse(p.unread)
    }
    @Test fun newReplyFollowsOnlyWhileAlreadyFollowing() {
        val p = seeded(); assertEquals(ConversationScrollIntent.ANIMATE, p.content("new", "answer", false, false)); assertFalse(p.unread)
    }
    @Test fun streamingSameIdCanFollowUpdatedTextOrStatus() {
        val p = seeded(); assertEquals(ConversationScrollIntent.ANIMATE, p.content("last-500", "more text", false, false))
        assertEquals(ConversationScrollIntent.NONE, p.content("last-500", "more text", false, false))
    }
    @Test fun readingOlderMessagesIsNotInterruptedByNewReplies() {
        val p = seeded(); p.ownerViewport(false, true)
        assertEquals(ConversationScrollIntent.NONE, p.content("new", "answer", false, false)); assertTrue(p.unread); assertFalse(p.following)
    }
    @Test fun contentGrowthIsNotMistakenForOwnerScrolling() {
        val p = seeded(); p.ownerViewport(false, false)
        assertTrue(p.following); assertEquals(ConversationScrollIntent.ANIMATE, p.content("new", "answer", false, false))
    }
    @Test fun ownerScrollingHasPriorityEvenWhenTheyPreviouslyFollowed() {
        val p = seeded(); assertEquals(ConversationScrollIntent.NONE, p.content("new", "answer", false, true)); assertTrue(p.unread)
    }
    @Test fun latestButtonResumesFollowingAndClearsUnreadIndicator() {
        val p = seeded(); p.ownerViewport(false, true); p.content("new", "answer", false, false)
        assertEquals(ConversationScrollIntent.ANIMATE, p.latest()); assertFalse(p.unread); assertTrue(p.following)
    }
    @Test fun scrollToBottomNaturallyClearsUnread() {
        val p = seeded(); p.ownerViewport(false, true); p.content("new", "answer", false, false)
        p.ownerViewport(true, true); assertTrue(p.following); assertFalse(p.unread)
    }
    @Test fun ownNewMessageReturnsToItsConversationTail() {
        val p = seeded(); p.ownerViewport(false, true)
        assertEquals(ConversationScrollIntent.ANIMATE, p.content("my-new-message", "hello", true, false))
    }
    @Test fun sameOwnerMessageEditDoesNotStealTheScrollPosition() {
        val p = seeded(); p.content("owner", "one", true, false); p.ownerViewport(false, true)
        assertEquals(ConversationScrollIntent.NONE, p.content("owner", "two", true, false))
    }
    @Test fun clearAndReopenStartsFresh() {
        val p = seeded(); p.ownerViewport(false, true); p.content(null, null, false, false)
        assertEquals(ConversationScrollIntent.IMMEDIATE, p.content("restored", "answer", false, false))
    }
    @Test fun longBurstNeverPullsAnOwnerAwayFromTheirChosenHistoryPosition() {
        val p = seeded(); p.ownerViewport(false, true)
        repeat(5_000) { assertEquals(ConversationScrollIntent.NONE, p.content("reply-$it", "new", false, false)) }
        assertTrue(p.unread); assertFalse(p.following)
    }
    @Test fun preLayoutViewportDoesNotSuppressInitialRestoration() {
        val p = ConversationFollowPolicy(); p.ownerViewport(false, true)
        assertEquals(ConversationScrollIntent.IMMEDIATE, p.content("latest", "hello", false, false))
    }
}
