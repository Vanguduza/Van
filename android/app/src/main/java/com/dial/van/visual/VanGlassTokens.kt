package com.dial.van.visual

/**
 * DIAL Glass design tokens.
 *
 * Source of truth: `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` §3, §6, §8, §14.
 *
 * The canonical rule from §1 governs every value here: **Van is the solid visual anchor;
 * glass is the contextual interface around him.** Nothing in this file is allowed to make the
 * character translucent — these tokens only describe the shell.
 */
data class VanGlassStyle(
    /** §8 `vanGlass.backgroundAlpha`. */
    val backgroundAlpha: Float,
    /** §8 `vanGlass.blur`, in dp. Ignored when the effect budget forbids live blur. */
    val blurDp: Float,
    /** §8 `vanGlass.borderAlpha`. */
    val borderAlpha: Float,
    /** §8 `vanGlass.borderWidth`, in dp. */
    val borderWidthDp: Float,
    /** §8 `vanGlass.cornerRadius`, in dp. */
    val cornerRadiusDp: Float,
    /** §8 `vanGlass.innerHighlightAlpha` — restrained top-left sheen. */
    val innerHighlightAlpha: Float,
    /** §8 `vanGlass.shadowElevation`, in dp. */
    val elevationDp: Float,
    /** §8 `vanGlass.activeGlowAlpha` — cyan only, and only on interactive edges. */
    val activeGlowAlpha: Float,
    /** Edge accent. Cyan normally; amber/red only for warning and approval (§6). */
    val borderColor: Int,
    /** §6 APPROVAL REQUIRED / §12 contrast: controls must be opaque enough to tap safely. */
    val requiresSolidControls: Boolean,
)

object VanGlassTokens {

    // §8 starting values.
    const val BACKGROUND_ALPHA = 0.62f
    const val BLUR_DP = 24f
    const val BORDER_WIDTH_DP = 1f
    const val BORDER_ALPHA = 0.22f
    const val CORNER_RADIUS_DP = 22f
    const val INNER_HIGHLIGHT_ALPHA = 0.10f
    const val SHADOW_ELEVATION_DP = 8f
    const val ACTIVE_GLOW_ALPHA = 0.28f

    /** §3 base tint: translucent charcoal / deep navy. Never milk-white or frosted-light. */
    const val TINT_NAVY = 0xFF0A0F1E.toInt()

    /** §3 border: cyan-white edge at low opacity. */
    const val EDGE_CYAN = 0xFF9BE9FF.toInt()
    const val ACCENT_CYAN = 0xFF00DAFF.toInt()
    const val ACCENT_AMBER = 0xFFFFB300.toInt()
    const val ACCENT_RED = 0xFFEF4444.toInt()
    const val ACCENT_GREEN = 0xFF22C55E.toInt()

    /** §3 opacity envelope: 55–72%. §14 allows Command Centre panels to sit above it. */
    const val MIN_COMPACT_ALPHA = 0.55f
    const val MAX_COMPACT_ALPHA = 0.72f

    /**
     * Resolves the shell style for a durable state.
     *
     * @param panel true for Command Centre panels, which §14 requires to be more opaque than
     *   the floating compact surface.
     * @param liveBlurAvailable when false, §10's fallback applies: drop the blur but keep the
     *   borders, radii, depth and glow by pre-tinting the surface more heavily.
     * @param noisyBackdrop §12 contrast rule: glass must become more opaque over visually
     *   noisy backgrounds.
     */
    fun forState(
        state: VanDurableState,
        panel: Boolean = false,
        liveBlurAvailable: Boolean = true,
        budget: VanEffectBudget = VanEffectBudget.FULL,
        noisyBackdrop: Boolean = false,
    ): VanGlassStyle {
        var background: Float
        var border = BORDER_ALPHA
        var glow = ACTIVE_GLOW_ALPHA
        var color = EDGE_CYAN
        var solidControls = false

        when (state) {
            // §6 IDLE — glass opacity medium-low, minimal shadow.
            VanDurableState.IDLE,
            VanDurableState.CONNECTING,
            VanDurableState.SLEEPING,
            -> {
                background = MIN_COMPACT_ALPHA
                glow = 0.18f
            }

            // §6 LISTENING — glass edges brighten.
            VanDurableState.LISTENING -> {
                background = BACKGROUND_ALPHA
                border = 0.34f
                glow = 0.34f
            }

            // §6 THINKING — glass remains calm and neutral.
            VanDurableState.THINKING,
            VanDurableState.DELEGATING,
            VanDurableState.SEARCHING,
            -> background = BACKGROUND_ALPHA

            // §6 WORKING — slightly denser glass opacity.
            VanDurableState.WORKING -> {
                background = 0.68f
                glow = 0.32f
            }

            // §6 SUCCESS — glass remains consistent, green as a *secondary* highlight only.
            VanDurableState.SUCCESS -> {
                background = BACKGROUND_ALPHA
                color = ACCENT_GREEN
                border = 0.30f
            }

            // §6 WARNING — border becomes more opaque, warning copy gets contrast.
            VanDurableState.WARNING,
            VanDurableState.ERROR,
            -> {
                background = 0.70f
                border = 0.42f
                color = if (state == VanDurableState.ERROR) ACCENT_RED else ACCENT_AMBER
                solidControls = true
            }

            // §6 APPROVAL REQUIRED — glass becomes more solid, controls opaque, aura restrained.
            VanDurableState.WAITING_FOR_OWNER,
            VanDurableState.URGENT,
            -> {
                background = 0.88f
                border = 0.52f
                glow = 0.20f
                color = if (state == VanDurableState.URGENT) ACCENT_RED else ACCENT_AMBER
                solidControls = true
            }

            VanDurableState.WAITING,
            VanDurableState.ATTENTIVE,
            VanDurableState.SPEAKING,
            -> background = BACKGROUND_ALPHA

            // §6 OFFLINE / DEGRADED — glass loses some cyan edge light, but never looks broken.
            VanDurableState.OFFLINE,
            VanDurableState.DEGRADED,
            -> {
                background = 0.64f
                border = 0.12f
                glow = 0.05f
                color = if (state == VanDurableState.DEGRADED) ACCENT_AMBER else EDGE_CYAN
            }
        }

        // §14 Command Centre panels are more opaque than the compact floating surface.
        if (panel) background += 0.16f
        // §10 no live blur → pre-tinted translucent navy carries the separation instead.
        if (!liveBlurAvailable) background += 0.14f
        // §12 noisy backdrops need more opacity for text legibility.
        if (noisyBackdrop) background += 0.10f

        return VanGlassStyle(
            backgroundAlpha = background.coerceIn(0.40f, 0.97f),
            blurDp = if (budget.allowLiveBlur && liveBlurAvailable) BLUR_DP else 0f,
            borderAlpha = border,
            borderWidthDp = BORDER_WIDTH_DP,
            cornerRadiusDp = CORNER_RADIUS_DP,
            innerHighlightAlpha = if (budget.allowRefraction) INNER_HIGHLIGHT_ALPHA else INNER_HIGHLIGHT_ALPHA * 0.6f,
            elevationDp = if (state == VanDurableState.IDLE) SHADOW_ELEVATION_DP * 0.5f else SHADOW_ELEVATION_DP,
            activeGlowAlpha = glow * budget.glowScale,
            borderColor = color,
            requiresSolidControls = solidControls,
        )
    }
}
