package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class VanMinimizedExpressionTest {
    @Test fun idleHasCalmNeutralFace() {
        val e = VanMinimizedExpressionMap.from(VanVisualState())
        assertEquals(VanSmallMouth.NEUTRAL, e.mouth)
        assertEquals(0f, e.speechOpening)
    }
    @Test fun verifiedSuccessOnlyHasSoftSmileFromResolvedState() {
        assertEquals(
            VanSmallMouth.SMILE,
            VanMinimizedExpressionMap.from(VanVisualState(durableState=VanDurableState.SUCCESS)).mouth,
        )
        assertEquals(
            VanSmallMouth.NEUTRAL,
            VanMinimizedExpressionMap.from(VanVisualState(durableState=VanDurableState.WORKING)).mouth,
        )
    }
    @Test fun warningAndErrorHaveConcernInsteadOfCelebration() {
        for (s in listOf(VanDurableState.WARNING, VanDurableState.ERROR, VanDurableState.URGENT)) {
            val e=VanMinimizedExpressionMap.from(VanVisualState(durableState=s))
            assertEquals(VanSmallMouth.CONCERN,e.mouth)
            assertTrue(e.browLift < 0f)
        }
    }
    @Test fun ownerApprovalRemainsAttentiveNotSmiling() {
        val e=VanMinimizedExpressionMap.from(VanVisualState(durableState=VanDurableState.WAITING_FOR_OWNER))
        assertEquals(VanSmallMouth.NEUTRAL,e.mouth)
        assertTrue(e.browLift > 0f)
    }
    @Test fun speechMouthUsesOnlyApprovedFiveVisemes() {
        for (v in -5..15) {
            val e=VanMinimizedExpressionMap.from(VanVisualState(
                durableState=VanDurableState.SPEAKING,speaking=true,mouthOpen=0.7f,viseme=v))
            assertEquals(VanSmallMouth.SPEECH,e.mouth)
            assertTrue(e.viseme in 0..4)
            assertEquals(0.7f,e.speechOpening)
        }
    }
    @Test fun urgentPoseSuppressesChattyMouthEvenWhileSpeaking() {
        val e=VanMinimizedExpressionMap.from(VanVisualState(durableState=VanDurableState.URGENT,speaking=true,mouthOpen=0.9f))
        assertEquals(VanSmallMouth.CONCERN,e.mouth)
    }
    @Test fun nonfiniteSpeechOpeningCannotReachRenderer() {
        for (v in listOf(Float.NaN,Float.NEGATIVE_INFINITY,Float.POSITIVE_INFINITY)) {
            val e=VanMinimizedExpressionMap.from(VanVisualState(durableState=VanDurableState.SPEAKING,speaking=true,mouthOpen=v))
            assertEquals(0f,e.speechOpening)
        }
    }
}
