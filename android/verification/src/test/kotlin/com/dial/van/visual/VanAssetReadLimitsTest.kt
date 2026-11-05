package com.dial.van.visual

import java.io.ByteArrayInputStream
import java.io.InputStream
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class VanAssetReadLimitsTest {
    @Test fun normalAndEmptyBundleReadExactly() {
        val input=ByteArray(50_000){(it%255).toByte()}
        assertContentEquals(input,VanAssetReadLimits.read(ByteArrayInputStream(input),input.size))
        assertTrue(VanAssetReadLimits.read(ByteArrayInputStream(byteArrayOf()),1).isEmpty())
    }
    @Test fun boundIsCheckedDuringReadNotAfterUnboundedAllocation() {
        var count=0
        val infinite=object:InputStream(){override fun read():Int{count++;return 42}}
        assertFailsWith<IllegalArgumentException>{VanAssetReadLimits.read(infinite,16_384)}
        assertEquals(16_385,count)
    }
    @Test fun brokenZeroLengthBulkReadsCannotLoopForever() {
        var calls=0
        val odd=object:InputStream(){override fun read():Int = if(calls++<3)42 else -1
            override fun read(b:ByteArray,off:Int,len:Int):Int=0}
        assertContentEquals(byteArrayOf(42,42,42),VanAssetReadLimits.read(odd,3))
    }
    @Test fun exactMaximumAllowedButOneExtraByteRefused() {
        assertEquals(8_192,VanAssetReadLimits.read(ByteArrayInputStream(ByteArray(8_192)),8_192).size)
        assertFailsWith<IllegalArgumentException>{VanAssetReadLimits.read(ByteArrayInputStream(ByteArray(8_193)),8_192)}
    }
    @Test fun invalidOrExcessiveBudgetIsNotAccepted() {
        for (size in listOf(-1,0,Int.MAX_VALUE)) assertFailsWith<IllegalArgumentException>{VanAssetReadLimits.read(ByteArrayInputStream(byteArrayOf()),size)}
    }
    @Test fun rendererSelectsFallbackForOversizedArtBeforeNativeLoad() {
        assertEquals(VanRenderer.CANDIDATE_B,VanVisualRuntime.decide(VanAssetReadLimits.RIVE_BYTES+1L,true,candidateBAvailable=true).renderer)
        assertEquals(VanRenderer.RIVE,VanVisualRuntime.decide(VanAssetReadLimits.RIVE_BYTES.toLong(),true).renderer)
    }
}
