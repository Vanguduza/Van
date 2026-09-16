package com.dial.van.visual

/**
 * DIAL Glass design tokens — optical glass, not a stroked card.
 *
 * Source of truth: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md`.
 *
 * VAN is the solid visual anchor. Glass condenses from the aura when interface space is
 * needed. These tokens describe that condensed field only — never the character.
 */
data class VanGlassStyle(
    /** Absorptive tint alpha. */
    val backgroundAlpha: Float,
    /** Live backdrop blur, in dp. Ignored when the effect budget forbids live blur. */
    val blurDp: Float,
    /** Structural edge alpha — faint, never a glowing perimeter. */
    val borderAlpha: Float,
    /** Structural edge width, in dp. */
    val borderWidthDp: Float,
    /** Corner radius, in dp. */
    val cornerRadiusDp: Float,
    /** Restrained top-left inner highlight. */
    val innerHighlightAlpha: Float,
    /** Spatial shadow elevation, in dp. */
    val elevationDp: Float,
    /** Selective specular energy on the lit edge only. */
    val activeGlowAlpha: Float,
    /** Edge accent. Cyan normally; amber/red only for warning and approval. */
    val borderColor: Int,
    /** Approval / warning: controls must be opaque enough to tap safely. */
    val requiresSolidControls: Boolean,
    /** Fine optical grain. */
    val grainAlpha: Float = 0.045f,
    /** Hard structural edge, distinct from specular. */
    val structuralEdgeAlpha: Float = 0.10f,
    /** Specular highlight confined to the top-left fragment. */
    val specularAlpha: Float = 0.26f,
    /** Aura light contaminating the character-facing side of the glass. */
    val contaminationAlpha: Float = 0.14f,
)

object VanGlassTokens {

    const val BACKGROUND_ALPHA = 0.58f
    const val BLUR_DP = 24f
    const val BORDER_WIDTH_DP = 1f
    const val BORDER_ALPHA = 0.10f
    const val CORNER_RADIUS_DP = 22f
    const val INNER_HIGHLIGHT_ALPHA = 0.11f
    const val SHADOW_ELEVATION_DP = 8f
    const val ACTIVE_GLOW_ALPHA = 0.18f
    const val GRAIN_ALPHA = 0.045f
    const val STRUCTURAL_EDGE_ALPHA = 0.10f
    const val SPECULAR_ALPHA = 0.26f
    const val CONTAMINATION_ALPHA = 0.14f

    /** Base tint: translucent charcoal / deep navy. Never milk-white. */
    const val TINT_NAVY = 0xFF0A0F1E.toInt()

    const val EDGE_CYAN = 0xFF9BE9FF.toInt()
    const val ACCENT_CYAN = 0xFF00DAFF.toInt()
    const val ACCENT_AMBER = 0xFFFFB300.toInt()
    const val ACCENT_RED = 0xFFEF4444.toInt()
    const val ACCENT_GREEN = 0xFF22C55E.toInt()
    const val ACCENT_VIOLET = 0xFF8B5CF6.toInt()
    const val ACCENT_GOLD = 0xFFEAB308.toInt()
    const val ACCENT_TEAL = 0xFF14B8A6.toInt()

    const val MIN_COMPACT_ALPHA = 0.50f
    const val MAX_COMPACT_ALPHA = 0.72f

    /**
     * Resolves the condensed-glass style for a durable state.
     *
     * @param panel true for Command Centre panels, which sit more opaque than overlay glass.
     * @param liveBlurAvailable when false, drop blur but keep shaping, grain, depth and specular.
     * @param noisyBackdrop glass becomes more opaque over visually noisy backgrounds.
     */
    fun forState(
        state: VanDurableState,
        panel: Boolean = false,
        liveBlurAvailable: Boolean = true,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        noisyBackdrop: Boolean = false,
    ): VanGlassStyle {
        var background: Float
        var structural = STRUCTURAL_EDGE_ALPHA
        var specular = SPECULAR_ALPHA
        var glow = ACTIVE_GLOW_ALPHA
        var contamination = CONTAMINATION_ALPHA
        var color = EDGE_CYAN
        var solidControls = false

        when (state) {
            VanDurableState.IDLE,
            VanDurableState.CONNECTING,
            VanDurableState.SLEEPING,
            -> {
                background = MIN_COMPACT_ALPHA
                glow = 0.12f
                contamination = 0.10f
            }

            VanDurableState.LISTENING -> {
                background = BACKGROUND_ALPHA
                structural = 0.14f
                specular = 0.34f
                glow = 0.22f
                contamination = 0.22f
            }

            VanDurableState.THINKING,
            VanDurableState.DELEGATING,
            VanDurableState.SEARCHING,
            -> background = BACKGROUND_ALPHA

            VanDurableState.WORKING -> {
                background = 0.64f
                glow = 0.20f
                contamination = 0.20f
            }

            VanDurableState.SUCCESS -> {
                background = BACKGROUND_ALPHA
                color = ACCENT_GREEN
                structural = 0.14f
            }

            VanDurableState.WARNING,
            VanDurableState.ERROR,
            -> {
                background = 0.70f
                structural = 0.18f
                color = if (state == VanDurableState.ERROR) ACCENT_RED else ACCENT_AMBER
                solidControls = true
            }

            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.URGENT,
            -> {
                background = 0.88f
                structural = 0.22f
                glow = 0.12f
                specular = 0.18f
                color = if (state == VanDurableState.URGENT) ACCENT_RED else ACCENT_AMBER
                solidControls = true
            }

            VanDurableState.WAITING,
            VanDurableState.ATTENTIVE,
            VanDurableState.SPEAKING,
            -> background = BACKGROUND_ALPHA

            VanDurableState.OFFLINE,
            VanDurableState.DEGRADED,
            -> {
                background = 0.62f
                structural = 0.07f
                glow = 0.04f
                specular = 0.10f
                contamination = 0.06f
                color = if (state == VanDurableState.DEGRADED) ACCENT_AMBER else EDGE_CYAN
            }
        }

        if (panel) background += 0.16f
        if (!liveBlurAvailable) background += 0.12f
        if (noisyBackdrop) background += 0.10f

        val refraction = if (budget.allowRefraction) 1f else 0.55f

        return VanGlassStyle(
            backgroundAlpha = background.coerceIn(0.40f, 0.97f),
            blurDp = if (budget.allowLiveBlur && liveBlurAvailable) BLUR_DP else 0f,
            borderAlpha = structural,
            borderWidthDp = BORDER_WIDTH_DP,
            cornerRadiusDp = CORNER_RADIUS_DP,
            innerHighlightAlpha = INNER_HIGHLIGHT_ALPHA * refraction,
            elevationDp = if (state == VanDurableState.IDLE) SHADOW_ELEVATION_DP * 0.5f else SHADOW_ELEVATION_DP,
            activeGlowAlpha = glow * budget.glowScale,
            borderColor = color,
            requiresSolidControls = solidControls,
            grainAlpha = GRAIN_ALPHA * if (budget.allowRefraction) 1f else 0.45f,
            structuralEdgeAlpha = structural,
            specularAlpha = specular * refraction * budget.glowScale,
            contaminationAlpha = contamination * budget.glowScale,
        )
    }
}
