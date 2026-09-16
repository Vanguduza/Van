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
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class VanAcceptanceGateTest {

    @Test
    fun compactGeometryMatchesRev3Blueprint() {
        assertEquals(300, OverlayTheme.COMPACT_WIDTH_DP)
        assertEquals(188, OverlayTheme.COMPACT_HEIGHT_DP)
        assertTrue(OverlayTheme.VAN_GLASS_OVERLAP_DP in 12..24)
        assertEquals(184, OverlayTheme.RESTING_HIT_DP)
        assertEquals(96, OverlayTheme.RESTING_AVATAR_DP)
        assertEquals(62, OverlayTheme.MINIMIZED_VISUAL_DP)
        assertTrue(OverlayTheme.MINIMIZED_TOUCH_DP >= 64)
        assertEquals(88, OverlayTheme.DOCK_HIT_DP)
        assertEquals(76, OverlayTheme.DOCK_CHARACTER_DP)
        assertEquals(
            listOf("Chat", "Voice", "Projects", "Tasks", "Decisions"),
            OverlayTheme.COMPACT_ACTIONS,
        )
        assertEquals(
            listOf("Chat", "Voice", "Minimize", "Command Centre", "Dock", "Close"),
            OverlayTheme.QUICK_CONTROLS,
        )
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

    @Test
    fun commandCentreIdleAndDegradedEvidenceCannotCollapseToTheSameImage() {
        val idle = VanCommandCentreEvidence.render(degraded = false)
        val degraded = VanCommandCentreEvidence.render(degraded = true)
        var differingPixels = 0L
        for (y in 0 until idle.height) {
            for (x in 0 until idle.width) {
                if (idle.getRGB(x, y) != degraded.getRGB(x, y)) differingPixels++
            }
        }
        val ratio = differingPixels.toDouble() / (idle.width.toLong() * idle.height.toLong())
        assertTrue("IDLE and DEGRADED command-centre evidence collapsed (difference ratio $ratio)", ratio > 0.01)
    }

    @Test
    fun commandCentreEvidenceReconciliationRefreshesDistinctManifestHashes() {
        val outputDir = Files.createTempDirectory("van-command-centre-evidence").toFile()
        try {
            val revDir = File(outputDir, VanEvidenceMatrix.EVIDENCE_DIR).apply { mkdirs() }
            File(revDir, "manifest.json").writeText(
                """
                {
                  "shots": [
                    {"id":"command-centre-idle","state":"IDLE","sha256":"stale","bytes":1},
                    {"id":"command-centre-degraded","state":"DEGRADED","sha256":"stale","bytes":1}
                  ]
                }
                """.trimIndent(),
            )

            VanCommandCentreEvidence.reconcile(outputDir)

            val idle = File(revDir, "command-centre-idle.png")
            val degraded = File(revDir, "command-centre-degraded.png")
            assertTrue("idle evidence not written", idle.isFile && idle.length() > 0)
            assertTrue("degraded evidence not written", degraded.isFile && degraded.length() > 0)
            assertTrue("command-centre evidence files are byte-identical", !idle.readBytes().contentEquals(degraded.readBytes()))

            val manifest = File(revDir, "manifest.json").readText()
            val idleSha = manifestSha(manifest, "command-centre-idle")
            val degradedSha = manifestSha(manifest, "command-centre-degraded")
            assertNotEquals("manifest still records duplicate command-centre hashes", idleSha, degradedSha)
            assertTrue("idle byte count was not refreshed", manifest.contains("\"bytes\":${idle.length()}"))
            assertTrue("degraded byte count was not refreshed", manifest.contains("\"bytes\":${degraded.length()}"))
        } finally {
            outputDir.deleteRecursively()
        }
    }

    private fun manifestSha(manifest: String, id: String): String {
        val match = Regex("\\\"id\\\":\\\"${Regex.escape(id)}\\\"[^\\n]*?\\\"sha256\\\":\\\"([0-9a-f]{64})\\\"")
            .find(manifest)
        checkNotNull(match) { "Manifest does not contain a refreshed SHA for $id" }
        return match.groupValues[1]
    }
}
