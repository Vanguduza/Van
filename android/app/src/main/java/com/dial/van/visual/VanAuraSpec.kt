package com.dial.van.visual

/**
 * Living refractive aura specification.
 *
 * Source of truth: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md`.
 *
 * The aura is a deformable field that lives around VAN — core radiance, outer field,
 * filaments, and broken orbital arcs. A full circular ring is forbidden. The field sits
 * between VAN and any glass that later condenses from it, and never covers his face.
 */
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
    /** Secondary accent for warning/approval; null keeps the field purely cyan. */
    val alertAccent: Int?,
    /** Filament count in the 2–5 band (0 when the field is fully quiet). */
    val filamentCount: Int = 0,
    /** Horizontal stretch so the outer field cannot read as a circle. */
    val fieldAsymmetry: Float = 0.18f,
    /** Radial wobble that deforms the outer field away from an ellipse. */
    val deformation: Float = 0.16f,
) {
    /** Hard ceiling: the aura must never obscure facial features or outfit details. */
    val faceSafe: Boolean get() = intensity <= MAX_INTENSITY

    companion object {
        /** Highest working band stays below a wash that would hide the visor. */
        const val MAX_INTENSITY = 0.75f

        /** Each broken orbital arc is a fragment, never a ring. */
        const val MAX_ARC_SWEEP_DEG = 110f

        /** Combined sweep of every visible arc. */
        const val MAX_TOTAL_ARC_DEG = 220f
    }
}

object VanAuraSpecs {

    /**
     * Per-state field envelope.
     *
     * Idle stays quiet; listening and working raise filament and arc energy; offline and
     * sleeping keep a recognisable still field at very low intensity.
     */
    fun forState(state: VanDurableState, budget: VanEffectBudget = VanEffectBudget.FULL): VanAuraSpec {
        val base = when (state) {
            VanDurableState.IDLE,
            VanDurableState.CONNECTING,
            -> VanAuraSpec(
                intensity = 0.25f,
                arcActivity = 0.08f,
                sparkRate = 0.04f,
                groundGlow = 0.18f,
                orbLink = 0.10f,
                alertAccent = null,
                filamentCount = 2,
                fieldAsymmetry = 0.28f,
                deformation = 0.22f,
            )

            VanDurableState.ATTENTIVE -> VanAuraSpec(
                intensity = 0.32f,
                arcActivity = 0.18f,
                sparkRate = 0.08f,
                groundGlow = 0.20f,
                orbLink = 0.16f,
                alertAccent = null,
                filamentCount = 3,
                fieldAsymmetry = 0.22f,
                deformation = 0.16f,
            )

            VanDurableState.LISTENING -> VanAuraSpec(
                intensity = 0.52f,
                arcActivity = 0.50f,
                sparkRate = 0.18f,
                groundGlow = 0.28f,
                orbLink = 0.50f,
                alertAccent = null,
                filamentCount = 4,
                fieldAsymmetry = 0.24f,
                deformation = 0.20f,
            )

            VanDurableState.THINKING,
            VanDurableState.SEARCHING,
            VanDurableState.DELEGATING,
            -> VanAuraSpec(
                intensity = 0.42f,
                arcActivity = 0.28f,
                sparkRate = 0.12f,
                groundGlow = 0.20f,
                orbLink = 0.22f,
                alertAccent = null,
                filamentCount = 3,
                fieldAsymmetry = 0.18f,
                deformation = 0.18f,
            )

            VanDurableState.WORKING -> VanAuraSpec(
                intensity = 0.68f,
                arcActivity = 0.70f,
                sparkRate = 0.30f,
                groundGlow = 0.30f,
                orbLink = 0.60f,
                alertAccent = null,
                filamentCount = 5,
                fieldAsymmetry = 0.26f,
                deformation = 0.22f,
            )

            VanDurableState.SPEAKING -> VanAuraSpec(
                intensity = 0.45f,
                arcActivity = 0.30f,
                sparkRate = 0.10f,
                groundGlow = 0.24f,
                orbLink = 0.28f,
                alertAccent = null,
                filamentCount = 3,
                fieldAsymmetry = 0.20f,
                deformation = 0.16f,
            )

            VanDurableState.SUCCESS -> VanAuraSpec(
                intensity = 0.35f,
                arcActivity = 0.18f,
                sparkRate = 0.10f,
                groundGlow = 0.22f,
                orbLink = 0.14f,
                alertAccent = VanGlassTokens.ACCENT_GREEN,
                filamentCount = 3,
                fieldAsymmetry = 0.18f,
                deformation = 0.14f,
            )

            VanDurableState.WARNING -> VanAuraSpec(
                intensity = 0.40f,
                arcActivity = 0.20f,
                sparkRate = 0.08f,
                groundGlow = 0.20f,
                orbLink = 0.12f,
                alertAccent = VanGlassTokens.ACCENT_AMBER,
                filamentCount = 3,
                fieldAsymmetry = 0.22f,
                deformation = 0.16f,
            )

            VanDurableState.ERROR -> VanAuraSpec(
                intensity = 0.40f,
                arcActivity = 0.22f,
                sparkRate = 0.08f,
                groundGlow = 0.20f,
                orbLink = 0.12f,
                alertAccent = VanGlassTokens.ACCENT_RED,
                filamentCount = 3,
                fieldAsymmetry = 0.22f,
                deformation = 0.17f,
            )

            VanDurableState.WAITING_FOR_OWNER -> VanAuraSpec(
                intensity = 0.30f,
                arcActivity = 0.08f,
                sparkRate = 0.04f,
                groundGlow = 0.16f,
                orbLink = 0.08f,
                alertAccent = VanGlassTokens.ACCENT_AMBER,
                filamentCount = 2,
                fieldAsymmetry = 0.16f,
                deformation = 0.12f,
            )

            VanDurableState.URGENT -> VanAuraSpec(
                intensity = 0.34f,
                arcActivity = 0.12f,
                sparkRate = 0.06f,
                groundGlow = 0.16f,
                orbLink = 0.08f,
                alertAccent = VanGlassTokens.ACCENT_RED,
                filamentCount = 2,
                fieldAsymmetry = 0.18f,
                deformation = 0.14f,
            )

            VanDurableState.WAITING -> VanAuraSpec(
                intensity = 0.28f,
                arcActivity = 0.12f,
                sparkRate = 0.05f,
                groundGlow = 0.18f,
                orbLink = 0.10f,
                alertAccent = null,
                filamentCount = 2,
                fieldAsymmetry = 0.18f,
                deformation = 0.14f,
            )

            VanDurableState.OFFLINE,
            VanDurableState.SLEEPING,
            -> VanAuraSpec(
                intensity = 0.12f,
                arcActivity = 0f,
                sparkRate = 0f,
                groundGlow = 0.08f,
                orbLink = 0f,
                alertAccent = null,
                filamentCount = 0,
                fieldAsymmetry = 0.14f,
                deformation = 0.10f,
            )

            VanDurableState.DEGRADED -> VanAuraSpec(
                intensity = 0.16f,
                arcActivity = 0.04f,
                sparkRate = 0f,
                groundGlow = 0.10f,
                orbLink = 0f,
                alertAccent = VanGlassTokens.ACCENT_AMBER,
                filamentCount = 2,
                fieldAsymmetry = 0.16f,
                deformation = 0.12f,
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
        )
    }
}
