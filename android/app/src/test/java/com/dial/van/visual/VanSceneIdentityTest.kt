package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Guards `docs/VAN_CHARACTER_VISUAL_IDENTITY.md` against silent drift in the interim Canvas
 * character. The forbidden substitutions list is enforced here, not just documented.
 */
class VanSceneIdentityTest {

    private fun scene(
        state: VanDurableState = VanDurableState.IDLE,
        presentation: VanPresentation = VanPresentation.COMPACT,
    ) = VanScene.build(
        VanVisualState(durableState = state),
        VanSceneFrame(presentation = presentation, phase = 0.2f),
    )

    private fun List<VanDrawOp>.usesRgb(hex: Long): Boolean {
        val rgb = hex.toInt() and 0x00FFFFFF
        return any { (it.color and 0x00FFFFFF) == rgb }
    }

    @Test
    fun canonicalIdentityElementsAreAllPresent() {
        val ops = scene()
        assertTrue("silver/white swept hair missing", ops.usesRgb(VanScene.HAIR))
        assertTrue("medium-brown skin missing", ops.usesRgb(VanScene.SKIN))
        assertTrue("blue eyes missing", ops.usesRgb(VanScene.EYE_IRIS))
        assertTrue("cyan visor missing", ops.usesRgb(VanScene.VISOR))
        assertTrue("black/white technical jacket missing", ops.usesRgb(VanScene.JACKET))
        assertTrue("white jacket panel missing", ops.usesRgb(VanScene.JACKET_PANEL))
        assertTrue("charcoal underlayer missing", ops.usesRgb(VanScene.UNDERLAYER))
    }

    @Test
    fun hairIsLightNeverDark() {
        val hair = VanScene.HAIR.toInt()
        val r = (hair shr 16) and 0xFF
        val g = (hair shr 8) and 0xFF
        val b = hair and 0xFF
        val luma = 0.299 * r + 0.587 * g + 0.114 * b
        assertTrue("Hair must read silver/white, luma was $luma", luma > 200)
    }

    @Test
    fun visorIsTransparentSoBlueEyesStayVisible() {
        val ops = scene()
        val irises = ops.filterIsInstance<VanDrawOp.Circle>()
            .filter { (it.color and 0x00FFFFFF) == (VanScene.EYE_IRIS.toInt() and 0x00FFFFFF) }
        assertTrue("no irises to sit behind the visor", irises.isNotEmpty())
        // The visor is the cyan panel covering both eyes. Matching on colour alone would also
        // catch the cyan DIAL chest emblem, which carries no transparency requirement.
        val visorFill = ops.filterIsInstance<VanDrawOp.RoundRect>().firstOrNull { rect ->
            rect.strokeWidth == null &&
                (rect.color and 0x00FFFFFF) == (VanScene.VISOR.toInt() and 0x00FFFFFF) &&
                irises.all { iris ->
                    iris.cx in (rect.cx - rect.halfW)..(rect.cx + rect.halfW) &&
                        iris.cy in (rect.cy - rect.halfH)..(rect.cy + rect.halfH)
                }
        }
        requireNotNull(visorFill) { "visor fill missing" }
        val alpha = (visorFill.color ushr 24) and 0xFF
        assertTrue("Visor must stay transparent, alpha was $alpha", alpha in 1..140)

        val irisIndex = ops.indexOfFirst { (it.color and 0x00FFFFFF) == (VanScene.EYE_IRIS.toInt() and 0x00FFFFFF) }
        val visorIndex = ops.indexOf(visorFill)
        assertTrue("Eyes must be painted before the visor", irisIndex in 0 until visorIndex)
    }

    @Test
    fun orbCompanionAccompaniesEveryPresentation() {
        // CF-D-05-REV2_1: the dark bar-eyed orb floats over VAN's open palm, on the viewer's
        // left at chin height, exactly where Candidate B places it.
        VanPresentation.entries.forEach { presentation ->
            val (ox, oy) = VanScene.orbCentre(presentation)
            assertTrue("$presentation orb is not on the viewer's left: $ox", ox < 0.40f)
            val ops = scene(presentation = presentation)
            val shell = ops.filterIsInstance<VanDrawOp.Circle>().filter {
                (it.color and 0x00FFFFFF) == (VanScene.ORB_BODY.toInt() and 0x00FFFFFF) &&
                    kotlin.math.abs(it.cx - ox) < 0.03f && kotlin.math.abs(it.cy - oy) < 0.05f
            }
            assertTrue("dark orb shell missing for $presentation", shell.isNotEmpty())
            val barEyes = ops.filterIsInstance<VanDrawOp.RoundRect>().filter {
                (it.color and 0x00FFFFFF) == (VanScene.ORB_EYE.toInt() and 0x00FFFFFF) && it.halfH > it.halfW * 2f &&
                    kotlin.math.abs(it.cx - ox) < shell.first().r && kotlin.math.abs(it.cy - oy) < shell.first().r
            }
            assertEquals("the orb has two vertical bar eyes for $presentation", 2, barEyes.size)
        }
    }

    @Test
    fun fullFigureIsCandidateBsCompactBuild() {
        // Command Centre shows the whole figure, framed like the Rive artboard, so its head
        // count must sit inside the locked 3.2 ± 0.3.
        val ops = scene(presentation = VanPresentation.COMMAND_CENTRE)
        val hair = ops.filterIsInstance<VanDrawOp.PathOp>().first { (it.color and 0x00FFFFFF) == (VanScene.HAIR.toInt() and 0x00FFFFFF) }
        val crown = hair.segments.mapNotNull { (it as? VanPathSeg.LineTo)?.y ?: (it as? VanPathSeg.MoveTo)?.y }.min()
        val sole = ops.filterIsInstance<VanDrawOp.PathOp>().flatMap { op -> op.segments.mapNotNull { (it as? VanPathSeg.LineTo)?.y } }.max()
        val chin = VanBodyLayout.CHIN_V
        val heads = (sole - crown) / (chin - crown)
        assertTrue("Canvas VAN is $heads heads tall, outside 2.9–3.5", heads in 2.9f..3.5f)
    }

    @Test
    fun compactPresentationKeepsFaceLargeEnoughToRead() {
        val ops = scene(presentation = VanPresentation.COMPACT)
        val iris = ops.filterIsInstance<VanDrawOp.Circle>()
            .filter { (it.color and 0x00FFFFFF) == (VanScene.EYE_IRIS.toInt() and 0x00FFFFFF) }
        assertEquals("expected two irises", 2, iris.size)
        // At 76dp the iris must still cover multiple pixels.
        assertTrue("iris too small to read at overlay size: ${iris.first().r}", iris.first().r > 0.028f)
    }

    @Test
    fun geometryStaysInsideTheDrawableBox() {
        VanPresentation.entries.forEach { presentation ->
            VanDurableState.entries.forEach { state ->
                VanScene.build(
                    VanVisualState(durableState = state, urgency = 1f),
                    VanSceneFrame(presentation = presentation, phase = 0.6f),
                ).forEach { op ->
                    val bounds = extentOf(op)
                    assertTrue(
                        "$state/$presentation op escapes the box: $op",
                        bounds.all { it > -0.12f && it < 1.12f },
                    )
                }
            }
        }
    }

    @Test
    fun theCharacterIsAlwaysOpaqueAndInFullColour() {
        // Owner direction (2026-09-25): offline desaturation made VAN read as grey and
        // see-through like his aura. State lives in the aura, ring and copy, never in VAN.
        val idle = VanStatusPalette.forState(VanDurableState.IDLE)
        val offline = VanStatusPalette.forState(VanDurableState.OFFLINE)
        val degraded = VanStatusPalette.forState(VanDurableState.DEGRADED)
        val urgent = VanStatusPalette.forState(VanDurableState.URGENT)

        VanDurableState.entries.forEach { state ->
            val palette = VanStatusPalette.forState(state)
            assertEquals("$state must keep the character optically solid", 1f, palette.dim, 0.0001f)
            assertEquals("$state must keep the character in full colour", 0f, palette.desaturation, 0.0001f)
        }
        assertNotEquals("offline and degraded need different ring accents", offline.accent, degraded.accent)
        assertNotEquals("degraded and urgent need different ring accents", degraded.accent, urgent.accent)
        assertNotEquals("urgent must not reuse the calm ring", idle.ringStyle, urgent.ringStyle)
    }

    @Test
    fun eighteenStatesAndFourteenDistinctActionPoses() {
        assertEquals(18, VanDurableState.entries.size)
        assertEquals(14, VanFiniteAction.entries.size)
        val signatures = VanFiniteAction.entries.map { action ->
            VanScene.build(
                VanVisualState(durableState = VanDurableState.IDLE, actionCode = action.code),
                VanSceneFrame(presentation = VanPresentation.COMMAND_CENTRE, phase = 0.2f),
            ).toString()
        }
        assertEquals("each finite action must change the pose", 14, signatures.toSet().size)
    }

    @Test
    fun glowStaysRestrainedAcrossEveryState() {
        VanDurableState.entries.forEach { state ->
            val palette = VanStatusPalette.forState(state)
            assertTrue("$state glow too strong: ${palette.glow}", palette.glow <= 0.45f)
        }
    }

    @Test
    fun reducedMotionRemovesEveryOscillation() {
        val state = VanVisualState(durableState = VanDurableState.WAITING_FOR_OWNER, urgency = 0.5f)
        val a = VanScene.build(state, VanSceneFrame(phase = 0.05f, reducedMotion = true))
        val b = VanScene.build(state, VanSceneFrame(phase = 0.72f, reducedMotion = true))
        assertEquals("reduced motion must be phase-independent", a, b)

        val moving = VanScene.build(state, VanSceneFrame(phase = 0.72f))
        assertNotEquals("animated pose should differ from the still pose", a, moving)
    }

    @Test
    fun speakingOpensTheMouthProportionally()  {
        val closed = VanScene.build(
            VanVisualState(durableState = VanDurableState.SPEAKING, speaking = true, mouthOpen = 0.1f),
            VanSceneFrame(phase = 0.2f),
        ).filterIsInstance<VanDrawOp.Oval>().filter { (it.color and 0x00FFFFFF) == (VanScene.MOUTH.toInt() and 0x00FFFFFF) }
        val open = VanScene.build(
            VanVisualState(durableState = VanDurableState.SPEAKING, speaking = true, mouthOpen = 1f),
            VanSceneFrame(phase = 0.2f),
        ).filterIsInstance<VanDrawOp.Oval>().filter { (it.color and 0x00FFFFFF) == (VanScene.MOUTH.toInt() and 0x00FFFFFF) }

        assertTrue("mouth missing while speaking", closed.isNotEmpty() && open.isNotEmpty())
        assertTrue("mouth should open further with viseme drive", open.first().ry > closed.first().ry)
    }

    @Test
    fun gazeFollowsAttentionInputs() {
        fun irisCenters(x: Float) = VanScene.build(
            VanVisualState(durableState = VanDurableState.ATTENTIVE, attentionX = x),
            VanSceneFrame(phase = 0.2f),
        ).filterIsInstance<VanDrawOp.Circle>()
            .filter { (it.color and 0x00FFFFFF) == (VanScene.EYE_IRIS.toInt() and 0x00FFFFFF) }
            .map { it.cx }

        val left = irisCenters(-1f)
        val right = irisCenters(1f)
        assertTrue("gaze did not track attention_x", right.first() > left.first())
    }

    private fun extentOf(op: VanDrawOp): List<Float> = when (op) {
        is VanDrawOp.Circle -> listOf(op.cx - op.r, op.cx + op.r, op.cy - op.r, op.cy + op.r)
        is VanDrawOp.Oval -> listOf(op.cx - op.rx, op.cx + op.rx, op.cy - op.ry, op.cy + op.ry)
        is VanDrawOp.RoundRect -> listOf(
            op.cx - op.halfW,
            op.cx + op.halfW,
            op.cy - op.halfH,
            op.cy + op.halfH,
        )
        is VanDrawOp.Arc -> listOf(op.cx - op.r, op.cx + op.r, op.cy - op.r, op.cy + op.r)
        is VanDrawOp.PathOp -> op.segments.flatMap { seg ->
            when (seg) {
                is VanPathSeg.MoveTo -> listOf(seg.x, seg.y)
                is VanPathSeg.LineTo -> listOf(seg.x, seg.y)
                is VanPathSeg.QuadTo -> listOf(seg.x, seg.y, seg.cx, seg.cy)
                VanPathSeg.Close -> emptyList()
            }
        }
    }
}
