package com.dial.van.voice

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class PcmPlaybackVisualTest {
    @Test fun queuedButNotPlayedAudioCannotOpenMouth() {
        val clock=PcmPlaybackVisualClock();assertEquals(PcmPlaybackVisual(),clock.sample(FloatArray(10_000){1f},16_000,0,10_000,1_000))
    }
    @Test fun envelopeFollowsPlayedSegmentRatherThanTheWriteBuffer() {
        val data=FloatArray(8_000){if(it<4_000)0f else .15f};val clock=PcmPlaybackVisualClock()
        assertEquals(0f,clock.sample(data,16_000,3_000,8_000,1_000).mouthOpen)
        val voice=clock.sample(data,16_000,5_000,8_000,1_125);assertTrue(voice.mouthOpen>.8f);assertEquals(1,voice.viseme)
    }
    @Test fun unsubmittedSamplesAreNeverIncludedInDisplayedAmplitude() {
        val clock=PcmPlaybackVisualClock();val data=FloatArray(3_000){if(it<1_000)0f else 1f}
        assertEquals(0f,clock.sample(data,16_000,2_000,1_000,1_000).mouthOpen)
    }
    @Test fun stalledOrUnderrunPlaybackReturnsToNeutralUntilProgressResumes() {
        val c=PcmPlaybackVisualClock();val samples=FloatArray(5_000){.2f}
        assertTrue(c.sample(samples,16_000,1_000,5_000,1_000).mouthOpen>0)
        assertEquals(PcmPlaybackVisual(),c.sample(samples,16_000,1_000,5_000,1_121))
        assertTrue(c.sample(samples,16_000,1_640,5_000,1_140).mouthOpen>0)
    }
    @Test fun silenceNeverCyclesIntoUnsupportedPhonemeShapes() {
        val c=PcmPlaybackVisualClock()
        repeat(50){assertEquals(0,c.sample(FloatArray(4_000),16_000,(it+1)*64L,4_000,it*4L).viseme)}
    }
    @Test fun arbitraryWaveformUsesOnlyNeutralOrGenericOpenShape() {
        val c=PcmPlaybackVisualClock();val sample=FloatArray(8_000){if(it%3==0)-.3f else .1f}
        repeat(100){val s=c.sample(sample,16_000,(it+1)*64L,8_000,it*4L);assertTrue(s.viseme in 0..1);assertTrue(s.mouthOpen in 0f..1f);assertTrue(s.rms.isFinite())}
    }
    @Test fun badSamplesAndImpossibleMetadataCannotPoisonAnimation() {
        for (bad in listOf(Float.NaN,Float.POSITIVE_INFINITY,Float.NEGATIVE_INFINITY)) assertEquals(PcmPlaybackVisual(),PcmPlaybackVisualClock().sample(FloatArray(500){bad},16_000,500,500,100))
        assertEquals(PcmPlaybackVisual(),PcmPlaybackVisualClock().sample(FloatArray(500),0,500,500,100))
        assertEquals(PcmPlaybackVisual(),PcmPlaybackVisualClock().sample(FloatArray(500),16_000,-1,500,100))
    }
    @Test fun backwardPlaybackOrMonotonicClockDoesNotAnimateWrongGeneration() {
        val c=PcmPlaybackVisualClock();val data=FloatArray(2_000){.3f};c.sample(data,16_000,1_000,2_000,100)
        assertEquals(PcmPlaybackVisual(),c.sample(data,16_000,10,2_000,120))
        assertEquals(PcmPlaybackVisual(),c.sample(data,16_000,20,2_000,110))
    }
    @Test fun outOfRangeHeadIsSafelyBoundedToActualSamples() {
        val result=PcmPlaybackVisualClock().sample(FloatArray(1_000){.1f},16_000,Long.MAX_VALUE,Int.MAX_VALUE,1_000)
        assertTrue(result.mouthOpen in .54f..56f/100);assertEquals(1,result.viseme)
    }
}
