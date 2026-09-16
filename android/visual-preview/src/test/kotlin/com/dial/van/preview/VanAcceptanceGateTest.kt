package com.dial.van.preview

import com.dial.van.overlay.OverlayTheme
import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanDrawOp
import com.dial.van.visual.VanFiniteAction
import com.dial.van.visual.VanPresentation
import com.dial.van.visual.VanScene
import com.dial.van.visual.VanSceneFrame
import com.dial.van.visual.VanVisualState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class VanAcceptanceGateTest {

    @Test
    fun compactGeometryMatchesBlueprint() {
        assertEquals(280, OverlayTheme.COMPACT_WIDTH_DP)
        assertTrue(OverlayTheme.VAN_GLASS_OVERLAP_DP in 12..24)
        assertEquals(168, OverlayTheme.RESTING_HIT_DP)
        assertEquals(92, OverlayTheme.RESTING_AVATAR_DP)
        assertEquals(88, OverlayTheme.DOCK_HIT_DP)
        assertEquals(76, OverlayTheme.DOCK_CHARACTER_DP)
        assertEquals(listOf("Ask", "Projects", "Tasks", "Decisions"), OverlayTheme.COMPACT_ACTIONS)
    }

    @Test
    fun statusMarksNeverUseAFullRing() {
        VanDurableState.entries.forEach { state ->
            VanScene.build(
                VanVisualState(durableState = state, urgency = 1f),
                VanSceneFrame(presentation = VanPresentation.COMPACT, phase = 0.2f),
            ).filterIsInstance<VanDrawOp.Arc>().filter { it.r > 0.08f }.forEach { arc ->
                assertTrue(
                    "$state arc sweep ${arc.sweepDegrees} exceeds 110°",
                    kotlin.math.abs(arc.sweepDegrees) <= 110.01f,
                )
            }
        }
    }

    @Test
    fun fourteenActionsProduceDistinctPoses() {
        val signatures = VanFiniteAction.entries.map { action ->
            VanScene.build(
                VanVisualState(durableState = VanDurableState.IDLE, actionCode = action.code),
                VanSceneFrame(presentation = VanPresentation.COMMAND_CENTRE, phase = 0.2f),
            ).toString()
        }
        assertEquals(14, signatures.size)
        assertEquals("each action must change the pose", 14, signatures.toSet().size)
    }

    @Test
    fun grayscaleKeepsCriticalStatesDistinct() {
        val states = listOf(
            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.WARNING,
            VanDurableState.ERROR,
            VanDurableState.SUCCESS,
            VanDurableState.URGENT,
        )
        val shapeSignatures = states.map { state ->
            VanScene.build(
                VanVisualState(durableState = state, urgency = if (state == VanDurableState.URGENT) 1f else 0f),
                VanSceneFrame(presentation = VanPresentation.COMPACT, phase = 0.18f),
            ).filter { op ->
                when (op) {
                    is VanDrawOp.Arc -> op.r > 0.08f
                    is VanDrawOp.PathOp -> op.strokeWidth != null || op.segments.size >= 3
                    is VanDrawOp.RoundRect -> op.halfW >= 0.05f
                    is VanDrawOp.Circle -> op.r >= 0.05f
                    is VanDrawOp.Oval -> op.rx >= 0.05f
                }
            }.map { op ->
                when (op) {
                    is VanDrawOp.Arc -> "arc:${op.sweepDegrees.toInt()}:${op.r}"
                    is VanDrawOp.PathOp -> "path:${op.segments.size}:${op.strokeWidth}"
                    is VanDrawOp.RoundRect -> "rect:${op.halfW}:${op.halfH}"
                    is VanDrawOp.Circle -> "circle:${op.r}"
                    is VanDrawOp.Oval -> "oval:${op.rx}:${op.ry}"
                }
            }.toString()
        }
        assertEquals("critical states must differ by shape, not colour", 5, shapeSignatures.toSet().size)

        val tiles = states.map { VanEvidenceMatrix.grayscale(VanEvidenceMatrix.presenceTile(it)) }
        for (i in tiles.indices) {
            for (j in i + 1 until tiles.size) {
                val delta = VanEvidenceMatrix.meanAbsoluteDifference(tiles[i], tiles[j])
                assertTrue("${states[i]} vs ${states[j]} grayscale delta $delta", delta > 1.5)
            }
        }
    }
}
