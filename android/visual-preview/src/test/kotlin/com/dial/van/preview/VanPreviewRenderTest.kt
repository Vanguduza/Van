package com.dial.van.preview

import com.dial.van.overlay.OverlayTheme
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanHealthState
import com.dial.van.visual.VanPresenceFrame
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanScene
import com.dial.van.visual.VanSceneFrame
import com.dial.van.visual.VanSpeechState
import com.dial.van.visual.VanStatusPalette
import com.dial.van.visual.VanVisualState
import org.junit.Assert.assertTrue
import org.junit.Test
import java.awt.image.BufferedImage
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/**
 * Measures the acceptance-matrix distinctness requirements on real pixels, so "offline,
 * degraded and urgent are distinct" and orthogonal activity/health composition are evidence
 * rather than claims.
 */
class VanPreviewRenderTest {

    @Test
    fun everySheetRendersAtAReviewableSize() {
        listOf(
            VanPreviewSheets.floatingOverlaySheet(),
            VanPreviewSheets.stateSheet(),
            VanPreviewSheets.stateSheet(reducedMotion = true),
            VanPreviewSheets.stateSheet(budget = com.dial.van.visual.VanEffectBudget.LOW),
            VanPreviewSheets.stateSheet(budget = com.dial.van.visual.VanEffectBudget.STATIC),
            VanPreviewSheets.actionSheet(),
            VanPreviewSheets.commandCentreSheet(),
            VanPreviewSheets.glassTokenSheet(),
            VanPreviewSheets.auraTopologySheet(),
        ).forEach { sheet ->
            assertTrue("sheet too small: ${sheet.width}x${sheet.height}", sheet.width > 600 && sheet.height > 400)
            assertTrue("sheet rendered blank", nonBackgroundRatio(sheet) > 0.02)
        }

        val orthogonal = VanEvidenceMatrix.orthogonalPresenceBoard()
        assertTrue(
            "orthogonal board too small: ${orthogonal.width}x${orthogonal.height}",
            orthogonal.width > 1200 && orthogonal.height >= 360,
        )
        assertTrue("orthogonal board rendered blank", nonBackgroundRatio(orthogonal) > 0.02)
    }

    @Test
    fun orthogonalListeningAndDegradedEvidenceIsNotAPlainDegradedFrame() {
        val composite = VanEvidenceMatrix.orthogonalPresenceTile(
            VanPresenceFrame(
                activity = VanDurableState.LISTENING,
                health = VanHealthState.DEGRADED,
                speech = VanSpeechState.LISTENING,
            ),
        )
        val plainDegraded = VanEvidenceMatrix.presenceTile(VanDurableState.DEGRADED)
        val delta = meanAbsoluteDifference(composite, plainDegraded)
        assertTrue("LISTENING+DEGRADED evidence collapsed to plain DEGRADED (delta $delta)", delta > 1.0)
    }

    @Test
    fun offlineDegradedAndUrgentAreVisuallyDistinct() {
        val states = listOf(
            VanDurableState.IDLE,
            VanDurableState.DEGRADED,
            VanDurableState.OFFLINE,
            VanDurableState.URGENT,
        )
        val rendered = states.associateWith { renderCompact(it) }

        for (i in states.indices) {
            for (j in i + 1 until states.size) {
                val delta = meanAbsoluteDifference(rendered.getValue(states[i]), rendered.getValue(states[j]))
                assertTrue(
                    "${states[i]} and ${states[j]} render too similarly (mean delta $delta)",
                    delta > 4.0,
                )
            }
        }
    }

    @Test
    fun offlineAndDegradedLoseColourWithoutFadingTheCharacter() {
        val idleChroma = averageChroma(renderCompact(VanDurableState.IDLE))
        val degradedChroma = averageChroma(renderCompact(VanDurableState.DEGRADED))
        val offlineChroma = averageChroma(renderCompact(VanDurableState.OFFLINE))

        assertTrue(
            "degraded should visibly lose colour versus ready ($degradedChroma vs $idleChroma)",
            degradedChroma < idleChroma,
        )
        assertTrue(
            "offline should visibly lose more colour than degraded ($offlineChroma vs $degradedChroma)",
            offlineChroma < degradedChroma,
        )
        listOf(VanDurableState.IDLE, VanDurableState.DEGRADED, VanDurableState.OFFLINE).forEach { state ->
            assertTrue(
                "$state must keep full character opacity",
                abs(VanStatusPalette.forState(state).dim - 1f) < 0.0001f,
            )
        }
    }

    @Test
    fun reducedMotionHoldsAStillPose() {
        val listening = VanVisualState(durableState = VanDurableState.LISTENING, listening = true)
        val still = meanAbsoluteDifference(
            renderCompact(listening, phase = 0.05f, reducedMotion = true),
            renderCompact(listening, phase = 0.85f, reducedMotion = true),
        )
        assertTrue("reduced motion must not animate between phases (delta $still)", still < 0.01)

        val animated = meanAbsoluteDifference(
            renderCompact(listening, phase = 0.05f),
            renderCompact(listening, phase = 0.85f),
        )
        assertTrue("animated pose should move between phases (delta $animated)", animated > 0.4)
    }

    @Test
    fun compactCharacterFillsTheOverlayBubble() {
        val image = renderCompact(VanDurableState.IDLE)
        val coverage = nonBackgroundRatio(image)
        assertTrue("character too sparse to read at overlay size (coverage $coverage)", coverage > 0.25)
    }

    private fun renderCompact(
        state: VanDurableState,
        phase: Float = 0.18f,
        reducedMotion: Boolean = false,
    ): BufferedImage = renderCompact(
        VanVisualState(durableState = state, urgency = if (state == VanDurableState.URGENT) 1f else 0f),
        phase,
        reducedMotion,
    )

    private fun renderCompact(
        state: VanVisualState,
        phase: Float = 0.18f,
        reducedMotion: Boolean = false,
    ): BufferedImage = AwtVanRenderer.render(
        ops = VanScene.build(
            state,
            VanSceneFrame(presentation = VanPresentation.COMPACT, phase = phase, reducedMotion = reducedMotion),
        ),
        width = 180,
        height = 180,
        background = OverlayTheme.SURFACE_ARGB,
    )

    private fun meanAbsoluteDifference(a: BufferedImage, b: BufferedImage): Double {
        var total = 0L
        for (y in 0 until a.height) {
            for (x in 0 until a.width) {
                val pa = a.getRGB(x, y)
                val pb = b.getRGB(x, y)
                total += abs(((pa shr 16) and 0xFF) - ((pb shr 16) and 0xFF))
                total += abs(((pa shr 8) and 0xFF) - ((pb shr 8) and 0xFF))
                total += abs((pa and 0xFF) - (pb and 0xFF))
            }
        }
        return total.toDouble() / (a.width * a.height * 3)
    }

    private fun averageChroma(image: BufferedImage): Double {
        var total = 0L
        for (y in 0 until image.height) {
            for (x in 0 until image.width) {
                val p = image.getRGB(x, y)
                val r = (p shr 16) and 0xFF
                val g = (p shr 8) and 0xFF
                val b = p and 0xFF
                total += max(r, max(g, b)) - min(r, min(g, b))
            }
        }
        return total.toDouble() / (image.width * image.height)
    }

    private fun nonBackgroundRatio(image: BufferedImage): Double {
        val corner = image.getRGB(0, 0)
        var differing = 0
        for (y in 0 until image.height) {
            for (x in 0 until image.width) {
                if (image.getRGB(x, y) != corner) differing++
            }
        }
        return differing.toDouble() / (image.width * image.height)
    }
}
