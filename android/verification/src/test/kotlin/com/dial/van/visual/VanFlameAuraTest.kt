package com.dial.van.visual

import kotlin.math.abs
import kotlin.math.sqrt
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * CF-D-06 — VAN's aura is a flame envelope around his silhouette (the Goku / Naruto read the
 * owner asked for), not a detached field. These tests pin what makes it read that way.
 */
class VanFlameAuraTest {

    private val cx = 400f
    private val cy = 400f
    private val radius = 200f
    private val edge = radius * 2f

    private fun plan(
        state: VanDurableState,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
        semantic: VanDurableState = state,
    ) = VanAuraPlanner.plan(
        spec = VanAuraSpecs.forState(state, budget),
        semanticSpec = VanAuraSpecs.forState(semantic, budget),
        centerX = cx, centerY = cy, radius = radius, budget = budget, phase = phase,
    )

    /** The envelope rings (one closed path around the whole figure), not fragments or wisps. */
    private fun flames(state: VanDurableState, budget: VanEffectBudget = VanEffectBudget.FULL, phase: Float = 0.18f) =
        plan(state, budget, phase).filterIsInstance<VanAuraOp.Flame>().filter { it.path.size > VanFlameAura.SAMPLES }

    private fun VanAuraOp.Flame.points(): List<Pair<Float, Float>> = path.mapNotNull {
        when (it) {
            is VanPathSeg.MoveTo -> it.x to it.y
            is VanPathSeg.LineTo -> it.x to it.y
            is VanPathSeg.QuadTo -> it.cx to it.cy
            VanPathSeg.Close -> null
        }
    }

    private fun insideBody(x: Float, y: Float): Boolean =
        VanBodyLayout.contains((x - cx) / edge + 0.5f, (y - cy) / edge + 0.5f)

    @Test
    fun `every state that has an aura has a flame envelope`() {
        for (state in VanDurableState.entries) {
            val spec = VanAuraSpecs.forState(state)
            if (spec.intensity <= 0.01f) continue
            assertTrue(flames(state).size >= 3, "$state has no layered flame envelope")
        }
    }

    @Test
    fun `the envelope wraps the silhouette without covering it`() {
        // Every tongue vertex sits outside the body: the flames hug VAN, they are not painted
        // over him.
        for (state in listOf(VanDurableState.IDLE, VanDurableState.WORKING, VanDurableState.URGENT)) {
            for (flame in flames(state)) {
                val inside = flame.points().count { (x, y) -> insideBody(x, y) }
                assertEquals(0, inside, "$state flame layer has $inside vertices inside the body")
            }
        }
    }

    @Test
    fun `flames rise above the head`() {
        val crownY = cy + (VanBodyLayout.HAIR_CROWN_V - 0.5f) * edge
        val top = flames(VanDurableState.WORKING).minOf { f -> f.points().minOf { it.second } }
        assertTrue(top < crownY - edge * 0.10f, "the tallest tongue ($top) barely clears the crown ($crownY)")
    }

    @Test
    fun `a working VAN flares and a sleeping one smoulders`() {
        fun height(state: VanDurableState): Float {
            val crownY = cy + (VanBodyLayout.HAIR_CROWN_V - 0.5f) * edge
            return crownY - flames(state).minOf { f -> f.points().minOf { it.second } }
        }
        assertTrue(height(VanDurableState.WORKING) > height(VanDurableState.IDLE))
        assertTrue(height(VanDurableState.IDLE) > height(VanDurableState.SLEEPING))
        val sleepingAlpha = flames(VanDurableState.SLEEPING).maxOf { it.alpha }
        val workingAlpha = flames(VanDurableState.WORKING).maxOf { it.alpha }
        assertTrue(workingAlpha > sleepingAlpha * 1.5f, "working $workingAlpha vs sleeping $sleepingAlpha")
    }

    @Test
    fun `no tongue escapes the aura envelope reach`() {
        for (state in VanDurableState.entries) {
            val reach = radius * VanAuraSpec.MAX_ENVELOPE_SCALE + 0.5f
            for (flame in flames(state)) {
                for ((x, y) in flame.points()) {
                    val d = sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy))
                    assertTrue(d <= reach, "$state tongue at $d px, reach $reach")
                }
            }
        }
    }

    @Test
    fun `the outer flame carries the state colour and the core runs white-hot`() {
        val error = VanAuraSpecs.forState(VanDurableState.ERROR).semanticColor!!
        val layers = plan(VanDurableState.IDLE, semantic = VanDurableState.ERROR).filterIsInstance<VanAuraOp.Flame>()
            .filter { it.path.size > VanFlameAura.SAMPLES }
        assertTrue(layers.any { it.color and 0xFFFFFF == error and 0xFFFFFF }, "the semantic colour never reached the flames")
        val core = layers.last()
        val r = (core.color shr 16) and 0xFF; val g = (core.color shr 8) and 0xFF; val b = core.color and 0xFF
        assertTrue(minOf(r, g, b) > 180, "the core layer is not near-white: #${Integer.toHexString(core.color)}")
        val idle = flames(VanDurableState.IDLE)
        assertTrue(idle.any { it.color and 0xFFFFFF == VanGlassTokens.ACCENT_CYAN and 0xFFFFFF }, "identity cyan missing when no state colour applies")
    }

    @Test
    fun `the fire moves with the phase and loops without a jump`() {
        val a = flames(VanDurableState.WORKING, phase = 0.10f)
        val b = flames(VanDurableState.WORKING, phase = 0.35f)
        assertNotEquals(a, b, "the flames did not move between phases")
        val start = flames(VanDurableState.WORKING, phase = 0f)
        val end = flames(VanDurableState.WORKING, phase = 1f)
        for ((s, e) in start.zip(end)) {
            for ((p, q) in s.points().zip(e.points())) {
                assertTrue(abs(p.first - q.first) < 0.6f && abs(p.second - q.second) < 0.6f, "the loop jumps at the wrap")
            }
        }
    }

    @Test
    fun `embers rise off a busy aura and a static budget draws none`() {
        val embers = plan(VanDurableState.WORKING).filterIsInstance<VanAuraOp.Dot>()
            .filter { it.bloomRadiusScale == 3.2f }
        assertTrue(embers.size >= 5, "only ${embers.size} embers on a working aura")
        val still = plan(VanDurableState.WORKING, budget = VanEffectBudget.STATIC).filterIsInstance<VanAuraOp.Dot>()
            .filter { it.bloomRadiusScale == 3.2f }
        assertTrue(still.isEmpty())
        assertTrue(flames(VanDurableState.WORKING, VanEffectBudget.STATIC).size < flames(VanDurableState.WORKING).size)
    }

    @Test
    fun `the flame plan is deterministic`() {
        assertEquals(flames(VanDurableState.LISTENING, phase = 0.42f), flames(VanDurableState.LISTENING, phase = 0.42f))
    }

    @Test
    fun `the silhouette is Candidate B's compact build`() {
        val heads = (VanBodyLayout.SOLE_V - VanBodyLayout.HAIR_CROWN_V) / (VanBodyLayout.CHIN_V - VanBodyLayout.HAIR_CROWN_V)
        assertTrue(heads in 2.9f..3.5f, "silhouette is $heads heads, outside the locked 3.2 ± 0.3")
        assertTrue(VanBodyLayout.contains(0.49f, 0.20f), "no head at the top")
        assertTrue(VanBodyLayout.contains(0.40f, 0.88f), "no boot at the bottom")
        assertTrue(!VanBodyLayout.contains(0.05f, 0.05f))
    }

    // ---- Aura Rev 2 (CF-D-08) --------------------------------------------------------------

    private fun ops(state: VanDurableState, phase: Float = 0.18f, slow: Float = 0f, pulse: Float = 0f,
                    silhouette: VanSilhouette? = null, budget: VanEffectBudget = VanEffectBudget.FULL) =
        VanAuraPlanner.plan(
            spec = VanAuraSpecs.forState(state, budget), semanticSpec = VanAuraSpecs.forState(state, budget),
            centerX = cx, centerY = cy, radius = radius, budget = budget, phase = phase,
            silhouette = silhouette, slowPhase = slow, pulse = pulse,
        )

    private val crownY get() = cy + (VanBodyLayout.HAIR_CROWN_V - 0.5f) * edge

    @Test
    fun `flame fragments break off and rise above the envelope`() {
        val fragments = ops(VanDurableState.WORKING).filterIsInstance<VanAuraOp.Flame>()
            .filter { !it.front && it.path.size <= VanFlameAura.SAMPLES }
        assertTrue(fragments.size >= 3, "only ${fragments.size} fragments on a working aura")
        assertTrue(fragments.size <= VanFlameAura.MAX_FRAGMENTS)
        assertTrue(fragments.any { f -> f.points().minOf { it.second } < crownY - edge * 0.12f }, "no fragment clears the crown")
        val still = ops(VanDurableState.WORKING, budget = VanEffectBudget.STATIC).filterIsInstance<VanAuraOp.Flame>()
            .filter { it.path.size <= VanFlameAura.SAMPLES }
        assertTrue(still.isEmpty(), "a static budget must not animate fragments")
    }

    @Test
    fun `front wisps cross the lower body only, never the face, and stay translucent`() {
        val front = ops(VanDurableState.WORKING).filter { it.front }
        val wisps = front.filterIsInstance<VanAuraOp.Flame>()
        assertTrue(wisps.isNotEmpty(), "no front wisps: the field has no depth")
        val shape = VanSilhouette.fromLayout()
        val faceLine = cy + (shape.topV + VanFlameAura.FRONT_TOP_FRACTION * (shape.bottomV - shape.topV) - 0.5f) * edge
        for (w in wisps) {
            assertTrue(w.alpha <= VanFlameAura.FRONT_ALPHA_MAX + 1e-4f, "front wisp alpha ${w.alpha}")
            assertTrue(w.points().minOf { it.second } >= faceLine - 0.5f, "a front wisp rises over the face")
        }
        assertTrue(ops(VanDurableState.IDLE).filter { !it.front }.none { it is VanAuraOp.Rim }, "rim must be in front")
    }

    @Test
    fun `the rim lights VAN's edge and never bridges a gap across the background`() {
        val rim = ops(VanDurableState.WORKING).filterIsInstance<VanAuraOp.Rim>().single()
        assertTrue(rim.alpha <= VanFlameAura.RIM_ALPHA_MAX + 1e-4f)
        assertTrue(rim.runs.size >= 2, "one continuous rim would have to cross the gap between the legs")
        for (run in rim.runs) {
            for ((a, b) in run.zipWithNext()) {
                val mx = (a.x + b.x) / 2f; val my = (a.y + b.y) / 2f
                val gap = kotlin.math.hypot(b.x - a.x, b.y - a.y)
                assertTrue(gap < edge * 0.08f, "rim chord of $gap px spans empty space")
                assertTrue(insideBody(mx + (cx - mx) * 0.05f, my + (cy - my) * 0.05f) || insideBody(mx, my) ||
                    gap < edge * 0.02f, "rim chord crosses the background at ($mx,$my)")
            }
        }
    }

    @Test
    fun `the slow clock changes the fire while the fast loop stays seamless`() {
        val a = flames(VanDurableState.WORKING, phase = 0.3f)
        val b = ops(VanDurableState.WORKING, phase = 0.3f, slow = 0.37f).filterIsInstance<VanAuraOp.Flame>()
            .filter { it.path.size > VanFlameAura.SAMPLES }
        assertNotEquals(a, b, "the second clock does nothing: the loop would visibly repeat")
        val s0 = ops(VanDurableState.WORKING, phase = 0f, slow = 0.37f).filterIsInstance<VanAuraOp.Flame>().filter { it.path.size > VanFlameAura.SAMPLES }
        val s1 = ops(VanDurableState.WORKING, phase = 1f, slow = 0.37f).filterIsInstance<VanAuraOp.Flame>().filter { it.path.size > VanFlameAura.SAMPLES }
        for ((x, y) in s0.zip(s1)) for ((p, q) in x.points().zip(y.points())) {
            assertTrue(abs(p.first - q.first) < 0.6f && abs(p.second - q.second) < 0.6f, "fast loop jumps at the wrap")
        }
    }

    @Test
    fun `a pulse expands and whitens the fire`() {
        fun top(p: Float) = ops(VanDurableState.IDLE, pulse = p).filterIsInstance<VanAuraOp.Flame>()
            .filter { it.path.size > VanFlameAura.SAMPLES }.minOf { f -> f.points().minOf { it.second } }
        assertTrue(top(1f) < top(0f) - edge * 0.03f, "the pulse did not expand the field")
    }

    @Test
    fun `a live alpha mask drives the flames`() {
        // A tall capsule-shaped figure, off to the left: flames must follow it, not the layout.
        val w = 64; val h = 64
        val mask = ByteArray(w * h) { i ->
            val x = i % w; val y = i / w
            if (x in 14..26 && y in 8..58) 255.toByte() else 0
        }
        val shape = VanSilhouette.fromAlphaMask(w, h, mask)!!
        assertEquals(20.5f / 64f, shape.centerU, 0.02f)
        assertTrue(shape.contains(0.31f, 0.5f) && !shape.contains(0.7f, 0.5f))
        val rings = ops(VanDurableState.WORKING, silhouette = shape).filterIsInstance<VanAuraOp.Flame>()
            .filter { it.path.size > VanFlameAura.SAMPLES }
        for (ring in rings) for ((x, y) in ring.points()) {
            assertTrue(!shape.contains((x - cx) / edge + 0.5f, (y - cy) / edge + 0.5f), "a tongue lands inside the masked figure")
        }
        val meanX = rings.first().points().map { it.first }.average()
        assertTrue(meanX < cx - edge * 0.05f, "the flames did not move with the figure: mean x $meanX")
        assertNull(VanSilhouette.fromAlphaMask(w, h, ByteArray(w * h)), "an empty mask must not replace the last silhouette")
    }
}
