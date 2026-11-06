package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class VanRendererHardeningTest {
    @Test fun redundantVisualSnapshotsDoNotQueueMoreNativeWakeups() {
        val gate=VanRiveUpdateGate();val state=VanVisualState()
        assertNotNull(gate.next(state,true,true))
        repeat(10_000){assertNull(gate.next(state,true,true))}
    }
    @Test fun hiddenViewNeverStartsAPoseRefreshAndResumptionUsesCurrentState() {
        val gate=VanRiveUpdateGate();val idle=VanVisualState()
        gate.next(idle,true,true)
        repeat(100){assertNull(gate.next(idle.copy(durableState=VanDurableState.ERROR),false,false))}
        assertEquals(VanDurableState.ERROR,assertNotNull(gate.next(idle.copy(durableState=VanDurableState.ERROR),true,false)).durableState)
    }
    @Test fun stillModeUpdatesRealStatusWithoutSpeechOrGestureAnimation() {
        val gate=VanRiveUpdateGate();val speaking=VanVisualState(durableState=VanDurableState.SPEAKING,speaking=true,mouthOpen=.8f,viseme=3,attentionX=.5f,actionCode=1,contextCode=15)
        val still=assertNotNull(gate.next(speaking,true,false))
        assertEquals(speaking.durableState,still.durableState)
        assertFalse(still.speaking);assertEquals(0f,still.mouthOpen);assertEquals(0,still.actionCode);assertEquals(0,still.contextCode)
        repeat(100){assertNull(gate.next(speaking.copy(mouthOpen=it/100f,viseme=it%5,attentionX=it/100f),true,false))}
    }
    @Test fun transitionFromStillToAnimatedAlwaysPushesTheCurrentInputs() {
        val gate=VanRiveUpdateGate();val state=VanVisualState(durableState=VanDurableState.SPEAKING,speaking=true,mouthOpen=.5f)
        gate.next(state,true,false)
        assertTrue(assertNotNull(gate.next(state,true,true)).speaking)
        assertNull(gate.next(state,true,true))
    }
    @Test fun replacingNativeViewInvalidatesCachedInputSnapshot() {
        val gate=VanRiveUpdateGate();val state=VanVisualState();gate.next(state,true,true);gate.reset()
        assertNotNull(gate.next(state,true,true))
    }
    @Test fun stillTransitionBudgetIsFiniteAndCoversOriginalBlendBound() {
        assertTrue(VanRiveUpdateGate.STATIC_SETTLE_STEPS in 1..30)
        val seconds=VanRiveUpdateGate.STATIC_SETTLE_STEPS*VanRiveUpdateGate.STATIC_STEP_SECONDS
        assertTrue(seconds>=.42f && seconds<=.5f)
    }
    @Test fun dragResponseIsDensityNormalizedAndNeverExcessive() {
        assertEquals(VanInteractionResponsePolicy.drag(12f,-8f,1f),VanInteractionResponsePolicy.drag(36f,-24f,3f))
        val extreme=VanInteractionResponsePolicy.drag(1e20f,-1e20f,1f)
        assertEquals(-2.5f,extreme.leanDegrees);assertEquals(1.25f,extreme.liftDp)
    }
    @Test fun corruptDragInputReturnsToNeutralInsteadOfNaNTransform() {
        for (bad in listOf(Float.NaN,Float.POSITIVE_INFINITY,Float.NEGATIVE_INFINITY)) {
            assertEquals(VanInteractionResponse(),VanInteractionResponsePolicy.drag(bad,0f,1f))
            assertEquals(VanInteractionResponse(),VanInteractionResponsePolicy.drag(0f,bad,1f))
            assertEquals(VanInteractionResponse(),VanInteractionResponsePolicy.drag(1f,1f,bad))
        }
        assertEquals(VanInteractionResponse(),VanInteractionResponsePolicy.drag(1f,1f,0f))
    }
    @Test fun physicalResponseCannotOffsetPreciselySolvedPointing() {
        for (code in listOf(3,4,5,6,7))assertFalse(VanInteractionResponsePolicy.compatible(VanVisualState(actionCode=code)))
        for (code in listOf(18,26))assertFalse(VanInteractionResponsePolicy.compatible(VanVisualState(contextCode=code)))
        assertTrue(VanInteractionResponsePolicy.compatible(VanVisualState(actionCode=1)))
    }
}
