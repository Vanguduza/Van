package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * P1-VIS-001 — one aura description, two executors.
 *
 * The AWT evidence painter was a hand-written second implementation of `VanAura.kt` and had
 * drifted: no electrical branches at all, roughly double the Zone A alpha, 1.5x the radius,
 * differently placed haze blobs, no bloom on ion fragments, different orb-link constants.
 * Every committed piece of visual evidence was a picture of something the app does not look
 * like — which is the worst failure available to a renderer whose only job is evidence.
 *
 * These tests are about the *plan*, because the plan is now the only place those numbers
 * exist. A painter cannot diverge on a value it does not have.
 */
class VanAuraPlanTest {

    private fun plan(
        state: VanDurableState = VanDurableState.LISTENING,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
        radius: Float = 240f,
    ) = VanAuraPlanner.plan(
        spec = VanAuraSpecs.forState(state, budget),
        semanticSpec = VanAuraSpecs.forState(state, budget),
        centerX = 240f, centerY = 240f, radius = radius, budget = budget, phase = phase,
    )

    @Test
    fun `the plan carries the electrical layer the evidence painter omitted`() {
        // Electrical branches are finite events, so sweep the phase rather than asserting
        // that one arbitrary frame has them.
        val sawBranches = (0 until 200).any { index ->
            plan(state = VanDurableState.URGENT, phase = index / 200f)
                .filterIsInstance<VanAuraOp.Polyline>()
                .any { it.whiteCoreWidth != null }
        }
        assertTrue(sawBranches, "no electrical branch reached the plan in a full phase sweep")
    }

    @Test
    fun `an electrical branch has a bright core and a field strand does not`() {
        // That bright inner core is what makes a branch read as discharge rather than as
        // another ribbon; the evidence painter drew neither.
        val ops = (0 until 200).firstNotNullOfOrNull { index ->
            plan(state = VanDurableState.URGENT, phase = index / 200f)
                .filterIsInstance<VanAuraOp.Polyline>()
                .takeIf { list -> list.any { it.whiteCoreWidth != null } }
        }
        assertNotNull(ops)
        val branch = ops.first { it.whiteCoreWidth != null }
        val strand = ops.first { it.whiteCoreWidth == null }
        assertTrue(branch.whiteCoreAlpha > 0f)
        assertTrue(branch.whiteCoreWidth!! < branch.width, "the core should sit inside the stroke")
        assertEquals(0f, strand.whiteCoreAlpha)
    }

    @Test
    fun `Zone A carries the shipping alpha, not the evidence painter's doubled one`() {
        // The shipping Compose values: 0.045 + 0.045*intensity clamped to 0.035..0.085.
        // The AWT painter used 0.10 + 0.08*intensity clamped to 0.08..0.18.
        for (state in VanDurableState.entries) {
            val radials = plan(state).filterIsInstance<VanAuraOp.Radial>()
            if (radials.isEmpty()) continue
            val haze = radials.first()
            assertTrue(
                haze.alpha <= VanAuraPlanner.ZONE_A_ALPHA_MAX + 0.0001f,
                "$state Zone A alpha is ${haze.alpha}, above the shipping ceiling",
            )
            assertTrue(haze.alpha >= VanAuraPlanner.ZONE_A_ALPHA_MIN - 0.0001f, "$state: ${haze.alpha}")
        }
    }

    @Test
    fun `Zone A blobs are displaced so the haze cannot read as a body outline`() {
        val radials = plan().filterIsInstance<VanAuraOp.Radial>()
        assertTrue(radials.size >= 2)
        val first = radials[0]
        val second = radials[1]
        // The evidence painter placed both near the centre (-0.05 and +0.07 of bodyEdge),
        // which produces a halo. The shipping values are -0.31 and +0.34.
        assertTrue(first.cx < 240f, "the first blob is not displaced left")
        assertTrue(second.cx > 240f, "the second blob is not displaced right")
        assertTrue(
            second.cx - first.cx > 240f,
            "the blobs are ${second.cx - first.cx}px apart; they will read as one halo",
        )
    }

    @Test
    fun `ion fragments bloom`() {
        val dots = plan().filterIsInstance<VanAuraOp.Dot>()
        assertTrue(dots.isNotEmpty(), "no ion fragments at all")
        for (dot in dots) {
            assertTrue(dot.bloomRadiusScale > 1f, "the fragment has no bloom")
            assertTrue(dot.bloomAlphaScale in 0.01f..0.5f)
        }
    }

    @Test
    fun `the ground glow is clipped to a crescent, never a plate`() {
        val ground = plan(state = VanDurableState.IDLE)
            .filterIsInstance<VanAuraOp.Radial>()
            .firstOrNull { it.clip.isNotEmpty() }
        assertNotNull(ground, "no clipped ground glow")
        assertTrue(ground.clip.last() is VanPathSeg.Close, "the crescent is not closed")
        assertTrue(ground.cy > 240f, "the ground glow is not below VAN")
    }

    @Test
    fun `nothing is planned for a body too small or a field too quiet`() {
        // Both painters used to carry their own copy of this guard.
        assertTrue(plan(radius = 0.5f).isEmpty())
        val silent = VanAuraSpec(
            intensity = 0f, arcActivity = 0f, sparkRate = 0f, groundGlow = 0f,
            orbLink = 0f, alertAccent = null,
        )
        assertTrue(
            VanAuraPlanner.plan(
                spec = silent, semanticSpec = silent,
                centerX = 240f, centerY = 240f, radius = 240f,
            ).isEmpty(),
        )
    }

    @Test
    fun `the plan is deterministic for the same inputs`() {
        // Reproducible evidence depends on it: two renders of the same frame must be the
        // same bytes, or every regeneration churns the manifest.
        assertEquals(plan(phase = 0.42f), plan(phase = 0.42f))
    }

    @Test
    fun `semantic colour reaches Zone C and never the identity haze`() {
        val error = VanAuraSpecs.forState(VanDurableState.ERROR)
        val ops = VanAuraPlanner.plan(
            spec = VanAuraSpecs.forState(VanDurableState.IDLE),
            semanticSpec = error,
            centerX = 240f, centerY = 240f, radius = 240f,
        )
        val hazeColours = ops.filterIsInstance<VanAuraOp.Radial>().map { it.color }.toSet()
        assertEquals(setOf(VanGlassTokens.ACCENT_CYAN), hazeColours, "semantic colour leaked onto the haze")
        val semantic = error.semanticColor
        if (semantic != null) {
            assertTrue(
                ops.filterIsInstance<VanAuraOp.Polyline>().any { it.color == semantic },
                "the semantic colour never reached the field",
            )
        }
    }

    @Test
    fun `a still budget still produces a field`() {
        // REDUCED_MOTION is a designed still field, not an impoverished one.
        val still = plan(budget = VanEffectBudget.REDUCED_MOTION)
        assertTrue(still.isNotEmpty())
        assertTrue(still.filterIsInstance<VanAuraOp.Radial>().isNotEmpty())
    }

    @Test
    fun `the orb link is planned only when the spec asks for it`() {
        val quiet = VanAuraSpecs.forState(VanDurableState.IDLE).copy(orbLink = 0f)
        val ops = VanAuraPlanner.plan(
            spec = quiet, semanticSpec = quiet, centerX = 240f, centerY = 240f, radius = 240f,
        )
        assertNull(ops.filterIsInstance<VanAuraOp.Quad>().firstOrNull())
        val linked = quiet.copy(orbLink = 0.6f)
        assertNotNull(
            VanAuraPlanner.plan(
                spec = linked, semanticSpec = linked, centerX = 240f, centerY = 240f, radius = 240f,
            ).filterIsInstance<VanAuraOp.Quad>().firstOrNull(),
        )
    }
}
