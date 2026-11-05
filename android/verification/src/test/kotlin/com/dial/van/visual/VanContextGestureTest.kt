package com.dial.van.visual

import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class VanContextGestureTest {
    private val point = VanCueTarget(60f, 10f, 80f, 30f, 100f, 100f, 1, 1, true)
    private fun cue(id: String, context: VanContextGesture, evidence: VanCueEvidence = VanCueEvidence.LOCAL_UI, target: VanCueTarget? = null) =
        VanGestureCue("context-test", id, 1_000L, context.legacyAction, expiresAtMs = 5_000L, evidence = evidence, target = target, context = context)
    private val binary = "exact compiled candidate bytes".toByteArray()
    private fun manifest(bytes: ByteArray = binary): JSONObject = JSONObject().apply {
        put("schema", "van.character.context/1")
        put("asset_sha256", MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) })
        put("gestures", JSONArray().apply {
            VanContextGesture.entries.forEach { g -> put(JSONObject().apply {
                put("code", g.code); put("name", g.name); put("duration_ms", g.durationMs); put("legacy_action", g.legacyAction.code)
            }) }
        })
    }

    @Test fun existingFourteenWireCodesAreUnchanged() {
        assertEquals((1..14).toList(), VanFiniteAction.entries.map { it.code })
        assertEquals((15..26).toList(), VanContextGesture.entries.map { it.code })
    }
    @Test fun everyContextIsBoundedAndHasAnOriginalFallback() {
        VanContextGesture.entries.forEach { assertTrue(it.durationMs in 600L..1_800L); assertTrue(it.legacyAction.code in 1..14) }
    }
    @Test fun listeningEmphasisRequiresActualListening() {
        val c = cue("listen", VanContextGesture.LISTEN_EMPHASIS)
        assertEquals(VanCueOutcome.INVALID_CONTEXT, VanGestureDirector().submit(c, VanDurableState.IDLE, 1_000).outcome)
        assertEquals(VanCueOutcome.PLAY, VanGestureDirector().submit(c, VanDurableState.LISTENING, 1_000).outcome)
    }
    @Test fun thinkingAndSpeechBehavioursRequireTheirRealState() {
        assertEquals(VanCueOutcome.INVALID_CONTEXT, VanGestureDirector().submit(cue("think", VanContextGesture.THINK_CHIN), VanDurableState.SUCCESS, 1_000).outcome)
        assertEquals(VanCueOutcome.PLAY, VanGestureDirector().submit(cue("explain", VanContextGesture.EXPLAIN_OPEN_PALMS), VanDurableState.SPEAKING, 1_000).outcome)
    }
    @Test fun resultHandoffCannotBeTriggeredByUnverifiedOrLocalOnlyEvidence() {
        for (evidence in listOf(VanCueEvidence.LOCAL_UI, VanCueEvidence.UNVERIFIED)) {
            val d = VanGestureDirector().submit(cue("done", VanContextGesture.HANDOFF_RESULT, evidence), VanDurableState.SUCCESS, 1_000)
            assertFalse(d.accepted)
        }
        val d = VanGestureDirector().submit(cue("done", VanContextGesture.HANDOFF_RESULT, VanCueEvidence.VERIFIED_SOURCE), VanDurableState.SUCCESS, 1_000)
        assertEquals(VanContextGesture.HANDOFF_RESULT, d.context)
    }
    @Test fun guidanceAndInspectionRequireLiveTargets() {
        for (context in listOf(VanContextGesture.INSPECT_TARGET, VanContextGesture.GUIDE_NEXT_STEP)) {
            assertEquals(VanCueOutcome.INVALID_TARGET, VanGestureDirector().submit(cue("bad", context), VanDurableState.ATTENTIVE, 1_000).outcome)
            assertEquals(VanCueOutcome.PLAY, VanGestureDirector().submit(cue("good", context, target = point), VanDurableState.ATTENTIVE, 1_000).outcome)
        }
    }
    @Test fun falseRecoveryDoesNotPretendHealthy() {
        val c = cue("recovered", VanContextGesture.RECOVERY_READY, VanCueEvidence.VERIFIED_SOURCE)
        assertEquals(VanCueOutcome.INVALID_CONTEXT, VanGestureDirector().submit(c, VanDurableState.OFFLINE, 1_000).outcome)
        assertEquals(VanCueOutcome.PLAY, VanGestureDirector().submit(c, VanDurableState.ATTENTIVE, 1_000).outcome)
    }
    @Test fun contextCannotSilenceAnUrgentWarning() {
        for (context in VanContextGesture.entries) {
            assertFalse(VanGestureDirector().submit(cue("urgent", context, VanCueEvidence.VERIFIED_SOURCE, point), VanDurableState.URGENT, 1_000).accepted)
        }
    }
    @Test fun distinctContextsSharingFallbackAreNotMistakenForSameGesture() {
        val d = VanGestureDirector()
        assertEquals(VanCueOutcome.PLAY, d.submit(cue("explain", VanContextGesture.EXPLAIN_OPEN_PALMS), VanDurableState.SPEAKING, 1_000).outcome)
        assertEquals(VanCueOutcome.PLAY, d.submit(cue("compare", VanContextGesture.COMPARE_OPTIONS), VanDurableState.SPEAKING, 1_400).outcome)
    }
    @Test fun contextUsesItsOwnDurationAndThenExpires() {
        val d = VanGestureDirector()
        d.submit(cue("compare", VanContextGesture.COMPARE_OPTIONS), VanDurableState.ATTENTIVE, 1_000)
        assertEquals(VanFiniteAction.ACK_NOD, d.activeAt(2_799))
        assertEquals(null, d.activeAt(2_800))
    }
    @Test fun mismatchedLegacyFallbackIsRefused() {
        val malformed = cue("mismatch", VanContextGesture.THINK_CHIN).copy(action = VanFiniteAction.CELEBRATE)
        assertEquals(VanCueOutcome.INVALID_CONTEXT, VanGestureDirector().submit(malformed, VanDurableState.THINKING, 1_000).outcome)
    }
    @Test fun missingCorruptOrOversizedMetadataFailsClosed() {
        for (value in listOf(null, "not json", "{}", "x".repeat(16_385))) assertTrue(VanRiveContextCapabilities.resolve(binary, value).isEmpty())
    }
    @Test fun contextCapabilityIsBoundToExactLoadedBinary() {
        assertEquals((15..26).toSet(), VanRiveContextCapabilities.resolve(binary, manifest().toString()))
        assertTrue(VanRiveContextCapabilities.resolve("different".toByteArray(), manifest().toString()).isEmpty())
    }
    @Test fun changedCodeNameDurationOrFallbackInvalidatesExtension() {
        for ((key, value) in listOf("code" to 99, "name" to "WRONG", "duration_ms" to 8_000, "legacy_action" to 8)) {
            val m = manifest(); m.getJSONArray("gestures").getJSONObject(0).put(key, value)
            assertTrue(VanRiveContextCapabilities.resolve(binary, m.toString()).isEmpty())
        }
    }
    @Test fun duplicateEntryDoesNotMasqueradeAsFullExtension() {
        val m = manifest(); val rows = m.getJSONArray("gestures"); rows.put(11, rows.getJSONObject(0))
        assertTrue(VanRiveContextCapabilities.resolve(binary, m.toString()).isEmpty())
    }
    @Test fun originalAssetsOnlyReceiveTheirKnownFiniteCodes() {
        val supported = VanRiveContextCapabilities.resolve(binary, manifest().toString())
        for (g in VanContextGesture.entries) {
            assertEquals(g.legacyAction.code, VanRiveContextCapabilities.actionCode(g.legacyAction.code, g.code, emptySet()))
            assertEquals(g.code, VanRiveContextCapabilities.actionCode(g.legacyAction.code, g.code, supported))
            assertEquals(0, VanRiveContextCapabilities.actionCode(0, g.code, supported))
        }
    }
    @Test fun ordinaryStateMappingDoesNotSilentlyEmitExtendedCodes() {
        val frame = VanPresenceFrame(actionCode = VanFiniteAction.ACK_NOD.code, contextCode = VanContextGesture.THINK_CHIN.code)
        val visual = frame.toVisualState()
        assertEquals(2, visual.toRiveInputs()[VanInput.ACTION_CODE])
        assertEquals(17, visual.contextCode)
    }
}
