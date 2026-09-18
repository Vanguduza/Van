package com.dial.van.mission

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue
import org.json.JSONArray
import org.json.JSONObject

/**
 * Rev 1 §§6, 33, 35, 48 — the owner surfaces read live truth and say so honestly.
 *
 * §48 forbids screens disconnected from live APIs, fake helper text and
 * placeholder counts. The tests that matter here are the ones about what the
 * screen says when the backend's answer is uncomfortable: a mission that
 * finished without a receipt, an inference VAN has not earned the right to act
 * on, a state the owner should not read as progress.
 */
class MissionSurfaceTest {

    private fun mission(
        state: String,
        phase: String? = null,
        terminal: Boolean = false,
        outcome: String? = null,
    ) = MissionParsing.missionSummary(
        JSONObject()
            .put("mission_id", "msn_1")
            .put("title", "Collect statements")
            .put("goal", "collect this month's statements")
            .put("state", state)
            .put("current_phase", phase ?: JSONObject.NULL)
            .put("verification_state", "PENDING")
            .put("is_terminal", terminal)
            .put("final_outcome", outcome ?: JSONObject.NULL)
            .put("updated_at_ms", 1L)
    )

    @Test
    fun ownerReadableStatusDescribesTheOwnersSituationNotTheStateMachine() {
        assertEquals("Waiting for you", mission("WAITING_FOR_OWNER").ownerReadableStatus)
        assertEquals("Working: fetching", mission("RUNNING", phase = "fetching").ownerReadableStatus)
        assertEquals("Done, and checked", mission("VERIFIED_SUCCESS", terminal = true).ownerReadableStatus)
    }

    @Test
    fun unverifiableNeverReadsAsSuccess() {
        // §6 — the distinction between "it finished" and "it worked" has to
        // survive all the way to the screen, or the whole verification chain is
        // decorative.
        val text = mission("UNVERIFIABLE", terminal = true).ownerReadableStatus
        assertEquals("Finished, but Van could not confirm it worked", text)
        assertFalse(text.contains("Done"))
        assertFalse(text.contains("success", ignoreCase = true))
    }

    @Test
    fun partialSuccessIsNotPresentedAsDone() {
        assertEquals("Partly done", mission("PARTIAL_SUCCESS", terminal = true).ownerReadableStatus)
    }

    @Test
    fun aMissionWaitingOnTheOwnerIsNotCountedAsActive() {
        // Showing it as working would misrepresent what Van is actually doing.
        assertFalse(mission("WAITING_FOR_OWNER").isActive)
        assertTrue(mission("RUNNING").isActive)
        assertFalse(mission("VERIFIED_SUCCESS", terminal = true).isActive)
    }

    @Test
    fun absentFieldsStayNullRatherThanBecomingFriendlyDefaults() {
        // §48 — a screen that invents a value for something it did not receive
        // is the placeholder status the blueprint forbids.
        val parsed = mission("CAPTURED")
        assertNull(parsed.currentPhase)
        assertNull(parsed.projectId)
        assertNull(parsed.finalOutcome)
    }

    @Test
    fun aMissionMarkedDoneWithoutAReceiptSaysSoOnTheScreen() {
        val detail = MissionDetail(
            summary = mission("VERIFIED_SUCCESS", terminal = true),
            activities = emptyList(),
            events = emptyList(),
            verification = null,
        )
        assertEquals("Marked done, but no receipt was recorded", detail.verificationSummary)
    }

    @Test
    fun aVerifiedMissionReportsHowMuchEvidenceBackedIt() {
        val detail = MissionDetail(
            summary = mission("VERIFIED_SUCCESS", terminal = true),
            activities = emptyList(),
            events = emptyList(),
            verification = JSONObject()
                .put("status", "VERIFIED")
                .put("evidence_refs", JSONArray().put("provider-readback://nb-1")),
        )
        assertEquals("Checked against 1 piece(s) of evidence", detail.verificationSummary)
    }

    @Test
    fun homeAnswersTheFiveSecondQuestions() {
        // §35 — is Van okay, what is it doing, does it need me.
        val snapshot = HomeSnapshot(
            needsYouCount = 2,
            activeMissions = listOf(mission("RUNNING")),
            waitingMissions = listOf(mission("WAITING_FOR_OWNER")),
            openDecisions = emptyList(),
            degraded = emptyList(),
        )
        assertTrue(snapshot.vanIsOkay)
        assertTrue(snapshot.needsOwner)

        val unwell = snapshot.copy(degraded = listOf("AUTOMATION_FABRIC_UNAVAILABLE"))
        assertFalse(unwell.vanIsOkay)
    }

    @Test
    fun anAutonomyBearingInferenceReadsAsAQuestionNotAFinding() {
        // §64 — VAN noticing something about how the owner delegates must not
        // look like a settled fact it is already acting on.
        val entries = MissionParsing.understandingEntries(
            JSONObject().put(
                "fields",
                JSONObject().put(
                    "delegation_preferences",
                    JSONArray().put(
                        JSONObject()
                            .put("assertion_id", "oca_1")
                            .put("value", "happy for Van to act without asking")
                            .put("state", "CANDIDATE")
                            .put("confidence", 0.7)
                            .put("independent_episodes", 4)
                            .put("autonomy_bearing", true)
                            .put("owner_confirmed", false)
                    )
                )
            )
        )
        val entry = entries.getValue("delegation_preferences").single()
        assertEquals(
            "Van noticed this — it will not act on it unless you confirm",
            entry.ownerReadableState,
        )
    }

    @Test
    fun aConfirmedTraitIsDistinguishedFromOneVanConfirmedItself() {
        fun entry(ownerConfirmed: Boolean) = UnderstandingEntry(
            assertionId = "a", field = "communication_preferences", value = "terse",
            state = "CONFIRMED", confidence = 1.0, independentEpisodes = 3,
            autonomyBearing = false, ownerConfirmed = ownerConfirmed,
        )
        assertEquals("You confirmed this", entry(true).ownerReadableState)
        assertEquals("Van is acting on this", entry(false).ownerReadableState)
    }

    @Test
    fun anAdaptationAwaitingTheOwnerIsSurfacedNotBuried() {
        // §26 — the owner must be able to correct or reject a material change,
        // which starts with being told there is one.
        val view = UnderstandingView(
            fields = emptyMap(),
            sharedVocabulary = JSONArray(),
            cognitiveComplement = JSONArray(),
            recentAdaptation = JSONArray(),
            adaptationAwaitingYou = JSONArray().put(JSONObject().put("change_id", "grow_1")),
        )
        assertTrue(view.hasAdaptationAwaitingOwner)
    }
}
