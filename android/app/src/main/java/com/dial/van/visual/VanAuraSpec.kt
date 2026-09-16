package com.dial.van.visual

/**
 * Living refractive aura specification.
 *
 * Rev 2.2: three-zone field. Zone A identity, Zone B activity, Zone C outer semantic envelope.
 * Source: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_2_ADDENDUM_AURA_SEMANTIC_ENVELOPE.md`.
 *
 * A full circular ring is forbidden. Semantic colour lives in Zone C, not on VAN's body.
 */
data class VanAuraEnvelopeSegment(
    val startDeg: Float,
    val sweepDeg: Float,
    val node: Boolean = false,
)

data class VanAuraSpec(
    /** Field intensity, 0..1. */
    val intensity: Float,
    /** Arc / filament activity, 0..1 — drives filament count and broken-arc energy. */
    val arcActivity: Float,
    /** Micro-spark frequency, 0..1. */
    val sparkRate: Float,
    /** Soft illumination under the body; rendered as a crescent, never a plate. */
    val groundGlow: Float,
    /** Occasional energy bridge toward the orb companion. */
    val orbLink: Float,
    /** Secondary accent for warning/approval glass; not the inner aura colour. */
    val alertAccent: Int?,
    /** Filament count in the 2–5 band (0 when the field is fully quiet). */
    val filamentCount: Int = 0,
    /** Horizontal stretch so the outer field cannot read as a circle. */
    val fieldAsymmetry: Float = 0.18f,
    /** Radial wobble that deforms the outer field away from an ellipse. */
    val deformation: Float = 0.16f,
    /** Zone C radius relative to the Zone B arc radius. Target 1.35–1.70. */
    val envelopeRadiusScale: Float = 1.50f,
    /** Zone C alpha before budget scaling. */
    val envelopeAlpha: Float = 0.12f,
    /** Semantic colour for Zone C only. Null keeps a dim identity-cyan remnant. */
    val semanticColor: Int? = null,
    /** Sparse broken Zone C fragments. Combined sweep must stay ≤ 180°. */
    val envelopeSegments: List<VanAuraEnvelopeSegment> = emptyList(),
) {
    /** Hard ceiling: the aura must never obscure facial features or outfit details. */
    val faceSafe: Boolean get() = intensity <= MAX_INTENSITY

    fun envelopeCoverageDeg(): Float = envelopeSegments.sumOf { it.sweepDeg.toDouble() }.toFloat()

    fun segmentsForBudget(budget: VanEffectBudget): List<VanAuraEnvelopeSegment> {
        if (envelopeSegments.isEmpty()) return emptyList()
        val critical = semanticColor != null && envelopeSegments.size >= 2
        val keep = when (budget) {
            VanEffectBudget.STATIC -> if (critical) 2 else 1
            VanEffectBudget.LOW -> 1
            VanEffectBudget.REDUCED, VanEffectBudget.REDUCED_MOTION ->
                envelopeSegments.size.coerceAtMost(2).coerceAtLeast(1)
            else -> envelopeSegments.size
        }.coerceIn(1, envelopeSegments.size.coerceAtMost(MAX_ENVELOPE_SEGMENTS))
        return envelopeSegments.take(keep)
    }

    companion object {
        const val MAX_INTENSITY = 0.75f
        const val MAX_ARC_SWEEP_DEG = 110f
        const val MAX_TOTAL_ARC_DEG = 220f
        const val MAX_ENVELOPE_COVERAGE_DEG = 180f
        const val MAX_ENVELOPE_SEGMENTS = 4
        const val MIN_ENVELOPE_SCALE = 1.35f
        const val MAX_ENVELOPE_SCALE = 1.70f
        const val INNER_RADIUS_SCALE = 1.00f
        const val MID_RADIUS_SCALE = 1.12f
    }
}

object VanAuraSpecs {

    /**
     * Per-state three-zone field. Zone C topology is unique; colour does not carry meaning alone.
     */
    fun forState(state: VanDurableState, budget: VanEffectBudget = VanEffectBudget.FULL): VanAuraSpec {
        val base = when (state) {
            VanDurableState.IDLE -> spec(
                intensity = 0.25f, arc = 0.08f, spark = 0.04f, ground = 0.18f, orb = 0.10f,
                filaments = 2, asymmetry = 0.28f, deform = 0.22f,
                envelopeScale = 1.48f, envelopeAlpha = 0.12f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(210f, 48f)),
            )
            VanDurableState.CONNECTING -> spec(
                intensity = 0.28f, arc = 0.14f, spark = 0.08f, ground = 0.16f, orb = 0.14f,
                filaments = 2, asymmetry = 0.24f, deform = 0.18f,
                envelopeScale = 1.38f, envelopeAlpha = 0.10f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(40f, 36f, node = true)),
            )
            VanDurableState.ATTENTIVE -> spec(
                intensity = 0.32f, arc = 0.18f, spark = 0.08f, ground = 0.20f, orb = 0.16f,
                filaments = 3, asymmetry = 0.22f, deform = 0.16f,
                envelopeScale = 1.42f, envelopeAlpha = 0.11f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(-20f, 48f)),
            )
            VanDurableState.LISTENING -> spec(
                intensity = 0.52f, arc = 0.50f, spark = 0.18f, ground = 0.28f, orb = 0.50f,
                filaments = 4, asymmetry = 0.24f, deform = 0.20f,
                envelopeScale = 1.48f, envelopeAlpha = 0.14f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(300f, 54f)),
            )
            VanDurableState.THINKING -> spec(
                intensity = 0.42f, arc = 0.26f, spark = 0.10f, ground = 0.20f, orb = 0.20f,
                filaments = 3, asymmetry = 0.18f, deform = 0.16f,
                envelopeScale = 1.52f, envelopeAlpha = 0.12f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(310f, 70f)),
            )
            VanDurableState.SEARCHING -> spec(
                intensity = 0.44f, arc = 0.32f, spark = 0.14f, ground = 0.20f, orb = 0.24f,
                filaments = 3, asymmetry = 0.26f, deform = 0.20f,
                envelopeScale = 1.55f, envelopeAlpha = 0.13f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(10f, 62f)),
            )
            VanDurableState.WORKING -> spec(
                intensity = 0.68f, arc = 0.70f, spark = 0.30f, ground = 0.30f, orb = 0.60f,
                filaments = 5, asymmetry = 0.26f, deform = 0.22f,
                envelopeScale = 1.58f, envelopeAlpha = 0.16f, semantic = null,
                segments = listOf(
                    VanAuraEnvelopeSegment(20f, 50f),
                    VanAuraEnvelopeSegment(140f, 40f),
                    VanAuraEnvelopeSegment(250f, 48f),
                ),
            )
            VanDurableState.DELEGATING -> spec(
                intensity = 0.42f, arc = 0.28f, spark = 0.12f, ground = 0.20f, orb = 0.28f,
                filaments = 3, asymmetry = 0.22f, deform = 0.18f,
                envelopeScale = 1.54f, envelopeAlpha = 0.13f, semantic = null,
                segments = listOf(
                    VanAuraEnvelopeSegment(30f, 28f, node = true),
                    VanAuraEnvelopeSegment(210f, 32f, node = true),
                ),
            )
            VanDurableState.SPEAKING -> spec(
                intensity = 0.45f, arc = 0.30f, spark = 0.10f, ground = 0.24f, orb = 0.28f,
                filaments = 3, asymmetry = 0.20f, deform = 0.16f,
                envelopeScale = 1.44f, envelopeAlpha = 0.10f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(200f, 44f)),
            )
            VanDurableState.WAITING -> spec(
                intensity = 0.28f, arc = 0.12f, spark = 0.05f, ground = 0.18f, orb = 0.10f,
                filaments = 2, asymmetry = 0.18f, deform = 0.14f,
                envelopeScale = 1.38f, envelopeAlpha = 0.08f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(180f, 32f)),
            )
            VanDurableState.WAITING_FOR_OWNER -> spec(
                intensity = 0.30f, arc = 0.08f, spark = 0.04f, ground = 0.16f, orb = 0.08f,
                filaments = 2, asymmetry = 0.16f, deform = 0.12f,
                envelopeScale = 1.55f, envelopeAlpha = 0.18f, semantic = VanGlassTokens.ACCENT_AMBER,
                alert = VanGlassTokens.ACCENT_AMBER,
                segments = listOf(
                    VanAuraEnvelopeSegment(-30f, 55f, node = true),
                    VanAuraEnvelopeSegment(150f, 50f, node = true),
                ),
            )
            VanDurableState.DEGRADED -> spec(
                intensity = 0.16f, arc = 0.04f, spark = 0f, ground = 0.10f, orb = 0f,
                filaments = 2, asymmetry = 0.16f, deform = 0.12f,
                envelopeScale = 1.42f, envelopeAlpha = 0.10f, semantic = VanGlassTokens.ACCENT_AMBER,
                alert = VanGlassTokens.ACCENT_AMBER,
                segments = listOf(VanAuraEnvelopeSegment(200f, 28f)),
            )
            VanDurableState.WARNING -> spec(
                intensity = 0.40f, arc = 0.20f, spark = 0.08f, ground = 0.20f, orb = 0.12f,
                filaments = 3, asymmetry = 0.22f, deform = 0.16f,
                envelopeScale = 1.52f, envelopeAlpha = 0.17f, semantic = VanGlassTokens.ACCENT_AMBER,
                alert = VanGlassTokens.ACCENT_AMBER,
                segments = listOf(
                    VanAuraEnvelopeSegment(-40f, 40f),
                    VanAuraEnvelopeSegment(140f, 38f),
                ),
            )
            VanDurableState.ERROR -> spec(
                intensity = 0.40f, arc = 0.22f, spark = 0.08f, ground = 0.20f, orb = 0.12f,
                filaments = 3, asymmetry = 0.22f, deform = 0.17f,
                envelopeScale = 1.50f, envelopeAlpha = 0.17f, semantic = VanGlassTokens.ACCENT_RED,
                alert = VanGlassTokens.ACCENT_RED,
                segments = listOf(
                    VanAuraEnvelopeSegment(10f, 36f),
                    VanAuraEnvelopeSegment(200f, 28f),
                ),
            )
            VanDurableState.SUCCESS -> spec(
                intensity = 0.35f, arc = 0.18f, spark = 0.10f, ground = 0.22f, orb = 0.14f,
                filaments = 3, asymmetry = 0.18f, deform = 0.14f,
                envelopeScale = 1.48f, envelopeAlpha = 0.16f, semantic = VanGlassTokens.ACCENT_GREEN,
                alert = VanGlassTokens.ACCENT_GREEN,
                segments = listOf(VanAuraEnvelopeSegment(220f, 72f)),
            )
            VanDurableState.URGENT -> spec(
                intensity = 0.34f, arc = 0.12f, spark = 0.06f, ground = 0.16f, orb = 0.08f,
                filaments = 2, asymmetry = 0.18f, deform = 0.14f,
                envelopeScale = 1.45f, envelopeAlpha = 0.18f, semantic = VanGlassTokens.ACCENT_RED,
                alert = VanGlassTokens.ACCENT_RED,
                segments = listOf(
                    VanAuraEnvelopeSegment(-50f, 32f, node = true),
                    VanAuraEnvelopeSegment(40f, 32f, node = true),
                ),
            )
            VanDurableState.OFFLINE -> spec(
                intensity = 0.12f, arc = 0f, spark = 0f, ground = 0.08f, orb = 0f,
                filaments = 0, asymmetry = 0.14f, deform = 0.10f,
                envelopeScale = 1.35f, envelopeAlpha = 0.06f, semantic = null,
                segments = listOf(VanAuraEnvelopeSegment(200f, 22f)),
            )
            VanDurableState.SLEEPING -> spec(
                intensity = 0.12f, arc = 0f, spark = 0f, ground = 0.10f, orb = 0f,
                filaments = 0, asymmetry = 0.12f, deform = 0.08f,
                envelopeScale = 1.36f, envelopeAlpha = 0.07f, semantic = VanGlassTokens.ACCENT_GOLD,
                segments = listOf(VanAuraEnvelopeSegment(240f, 26f)),
            )
        }

        val filaments = if (base.filamentCount <= 0) {
            0
        } else {
            (base.filamentCount * budget.filamentScale).toInt().coerceAtLeast(
                if (budget.filamentScale > 0f) 1 else 0,
            ).coerceAtMost(5)
        }

        return base.copy(
            intensity = (base.intensity * budget.glowScale).coerceAtMost(VanAuraSpec.MAX_INTENSITY),
            arcActivity = base.arcActivity * budget.filamentScale,
            sparkRate = base.sparkRate * budget.filamentScale,
            orbLink = base.orbLink * budget.filamentScale,
            filamentCount = filaments,
            deformation = base.deformation * if (budget.allowMotion) 1f else 0.85f,
            envelopeAlpha = base.envelopeAlpha * if (budget == VanEffectBudget.STATIC) 0.85f else 1f,
        )
    }

    /** Topology-board trade examples — architecture capacity, not a live trading product. */
    fun tradePreview(kind: String): VanAuraSpec {
        val idle = forState(VanDurableState.IDLE)
        return when (kind) {
            "watching" -> idle.copy(
                envelopeRadiusScale = 1.46f,
                envelopeAlpha = 0.14f,
                semanticColor = VanGlassTokens.ACCENT_TEAL,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(200f, 58f)),
            )
            "setup" -> idle.copy(
                envelopeRadiusScale = 1.50f,
                envelopeAlpha = 0.14f,
                semanticColor = VanGlassTokens.ACCENT_VIOLET,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(300f, 50f, node = true)),
            )
            "entry" -> idle.copy(
                envelopeRadiusScale = 1.48f,
                envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_GOLD,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(-25f, 44f, node = true)),
            )
            "in_trade" -> idle.copy(
                envelopeRadiusScale = 1.58f,
                envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_CYAN,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(15f, 46f),
                    VanAuraEnvelopeSegment(200f, 36f),
                ),
            )
            "profit" -> idle.copy(
                envelopeRadiusScale = 1.48f,
                envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_GREEN,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(220f, 64f)),
            )
            "risk" -> idle.copy(
                envelopeRadiusScale = 1.52f,
                envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_AMBER,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(-40f, 34f),
                    VanAuraEnvelopeSegment(150f, 30f),
                ),
            )
            "stop" -> idle.copy(
                envelopeRadiusScale = 1.50f,
                envelopeAlpha = 0.17f,
                semanticColor = VanGlassTokens.ACCENT_RED,
                envelopeSegments = listOf(VanAuraEnvelopeSegment(10f, 36f), VanAuraEnvelopeSegment(200f, 24f)),
            )
            else -> idle.copy(
                envelopeRadiusScale = 1.45f,
                envelopeAlpha = 0.16f,
                semanticColor = VanGlassTokens.ACCENT_RED,
                envelopeSegments = listOf(
                    VanAuraEnvelopeSegment(-50f, 30f, node = true),
                    VanAuraEnvelopeSegment(40f, 30f, node = true),
                ),
            )
        }
    }

    private fun spec(
        intensity: Float,
        arc: Float,
        spark: Float,
        ground: Float,
        orb: Float,
        filaments: Int,
        asymmetry: Float,
        deform: Float,
        envelopeScale: Float,
        envelopeAlpha: Float,
        semantic: Int?,
        segments: List<VanAuraEnvelopeSegment>,
        alert: Int? = null,
    ) = VanAuraSpec(
        intensity = intensity,
        arcActivity = arc,
        sparkRate = spark,
        groundGlow = ground,
        orbLink = orb,
        alertAccent = alert,
        filamentCount = filaments,
        fieldAsymmetry = asymmetry,
        deformation = deform,
        envelopeRadiusScale = envelopeScale.coerceIn(VanAuraSpec.MIN_ENVELOPE_SCALE, VanAuraSpec.MAX_ENVELOPE_SCALE),
        envelopeAlpha = envelopeAlpha,
        semanticColor = semantic,
        envelopeSegments = segments,
    )
}
