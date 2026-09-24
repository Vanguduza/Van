package com.dial.van.visual

/**
 * VAN optical-glass tokens.
 *
 * Glass belongs to work surfaces and aura condensation only. VAN's skin, hair, eyes and jacket
 * are never composited with these alpha values. Rev 3 shifts the material from near-black HUD
 * glass toward a readable baby-cyan optical shell while retaining enough absorber over busy apps.
 */
data class VanGlassStyle(
    val backgroundAlpha: Float,
    val blurDp: Float,
    val borderAlpha: Float,
    val borderWidthDp: Float,
    val cornerRadiusDp: Float,
    val innerHighlightAlpha: Float,
    val elevationDp: Float,
    val activeGlowAlpha: Float,
    val borderColor: Int,
    val requiresSolidControls: Boolean,
    val grainAlpha: Float = 0.035f,
    val structuralEdgeAlpha: Float = 0.12f,
    val specularAlpha: Float = 0.28f,
    val contaminationAlpha: Float = 0.16f,
    val cyanTintAlpha: Float = 0.14f,
)

object VanGlassTokens {
    const val BACKGROUND_ALPHA = 0.58f
    const val BLUR_DP = 24f
    const val BORDER_WIDTH_DP = 1f
    const val BORDER_ALPHA = 0.12f
    const val CORNER_RADIUS_DP = 22f
    const val INNER_HIGHLIGHT_ALPHA = 0.13f
    const val SHADOW_ELEVATION_DP = 8f
    const val ACTIVE_GLOW_ALPHA = 0.18f
    const val GRAIN_ALPHA = 0.035f
    const val STRUCTURAL_EDGE_ALPHA = 0.12f
    const val SPECULAR_ALPHA = 0.28f
    const val CONTAMINATION_ALPHA = 0.16f

    const val TINT_NAVY = 0xFF071722.toInt()
    const val TINT_DEEP = 0xFF051018.toInt()
    const val BABY_CYAN = 0xFFBDEFFF.toInt()
    const val ICE_CYAN = 0xFFD9FAFF.toInt()
    const val STRUCTURAL_CYAN = 0xFF62EAF7.toInt()
    const val EDGE_CYAN = 0xFFBDEFFF.toInt()
    const val ACCENT_CYAN = 0xFF00DAFF.toInt()
    const val ACCENT_AMBER = 0xFFFFB300.toInt()
    const val ACCENT_RED = 0xFFEF4444.toInt()
    const val ACCENT_GREEN = 0xFF22C55E.toInt()
    const val ACCENT_VIOLET = 0xFF8B5CF6.toInt()
    const val ACCENT_GOLD = 0xFFEAB308.toInt()
    const val ACCENT_TEAL = 0xFF14B8A6.toInt()
    /** Aura Rev 2 — THINKING's cyan-violet flame. */
    const val ACCENT_THINK = 0xFF7B7CF8.toInt()
    /** Aura Rev 2 — SLEEPING's faint night blue (was gold, which read as a warning). */
    const val ACCENT_SLEEP = 0xFF6E8FD8.toInt()

    const val MIN_COMPACT_ALPHA = 0.54f
    const val MAX_COMPACT_ALPHA = 0.76f

    fun forState(
        state: VanDurableState,
        panel: Boolean = false,
        liveBlurAvailable: Boolean = true,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        noisyBackdrop: Boolean = false,
    ): VanGlassStyle {
        var background = BACKGROUND_ALPHA
        var structural = STRUCTURAL_EDGE_ALPHA
        var specular = SPECULAR_ALPHA
        var glow = ACTIVE_GLOW_ALPHA
        var contamination = CONTAMINATION_ALPHA
        var cyanTint = 0.14f
        var color = STRUCTURAL_CYAN
        var solidControls = false

        when (state) {
            VanDurableState.IDLE,
            VanDurableState.CONNECTING,
            VanDurableState.SLEEPING,
            -> {
                background = MIN_COMPACT_ALPHA
                glow = 0.10f
                contamination = 0.12f
                cyanTint = 0.12f
            }

            VanDurableState.LISTENING -> {
                background = 0.60f
                structural = 0.15f
                specular = 0.34f
                glow = 0.22f
                contamination = 0.22f
                cyanTint = 0.18f
            }

            VanDurableState.THINKING,
            VanDurableState.DELEGATING,
            VanDurableState.SEARCHING,
            -> cyanTint = 0.16f

            VanDurableState.WORKING -> {
                background = 0.64f
                glow = 0.20f
                contamination = 0.22f
                cyanTint = 0.18f
            }

            VanDurableState.SUCCESS -> {
                color = ACCENT_GREEN
                structural = 0.15f
                cyanTint = 0.13f
            }

            VanDurableState.WARNING,
            VanDurableState.ERROR,
            -> {
                background = 0.72f
                structural = 0.20f
                color = if (state == VanDurableState.ERROR) ACCENT_RED else ACCENT_AMBER
                solidControls = true
                cyanTint = 0.10f
            }

            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.URGENT,
            -> {
                background = 0.86f
                structural = 0.24f
                glow = 0.12f
                specular = 0.20f
                color = if (state == VanDurableState.URGENT) ACCENT_RED else ACCENT_AMBER
                solidControls = true
                cyanTint = 0.09f
            }

            VanDurableState.WAITING,
            VanDurableState.ATTENTIVE,
            VanDurableState.SPEAKING,
            -> cyanTint = 0.15f

            VanDurableState.OFFLINE,
            VanDurableState.DEGRADED,
            -> {
                background = 0.66f
                structural = 0.09f
                glow = 0.05f
                specular = 0.12f
                contamination = 0.08f
                cyanTint = 0.08f
                color = if (state == VanDurableState.DEGRADED) ACCENT_AMBER else EDGE_CYAN
            }
        }

        if (panel) background += 0.14f
        if (!liveBlurAvailable) background += 0.18f
        if (noisyBackdrop) background += 0.10f

        val refraction = if (budget.allowRefraction) 1f else 0.55f

        return VanGlassStyle(
            backgroundAlpha = background.coerceIn(0.50f, 0.97f),
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
            cyanTintAlpha = cyanTint * refraction,
        )
    }
}
