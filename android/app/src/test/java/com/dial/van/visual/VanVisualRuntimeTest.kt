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

    @Test
    fun candidateBArtOutranksTheDrawingButNeverALoadableArtboard() {
        // Owner choice: real Candidate B art is the interim VAN; the procedural drawing is the
        // last resort; a loadable artboard always wins.
        val missing = VanVisualRuntime.decide(assetBytes = null, riveRuntimeAvailable = true, candidateBAvailable = true)
        assertEquals(VanRenderer.CANDIDATE_B, missing.renderer)
        assertEquals(VanCanvasReason.ASSET_MISSING, missing.reason)
        val failed = VanVisualRuntime.decide(assetBytes = 4096L, riveRuntimeAvailable = true, loadFailed = true, candidateBAvailable = true)
        assertEquals(VanRenderer.CANDIDATE_B, failed.renderer)
        assertEquals(VanCanvasReason.LOAD_FAILED, failed.reason)
        val rive = VanVisualRuntime.decide(assetBytes = 4096L, riveRuntimeAvailable = true, candidateBAvailable = true)
        assertEquals(VanRenderer.RIVE, rive.renderer)
        val retired = VanVisualRuntime.decide(assetBytes = null, riveRuntimeAvailable = true, ownerArtAvailable = true)
        assertEquals("the retired owner-art rung must never return", VanRenderer.CANVAS, retired.renderer)
    }

    @Test
    fun interimArtIsFramedLikeTheCharacterAndTheFlames() {
        // Full body: the whole bitmap fills the box's centred square, unstretched.
        val full = VanInterimArt.blit(VanFraming.FULL_BODY, 593, 300f, 300f)!!
        assertEquals(0, full.srcLeft)
        assertEquals(593, full.srcWidth)
        assertEquals(300f, full.dstWidth, 0.6f)
        // Compact: zoomed on head and shoulders; the face lands in the upper half of the box.
        val compact = VanInterimArt.blit(VanFraming.COMPACT, 593, 300f, 300f)!!
        assertTrue("compact must crop", compact.srcWidth < 593)
        val scale = compact.dstWidth / compact.srcWidth
        assertEquals("compact zoom", VanFraming.COMPACT.zoom * 300f / 593f, scale, 0.01f)
        val faceY = compact.dstTop + (VanBodyLayout.v(122f) * 593f - compact.srcTop) * scale
        assertTrue("face at $faceY is not in the upper half", faceY in 60f..170f)
        // A wide box letterboxes the square rather than stretching it.
        val wide = VanInterimArt.blit(VanFraming.FULL_BODY, 593, 500f, 300f)!!
        assertEquals(100f, wide.dstLeft, 0.6f)
    }
}
