package com.dial.van.visual

import kotlin.math.max

/**
 * One description of the aura, rendered by both painters.
 *
 * P1-VIS-001. `android/visual-preview` shares the *geometry* sources with the app but not
 * `VanAura.kt`, because `VanAura.kt` is Compose and the preview renders with Java2D. So the
 * AWT painter reimplemented the aura by hand, and the two drifted exactly as reimplemented
 * code does:
 *
 * * the AWT painter never drew `electricalBranches` at all — an entire visual layer missing
 *   from every piece of committed visual evidence;
 * * its Zone A alpha was roughly double the shipping value;
 * * its Zone A radius was roughly 1.5x;
 * * its Zone A blobs sat in different places;
 * * its ion fragments had no bloom;
 * * its orb link used different pulse constants and different control points.
 *
 * Every one of those is a number that appeared twice and was changed once. So neither
 * painter owns any of them any more: this file computes the aura as a list of typed ops in
 * pixel space, and both painters become executors that know how to stroke a path and fill a
 * radial gradient. A painter cannot diverge on a value it does not have.
 *
 * The ops are deliberately not `VanDrawOp`: that type is a unit-square description of VAN's
 * *body*, with flat fills and strokes. The aura needs radial gradients, layered glow passes
 * and absolute pixel coordinates, and folding the two together would make both worse.
 *
 * Pure Kotlin, no Android and no AWT, so it compiles into the app, into the preview renderer
 * and into the JVM verification harness — which is what makes the drift testable.
 */
sealed interface VanAuraOp {
    /** Packed ARGB, ignoring its alpha channel; [alpha] carries opacity. */
    val color: Int
    val alpha: Float

    /**
     * A soft radial falloff. Zone A identity haze and the ground crescent.
     *
     * [clip] is the ground glow's crescent: the gradient is drawn only inside it, so the
     * illumination reads as light on a surface rather than as a plate under VAN.
     */
    data class Radial(
        val cx: Float,
        val cy: Float,
        val radius: Float,
        override val color: Int,
        override val alpha: Float,
        val clip: List<VanPathSeg> = emptyList(),
    ) : VanAuraOp

    /**
     * A field strand. Rendered as a wide low-alpha glow pass and then the core.
     *
     * [whiteCoreWidth] is non-null only for electrical branches, whose bright inner core is
     * what makes them read as discharge rather than as another ribbon.
     */
    data class Polyline(
        val points: List<VanFieldPoint>,
        override val color: Int,
        override val alpha: Float,
        val width: Float,
        val glowWidth: Float,
        val glowAlphaScale: Float = 0.20f,
        val glowAlphaCeiling: Float = 0.18f,
        val whiteCoreWidth: Float? = null,
        val whiteCoreAlpha: Float = 0f,
    ) : VanAuraOp

    /** An ion fragment: a small bloom and a solid core. */
    data class Dot(
        val cx: Float,
        val cy: Float,
        val radius: Float,
        override val color: Int,
        override val alpha: Float,
        val bloomRadiusScale: Float = 2.8f,
        val bloomAlphaScale: Float = 0.16f,
    ) : VanAuraOp

    /** The occasional bridge toward the orb companion. */
    data class Quad(
        val startX: Float,
        val startY: Float,
        val controlX: Float,
        val controlY: Float,
        val endX: Float,
        val endY: Float,
        override val color: Int,
        override val alpha: Float,
        val width: Float,
    ) : VanAuraOp
}

object VanAuraPlanner {

    // The Zone A constants, in one place. These are the shipping Compose values; the AWT
    // painter's differing ones are gone rather than reconciled, because the shipping app is
    // what the evidence is supposed to be evidence of.
    const val ZONE_A_ALPHA_BASE = 0.045f
    const val ZONE_A_ALPHA_PER_INTENSITY = 0.045f
    const val ZONE_A_ALPHA_MIN = 0.035f
    const val ZONE_A_ALPHA_MAX = 0.085f
    const val ZONE_A_RADIUS_SCALE = 0.13f
    const val ZONE_A_FIRST_X = -0.31f
    const val ZONE_A_FIRST_Y = 0.05f
    const val ZONE_A_SECOND_X = 0.34f
    const val ZONE_A_SECOND_Y = -0.09f
    const val ZONE_A_SECOND_ALPHA_SCALE = 0.72f
    const val ZONE_A_SECOND_RADIUS_SCALE = 0.78f
    const val GROUND_GLOW_Y = 0.47f
    const val GROUND_GLOW_WIDTH = 0.28f
    const val GROUND_GLOW_ALPHA = 0.13f
    const val ORB_PULSE_BASE = 0.18f
    const val ORB_PULSE_RANGE = 0.34f
    const val DOT_BLOOM_RADIUS_SCALE = 2.8f
    const val DOT_BLOOM_ALPHA_SCALE = 0.16f
    const val BRANCH_CHILD_ALPHA_SCALE = 0.82f
    const val BRANCH_CHILD_WIDTH_SCALE = 0.78f
    const val BRANCH_CHILD_GLOW_SCALE = 0.72f

    /**
     * The whole aura, in draw order: Zone A haze, then the field, then the electrical
     * branches, then ion fragments, then the orb link.
     *
     * Returns an empty list for a body too small or a field too quiet to draw, so a caller
     * does not need its own guard — the AWT painter's guard and the Compose painter's guard
     * were themselves two copies of the same condition.
     */
    fun plan(
        spec: VanAuraSpec,
        semanticSpec: VanAuraSpec,
        centerX: Float,
        centerY: Float,
        radius: Float,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        phase: Float = 0.18f,
        identityColor: Int = VanGlassTokens.ACCENT_CYAN,
        bodyEdgeDp: Float? = null,
    ): List<VanAuraOp> {
        if (radius <= 1f || (spec.intensity <= 0.01f && semanticSpec.intensity <= 0.01f)) {
            return emptyList()
        }
        val bodyEdge = radius * 2f
        val semanticColor = semanticSpec.semanticColor ?: identityColor
        val motion = VanWindFieldMotion.sample(spec, phase, budget)
        val ops = mutableListOf<VanAuraOp>()

        ops += zoneA(spec, motion, centerX, centerY, bodyEdge, identityColor)

        val geometry = VanFieldGeometryEngine.build(
            spec = spec,
            phase = phase,
            budget = budget,
            bodyEdge = bodyEdge,
            centerX = centerX,
            centerY = centerY,
            semanticSpec = semanticSpec,
            bodyEdgeDp = bodyEdgeDp,
        )

        for (stroke in geometry.strokes) {
            ops += VanAuraOp.Polyline(
                points = stroke.points,
                color = if (stroke.ink == VanFieldInk.IDENTITY) identityColor else semanticColor,
                alpha = stroke.alpha,
                width = stroke.width,
                glowWidth = stroke.glowWidth,
            )
        }

        // The layer the AWT painter never drew.
        for (branch in geometry.electricalBranches) {
            val color = if (branch.ink == VanFieldInk.IDENTITY) identityColor else semanticColor
            ops += electrical(branch.trunk, color, branch.alpha, branch.width, branch.glowWidth)
            for (child in branch.children) {
                ops += electrical(
                    child,
                    color,
                    branch.alpha * BRANCH_CHILD_ALPHA_SCALE,
                    branch.width * BRANCH_CHILD_WIDTH_SCALE,
                    branch.glowWidth * BRANCH_CHILD_GLOW_SCALE,
                )
            }
        }

        for (dot in geometry.dots) {
            ops += VanAuraOp.Dot(
                cx = dot.point.x,
                cy = dot.point.y,
                radius = dot.radius,
                color = if (dot.ink == VanFieldInk.IDENTITY) identityColor else semanticColor,
                alpha = dot.alpha,
                bloomRadiusScale = DOT_BLOOM_RADIUS_SCALE,
                bloomAlphaScale = DOT_BLOOM_ALPHA_SCALE,
            )
        }

        if (spec.orbLink > 0.05f) {
            val pulse = ORB_PULSE_BASE + ORB_PULSE_RANGE * motion.electricPulse
            ops += VanAuraOp.Quad(
                startX = centerX + bodyEdge * 0.18f,
                startY = centerY - bodyEdge * 0.03f,
                controlX = centerX + bodyEdge * 0.30f,
                controlY = centerY - bodyEdge * 0.19f,
                endX = centerX + bodyEdge * 0.39f,
                endY = centerY - bodyEdge * 0.12f,
                color = identityColor,
                alpha = pulse * spec.orbLink,
                width = max(bodyEdge * 0.009f, 1f),
            )
        }
        return ops
    }

    private fun electrical(
        points: List<VanFieldPoint>,
        color: Int,
        alpha: Float,
        width: Float,
        glowWidth: Float,
    ): List<VanAuraOp> {
        if (points.size < 2 || alpha <= 0.01f) return emptyList()
        return listOf(
            VanAuraOp.Polyline(
                points = points,
                color = color,
                alpha = minOf(alpha, 0.92f),
                width = width,
                glowWidth = glowWidth,
                glowAlphaScale = 0.20f,
                glowAlphaCeiling = 0.22f,
                whiteCoreWidth = max(width * 0.48f, 0.55f),
                whiteCoreAlpha = minOf(alpha * 0.62f, 0.82f),
            ),
        )
    }

    private fun zoneA(
        spec: VanAuraSpec,
        motion: VanWindFieldFrame,
        centerX: Float,
        centerY: Float,
        bodyEdge: Float,
        cyan: Int,
    ): List<VanAuraOp> {
        val alpha = (ZONE_A_ALPHA_BASE + ZONE_A_ALPHA_PER_INTENSITY * spec.intensity)
            .coerceIn(ZONE_A_ALPHA_MIN, ZONE_A_ALPHA_MAX)
        val r = bodyEdge * ZONE_A_RADIUS_SCALE * motion.breathing
        val driftX = bodyEdge * 0.032f * sinTau(motion.phase)
        val driftY = bodyEdge * 0.022f * sinTau(2f * motion.phase + 0.9f / TAU)

        val ops = mutableListOf<VanAuraOp>(
            VanAuraOp.Radial(
                cx = centerX + bodyEdge * ZONE_A_FIRST_X + driftX,
                cy = centerY + bodyEdge * ZONE_A_FIRST_Y + driftY,
                radius = r, color = cyan, alpha = alpha,
            ),
            VanAuraOp.Radial(
                cx = centerX + bodyEdge * ZONE_A_SECOND_X - driftX * 0.6f,
                cy = centerY + bodyEdge * ZONE_A_SECOND_Y - driftY,
                radius = r * ZONE_A_SECOND_RADIUS_SCALE,
                color = cyan, alpha = alpha * ZONE_A_SECOND_ALPHA_SCALE,
            ),
        )

        if (spec.groundGlow > 0.01f) {
            val gy = centerY + bodyEdge * GROUND_GLOW_Y
            val gw = bodyEdge * GROUND_GLOW_WIDTH
            ops += VanAuraOp.Radial(
                cx = centerX, cy = gy, radius = gw, color = cyan,
                alpha = GROUND_GLOW_ALPHA * spec.groundGlow,
                clip = listOf(
                    VanPathSeg.MoveTo(centerX - gw, gy),
                    VanPathSeg.QuadTo(centerX, gy + bodyEdge * 0.045f, centerX + gw, gy),
                    VanPathSeg.QuadTo(centerX, gy - bodyEdge * 0.012f, centerX - gw, gy),
                    VanPathSeg.Close,
                ),
            )
        }
        return ops
    }

    private const val TAU = 6.2831855f

    private fun sinTau(turns: Float): Float = kotlin.math.sin(TAU * turns)
}
