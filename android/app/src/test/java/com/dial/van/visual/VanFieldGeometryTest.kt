package com.dial.van.visual

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import kotlin.math.roundToInt

class VanFieldGeometryTest {

    @Test
    fun semanticStatesRemainGeometricallyDistinctNotColourOnly() {
        val states = listOf(
            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.WARNING,
            VanDurableState.ERROR,
            VanDurableState.URGENT,
            VanDurableState.SUCCESS,
        )
        val signatures = states.map { state ->
            val spec = VanAuraSpecs.forState(state)
            val geometry = VanFieldGeometryEngine.build(
                spec = spec,
                phase = 0.31f,
                budget = VanEffectBudget.FULL,
                bodyEdge = 200f,
                centerX = 160f,
                centerY = 160f,
            )
            val semantic = geometry.strokes.filter { it.ink == VanFieldInk.SEMANTIC }
            assertTrue("$state missing semantic windy geometry", semantic.isNotEmpty())
            signature(semantic)
        }

        assertEquals(states.size, signatures.toSet().size)
    }

    @Test
    fun degradedSemanticEnvelopeDoesNotReplaceListeningInteractionField() {
        val listening = VanAuraSpecs.forState(VanDurableState.LISTENING)
        val degraded = VanAuraSpecs.forState(VanDurableState.DEGRADED)
        val listeningOnly = VanFieldGeometryEngine.build(
            spec = listening,
            phase = 0.31f,
            budget = VanEffectBudget.FULL,
            bodyEdge = 200f,
            centerX = 160f,
            centerY = 160f,
        )
        val degradedOnly = VanFieldGeometryEngine.build(
            spec = degraded,
            phase = 0.31f,
            budget = VanEffectBudget.FULL,
            bodyEdge = 200f,
            centerX = 160f,
            centerY = 160f,
        )
        val composite = VanFieldGeometryEngine.build(
            spec = listening,
            semanticSpec = degraded,
            phase = 0.31f,
            budget = VanEffectBudget.FULL,
            bodyEdge = 200f,
            centerX = 160f,
            centerY = 160f,
        )

        assertEquals(
            signature(listeningOnly.strokes.filter { it.ink == VanFieldInk.IDENTITY }),
            signature(composite.strokes.filter { it.ink == VanFieldInk.IDENTITY }),
        )
        assertEquals(
            signature(degradedOnly.strokes.filter { it.ink == VanFieldInk.SEMANTIC }),
            signature(composite.strokes.filter { it.ink == VanFieldInk.SEMANTIC }),
        )
    }

    @Test
    fun zoneBAndZoneCNeverEnterBodySafeCore() {
        val geometry = VanFieldGeometryEngine.build(
            spec = VanAuraSpecs.forState(VanDurableState.WORKING),
            phase = 0.42f,
            budget = VanEffectBudget.FULL,
            bodyEdge = 200f,
            centerX = 160f,
            centerY = 160f,
        )

        geometry.strokes.flatMap { it.points }.forEach { point ->
            val nx = (point.x - 160f) / (200f * 0.34f)
            val ny = (point.y - 160f) / (200f * 0.43f)
            assertTrue("field point entered body-safe core: $point", nx * nx + ny * ny >= 0.98f)
        }
    }

    @Test
    fun reducedMotionFreezesSharedGeometryAtAnyPhase() {
        val spec = VanAuraSpecs.forState(VanDurableState.WORKING, VanEffectBudget.REDUCED_MOTION)
        val a = VanFieldGeometryEngine.build(spec, 0.15f, VanEffectBudget.REDUCED_MOTION, 180f, 120f, 120f)
        val b = VanFieldGeometryEngine.build(spec, 0.85f, VanEffectBudget.REDUCED_MOTION, 180f, 120f, 120f)

        fun points(g: VanFieldGeometry): List<Pair<Int, Int>> = g.strokes.flatMap { it.points }.map {
            it.x.roundToInt() to it.y.roundToInt()
        }
        assertEquals(points(a), points(b))
    }

    private fun signature(strokes: List<VanFieldStroke>): String = strokes.joinToString("|") { stroke ->
        val first = stroke.points.first()
        val last = stroke.points.last()
        "${first.x.roundToInt()},${first.y.roundToInt()}->${last.x.roundToInt()},${last.y.roundToInt()}:${stroke.points.size}"
    }
}
