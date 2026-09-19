package com.dial.van.status

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Finding P0-EXEC-003, device side.
 *
 * The controller's status `when` ended in `else -> ACCEPTED`, so every gateway status it
 * did not know read to the owner as "under way", and it answered three different
 * post-execution outcomes with one word.
 */
class OwnerStatusProjectionTest {

    @Test
    fun anUnknownGatewayStatusIsUnknownNotWorking() {
        // The exact regression: a status added to the gateway after this build shipped.
        assertEquals(OwnerWorkStatus.UNKNOWN, OwnerStatusProjection.fromCommandResult("something_new"))
        assertEquals(OwnerWorkStatus.UNKNOWN, OwnerStatusProjection.fromCommandResult(null))
        assertEquals(OwnerWorkStatus.UNKNOWN, OwnerStatusProjection.fromCommandResult(""))
    }

    @Test
    fun unknownReachesTheOwnerAndIsNotTreatedAsFinished() {
        assertTrue(OwnerStatusProjection.needsOwner(OwnerWorkStatus.UNKNOWN))
        assertFalse(OwnerStatusProjection.isFinished(OwnerWorkStatus.UNKNOWN))
    }

    @Test
    fun acceptedIsNotSuccess() {
        assertEquals(OwnerWorkStatus.WORKING, OwnerStatusProjection.fromCommandResult("accepted"))
        assertFalse(OwnerStatusProjection.isFinished(OwnerWorkStatus.WORKING))
    }

    @Test
    fun theThreePostExecutionOutcomesStayThreeDifferentAnswers() {
        val outcomes = setOf(
            OwnerStatusProjection.fromMissionState("VERIFIED_SUCCESS"),
            OwnerStatusProjection.fromMissionState("PARTIAL_SUCCESS"),
            OwnerStatusProjection.fromMissionState("UNVERIFIABLE"),
        )
        assertEquals(3, outcomes.size, "the controller collapsed all three into FAILED")
    }

    @Test
    fun onlyAVerifiedMissionReadsAsDone() {
        val done = OwnerStatusProjection.missionState.filterValues { it == OwnerWorkStatus.DONE }
        assertEquals(setOf("VERIFIED_SUCCESS"), done.keys)
    }

    @Test
    fun aRefusalIsNotAFailure() {
        assertEquals(OwnerWorkStatus.REFUSED, OwnerStatusProjection.fromCommandResult("denied"))
        assertEquals(OwnerWorkStatus.REFUSED, OwnerStatusProjection.fromCommandResult("rejected_untrusted"))
        assertEquals(OwnerWorkStatus.REFUSED, OwnerStatusProjection.fromMissionState("BLOCKED_POLICY"))
        assertEquals(OwnerWorkStatus.FAILED, OwnerStatusProjection.fromMissionState("FAILED"))
    }

    @Test
    fun caseAndWhitespaceFromTheWireDoNotProduceUnknown() {
        assertEquals(OwnerWorkStatus.WORKING, OwnerStatusProjection.fromCommandResult(" ACCEPTED "))
        assertEquals(OwnerWorkStatus.DONE, OwnerStatusProjection.fromMissionState(" verified_success "))
    }

    @Test
    fun everyStatusHasADistinctSentence() {
        val sentences = OwnerWorkStatus.entries.map { OwnerStatusProjection.sentenceFor(it) }
        assertEquals(OwnerWorkStatus.entries.size, sentences.toSet().size)
        assertTrue(sentences.none { it.isBlank() })
    }

    @Test
    fun everyProjectedValueIsAStatusWithASentence() {
        val projected = OwnerStatusProjection.commandResult.values +
            OwnerStatusProjection.missionState.values
        for (status in projected) {
            assertTrue(OwnerStatusProjection.sentence.containsKey(status), "$status has no sentence")
        }
    }

    @Test
    fun nothingIsBothWorkingAndFinished() {
        assertFalse(OwnerStatusProjection.isFinished(OwnerWorkStatus.WORKING))
        assertFalse(OwnerStatusProjection.isFinished(OwnerWorkStatus.WAITING_ON_YOU))
        assertFalse(OwnerStatusProjection.isFinished(OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE))
    }
}

/**
 * The message status the owner's conversation shows, and its mapping from the owner status.
 */
class VanCommandStatusTest {

    @Test
    fun everyOwnerStatusMapsToAMessageStatus() {
        // The mapping is exhaustive at compile time; this asserts it at runtime too, so a
        // future `else` branch cannot quietly reintroduce a catch-all.
        for (owner in OwnerWorkStatus.entries) {
            commandStatusFor(owner)
        }
    }

    @Test
    fun anUnknownGatewayStatusShowsAsUnknown() {
        assertEquals(
            VanCommandStatus.UNKNOWN,
            commandStatusFor(OwnerStatusProjection.fromCommandResult("a_status_from_the_future")),
        )
    }

    @Test
    fun acceptedShowsAsAcceptedNotSucceeded() {
        assertEquals(
            VanCommandStatus.ACCEPTED,
            commandStatusFor(OwnerStatusProjection.fromCommandResult("accepted")),
        )
    }

    @Test
    fun theThreePostExecutionOutcomesShowAsThreeDifferentThings() {
        val shown = setOf(
            commandStatusFor(OwnerStatusProjection.fromMissionState("VERIFIED_SUCCESS")),
            commandStatusFor(OwnerStatusProjection.fromMissionState("PARTIAL_SUCCESS")),
            commandStatusFor(OwnerStatusProjection.fromMissionState("UNVERIFIABLE")),
        )
        assertEquals(3, shown.size)
        assertTrue(VanCommandStatus.SUCCEEDED in shown)
    }

    @Test
    fun aRefusalDoesNotShowAsAFailure() {
        assertEquals(
            VanCommandStatus.REFUSED,
            commandStatusFor(OwnerStatusProjection.fromCommandResult("denied")),
        )
    }

    @Test
    fun onlyAVerifiedOutcomeShowsAsSucceeded() {
        val succeeded = OwnerWorkStatus.entries.filter {
            commandStatusFor(it) == VanCommandStatus.SUCCEEDED
        }
        assertEquals(listOf(OwnerWorkStatus.DONE), succeeded)
    }
}
