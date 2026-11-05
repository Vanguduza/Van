package com.dial.van.visual

import com.dial.van.command.nav.VanRoute
import com.dial.van.voice.VoiceTurnLifecycle
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class VanHardeningEventsTest {
    @Test fun allRegisteredCanonicalRoutesHaveOwnedPresentationContext() {
        val groups=mutableSetOf<VanOwnedScreen>()
        for (template in VanRoute.ALL_TEMPLATES) {
            val args=Regex("\\{(\\w+)\\}").findAll(template).associate { it.groupValues[1] to "fixture-id" }
            val actual=assertNotNull(VanRoute.concreteRoute(template,args),template)
            val group=assertNotNull(VanOwnedScreenContext.classify(actual),actual);groups.add(group)
        }
        assertEquals(VanOwnedScreen.entries.toSet(),groups)
    }
    @Test fun externalAndUnknownScreenNamesCannotPretendOwnedContext() {
        for (route in listOf("", "other-app/home", "https://example.test/home", "com.other.settings", "unknown-screen")) assertNull(VanOwnedScreenContext.classify(route),route)
    }
    @Test fun sensitiveIdentifiersDoNotBecomeBehaviorCommands() {
        assertEquals(VanOwnedScreen.PROJECTS,VanOwnedScreenContext.classify("projects/approve-all"))
        assertEquals(VanOwnedScreen.TASKS,VanOwnedScreenContext.classify("work/missions/execute"))
    }
    @Test fun clearOldScreenCannotRemoveAReplacementScreen() {
        val state=VanScreenLease();state.observe(1,"home");state.observe(2,"memory");state.clear(1)
        assertEquals(VanOwnedScreen.MEMORY,state.screen)
        state.observe(1,"settings");assertEquals(VanOwnedScreen.MEMORY,state.screen)
        state.clear(2);assertNull(state.screen)
    }
    @Test fun onlyInspectingContextsSelectInspectionAndOthersGuide() {
        for (screen in VanOwnedScreen.entries) {
            val result=VanOwnedScreenContext.pointing(screen)
            assertTrue(result.requiresTarget)
            assertTrue(result in setOf(VanContextGesture.INSPECT_TARGET,VanContextGesture.GUIDE_NEXT_STEP))
        }
        assertEquals(VanContextGesture.INSPECT_TARGET,VanOwnedScreenContext.pointing(VanOwnedScreen.RESEARCH))
        assertEquals(VanContextGesture.GUIDE_NEXT_STEP,VanOwnedScreenContext.pointing(null))
    }
    @Test fun actualRefusalIsSeparateFromTimeoutOrUnknownOutcome() {
        for (status in listOf("denied","rejected","rejected_untrusted")) assertEquals(VanContextGesture.POLITE_REFUSAL,VanContextEventPolicy.command(status))
        for (status in listOf("timeout","expired","conflict","UNVERIFIABLE","accepted","completed","success","")) assertNull(VanContextEventPolicy.command(status))
    }
    @Test fun errorAcknowledgementComesOnlyFromActualErrorOrFailure() {
        assertEquals(VanContextGesture.ACKNOWLEDGE_ERROR,VanContextEventPolicy.command("failed"))
        assertEquals(VanContextGesture.ACKNOWLEDGE_ERROR,VanContextEventPolicy.command("error"))
        assertNull(VanContextEventPolicy.command("verifying"))
    }
    @Test fun staleOrClosedDecisionNeverRequestsFreshClarification() {
        assertNull(VanContextEventPolicy.decision(false,2,false));assertNull(VanContextEventPolicy.decision(true,2,true))
        assertNull(VanContextEventPolicy.decision(true,0,false));assertNull(VanContextEventPolicy.decision(true,101,false))
        assertEquals(VanContextGesture.COMPARE_OPTIONS,VanContextEventPolicy.decision(true,2,false))
        assertEquals(VanContextGesture.REQUEST_CLARIFICATION,VanContextEventPolicy.decision(true,1,false))
    }
    @Test fun compareRequiresAtLeastTwoActualChoices() {
        for (count in listOf(-1,0,1,101,Int.MAX_VALUE)) assertNull(VanContextEventPolicy.compare(count))
        assertEquals(VanContextGesture.COMPARE_OPTIONS,VanContextEventPolicy.compare(2))
    }
    @Test fun initialNominalHealthDoesNotManufactureARecoveryEvent() {
        assertFalse(VanContextEventPolicy.recovered(null,VanHealthState.NOMINAL))
        assertFalse(VanContextEventPolicy.recovered(VanHealthState.NOMINAL,VanHealthState.NOMINAL))
        assertFalse(VanContextEventPolicy.recovered(VanHealthState.OFFLINE,VanHealthState.DEGRADED))
        assertTrue(VanContextEventPolicy.recovered(VanHealthState.OFFLINE,VanHealthState.NOMINAL))
        assertTrue(VanContextEventPolicy.recovered(VanHealthState.DEGRADED,VanHealthState.NOMINAL))
    }
    @Test fun closingOldOverlayDoesNotCancelAnotherWindowsNewVoiceTurn() {
        val turns=VoiceTurnLifecycle();val old=turns.begin("overlay-uuid");val new=turns.begin("workspace-uuid")
        assertNull(turns.cancelIf(old.turnId));assertTrue(turns.acceptsRecognition(new))
    }
    @Test fun ownCancelledVoiceCannotPublishAnAlreadyQueuedFinal() {
        val turns=VoiceTurnLifecycle();val own=turns.begin("overlay-uuid");assertTrue(turns.claimFinal(own))
        assertEquals(own,turns.cancelIf(own.turnId));assertFalse(turns.finish(own));assertFalse(turns.claimFinal(own))
    }
    @Test fun repeatedScopedCleanupIsInertAndNeverCancelsLaterTurn() {
        val turns=VoiceTurnLifecycle();val own=turns.begin("old");turns.cancelIf("old");assertNull(turns.cancelIf("old"))
        val fresh=turns.begin("new");assertNull(turns.cancelIf("old"));assertTrue(turns.isCurrent(fresh));assertFalse(turns.isCurrent(own))
    }
    @Test fun noNonfiniteNumericValueCanReachRiveThroughAnyVisualState() {
        for (bad in listOf(Float.NaN,Float.POSITIVE_INFINITY,Float.NEGATIVE_INFINITY)) {
            val input=VanVisualState(attentionX=bad,attentionY=bad,mouthOpen=bad,urgency=bad,viseme=Int.MAX_VALUE,actionCode=Int.MAX_VALUE).toRiveInputs()
            for (v in input.values) if(v is Float)assertTrue(v.isFinite())
            assertEquals(0,input[VanInput.ACTION_CODE]);assertEquals(1,input[VanInput.VISEME])
        }
    }
    @Test fun originalValidRiveInputCodesAndRangesAreUnchanged() {
        for (a in 0..14)for(v in 0..4){
            val input=VanVisualState(attentionX=.5f,attentionY=-.5f,mouthOpen=.75f,urgency=.9f,actionCode=a,viseme=v).toRiveInputs()
            assertEquals(a,input[VanInput.ACTION_CODE]);assertEquals(v,input[VanInput.VISEME]);assertEquals(.75f,input[VanInput.MOUTH_OPEN])
        }
    }
    @Test fun illegalNegativeMouthAndActionShapesDoNotLeak() {
        val input=VanVisualState(mouthOpen=-10f,attentionX=10f,attentionY=-10f,viseme=-1,actionCode=-1).toRiveInputs()
        assertEquals(0f,input[VanInput.MOUTH_OPEN]);assertEquals(1f,input[VanInput.ATTENTION_X]);assertEquals(-1f,input[VanInput.ATTENTION_Y]);assertEquals(0,input[VanInput.ACTION_CODE]);assertEquals(0,input[VanInput.VISEME])
    }
}
