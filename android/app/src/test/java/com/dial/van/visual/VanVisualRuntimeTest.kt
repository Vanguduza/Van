package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The visual path must fail closed: anything short of a loadable authored artboard has to
 * resolve to the Canvas character rather than leaving a blank or half-bound avatar.
 */
class VanVisualRuntimeTest {

    @Test
    fun missingArtboardFallsBackToCanvas() {
        val decision = VanVisualRuntime.decide(assetBytes = null, riveRuntimeAvailable = true)
        assertEquals(VanRenderer.CANVAS, decision.renderer)
        assertEquals(VanCanvasReason.ASSET_MISSING, decision.reason)
    }

    @Test
    fun placeholderSizedArtboardIsRejected() {
        val decision = VanVisualRuntime.decide(assetBytes = 64, riveRuntimeAvailable = true)
        assertEquals(VanRenderer.CANVAS, decision.renderer)
        assertEquals(VanCanvasReason.ASSET_UNUSABLE, decision.reason)
    }

    @Test
    fun missingRuntimeFallsBackToCanvas() {
        val decision = VanVisualRuntime.decide(assetBytes = 512_000, riveRuntimeAvailable = false)
        assertEquals(VanRenderer.CANVAS, decision.renderer)
        assertEquals(VanCanvasReason.RUNTIME_UNAVAILABLE, decision.reason)
    }

    @Test
    fun loadFailureAlwaysWinsOverAHealthyLookingAsset() {
        val decision = VanVisualRuntime.decide(
            assetBytes = 512_000,
            riveRuntimeAvailable = true,
            loadFailed = true,
        )
        assertEquals(VanRenderer.CANVAS, decision.renderer)
        assertEquals(VanCanvasReason.LOAD_FAILED, decision.reason)
    }

    @Test
    fun onlyALoadableArtboardReachesRive() {
        val decision = VanVisualRuntime.decide(assetBytes = 512_000, riveRuntimeAvailable = true)
        assertEquals(VanRenderer.RIVE, decision.renderer)
        assertEquals(VanCanvasReason.NOT_APPLICABLE, decision.reason)
    }

    @Test
    fun everyCanvasReasonIsExplainable() {
        VanCanvasReason.entries.forEach { reason ->
            assertTrue("empty description for $reason", VanVisualRuntime.describe(reason).isNotBlank())
        }
    }
}
