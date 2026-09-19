package com.dial.van.mission

import com.dial.van.status.OwnerWorkStatus
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * The owner-facing read model, P0-EXEC-003 and P2-COH-001.
 *
 * Two things had to be true and were not: the screen must show the gateway's own
 * projection rather than re-deriving one, and a state this build does not know must not be
 * shown to the owner as if it were an answer.
 */
class MissionSummaryTest {

    private fun summary(vararg pairs: Pair<String, Any?>): MissionSummary {
        val json = JSONObject().put("mission_id", "msn_1")
        pairs.forEach { (k, v) -> if (v != null) json.put(k, v) }
        return MissionParsing.missionSummary(json)
    }

    @Test
    fun theGatewaysProjectionIsPreferredOverTheLocalTable() {
        // The gateway knows states this build may not; deferring to it is the point.
        val mission = summary("state" to "SOMETHING_NEW", "owner_status" to "WAITING_ON_YOU")
        assertEquals(OwnerWorkStatus.WAITING_ON_YOU, mission.ownerStatus)
    }

    @Test
    fun anOlderGatewayFallsBackToTheLocalTableNotToUnknown() {
        val mission = summary("state" to "RUNNING")
        assertEquals(OwnerWorkStatus.WORKING, mission.ownerStatus)
    }

    @Test
    fun anUnknownStateWithNoGatewayProjectionIsUnknown() {
        val mission = summary("state" to "SOMETHING_NEW")
        assertEquals(OwnerWorkStatus.UNKNOWN, mission.ownerStatus)
        assertTrue(mission.needsAttention)
    }

    @Test
    fun anUnknownGatewayProjectionNameDoesNotCrashOrGuess() {
        val mission = summary("state" to "RUNNING", "owner_status" to "NOT_A_STATUS")
        // Falls through to the local table rather than throwing or inventing a status.
        assertEquals(OwnerWorkStatus.WORKING, mission.ownerStatus)
    }

    @Test
    fun anUnknownStateIsNotLabelledWithTheRawEnum() {
        val mission = summary("state" to "SOMETHING_NEW")
        assertEquals("VAN does not know the state of this", mission.ownerReadableStatus)
        assertFalse(mission.ownerReadableStatus.contains("SOMETHING_NEW"))
    }

    @Test
    fun theThreePostExecutionOutcomesRemainThreeDifferentSentences() {
        val sentences = listOf("VERIFIED_SUCCESS", "PARTIAL_SUCCESS", "UNVERIFIABLE")
            .map { summary("state" to it).ownerReadableStatus }
        assertEquals(3, sentences.toSet().size)
    }

    @Test
    fun aVerifiedMissionNeedsNoAttentionAndAnUnverifiableOneDoes() {
        assertFalse(summary("state" to "VERIFIED_SUCCESS").needsAttention)
        assertTrue(summary("state" to "UNVERIFIABLE").needsAttention)
        assertTrue(summary("state" to "PARTIAL_SUCCESS").needsAttention)
    }

    @Test
    fun aWaitingMissionIsNotCountedAsActive() {
        // Showing a blocked mission as working misrepresents what VAN is doing.
        assertFalse(summary("state" to "WAITING_FOR_OWNER").isActive)
        assertTrue(summary("state" to "RUNNING").isActive)
    }

    @Test
    fun aRunningMissionNamesItsPhaseWhenItHasOne() {
        assertEquals(
            "Working: drafting",
            summary("state" to "RUNNING", "current_phase" to "drafting").ownerReadableStatus,
        )
    }

    @Test
    fun everyMissionStateTheGatewayCanSendHasItsOwnSentence() {
        val states = listOf(
            "CAPTURED", "UNDERSTOOD", "PLANNED", "AUTHORIZED", "RUNNING", "WAITING_EXTERNAL",
            "WAITING_FOR_OWNER", "RESUME_AUTHORIZED", "VERIFYING", "VERIFIED_SUCCESS",
            "PARTIAL_SUCCESS", "FAILED", "CANCELLED", "EXPIRED", "BLOCKED_POLICY",
            "BLOCKED_UNSAFE", "UNVERIFIABLE",
        )
        val unknownSentence = "VAN does not know the state of this"
        for (state in states) {
            val shown = summary("state" to state).ownerReadableStatus
            assertTrue(shown.isNotBlank(), "$state has no sentence")
            assertTrue(shown != unknownSentence, "$state fell through to the unknown label")
        }
    }
}
