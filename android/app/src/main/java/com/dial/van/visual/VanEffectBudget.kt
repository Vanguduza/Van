package com.dial.van.visual

/**
 * Battery, thermal and reduced-motion fallback ladder.
 *
 * Source of truth: `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` §10–§12.
 *
 * §11 fixes the order in which decoration is surrendered: filament frequency, then bloom
 * radius, then animated refraction, then live blur, keeping a static cyan rim glow — and
 * critical state indicators are never removed. §16 adds the hard rule that no state may rely
 * on colour alone, so nothing in this ladder is allowed to drop a state's shape or copy.
 */
enum class VanEffectBudget(
    /** §11 step 1 — filament frequency. */
    val filamentScale: Float,
    /** §11 step 2 — bloom radius. */
    val bloomScale: Float,
    /** §11 step 3 — animated refraction across the glass. */
    val allowRefraction: Boolean,
    /** §11 step 4 — live backdrop blur. */
    val allowLiveBlur: Boolean,
    /** §12 — motion at all; false keeps a static glow. */
    val allowMotion: Boolean,
    val glowScale: Float,
) {
    FULL(1.0f, 1.0f, true, true, true, 1.0f),

    /** Mild constraint: fewer filaments, everything else intact. */
    REDUCED(0.45f, 0.85f, true, true, true, 0.9f),

    /** Heavier constraint: no refraction, tighter bloom, blur dropped. */
    LOW(0.15f, 0.6f, false, false, true, 0.75f),

    /** §11 floor — static cyan rim glow only, state indicators still fully present. */
    STATIC(0f, 0.5f, false, false, false, 0.65f),
    ;

    /** §11: "Never remove critical state indicators." */
    val keepsStateIndicators: Boolean get() = true
}

/** Device signals that drive the ladder, kept separate so the policy stays unit-testable. */
data class VanEffectConditions(
    /** `PowerManager.isPowerSaveMode`. */
    val batterySaver: Boolean = false,
    /** `PowerManager.getCurrentThermalStatus()`; 0 = none. */
    val thermalStatus: Int = 0,
    /** System animator duration scale is zero, or an accessibility reduced-motion setting. */
    val reducedMotion: Boolean = false,
    /** `WindowManager.isCrossWindowBlurEnabled()`. */
    val crossWindowBlurEnabled: Boolean = true,
    /** Sustained frame budget miss reported by the overlay. */
    val frameBudgetMissed: Boolean = false,
)

object VanEffectPolicy {

    /** `PowerManager.THERMAL_STATUS_SEVERE`. */
    const val THERMAL_SEVERE = 3

    /** `PowerManager.THERMAL_STATUS_MODERATE`. */
    const val THERMAL_MODERATE = 2

    fun resolve(conditions: VanEffectConditions): VanEffectBudget = when {
        // §12 reduced motion is the strongest signal: motion stops entirely.
        conditions.reducedMotion -> VanEffectBudget.STATIC
        conditions.thermalStatus >= THERMAL_SEVERE -> VanEffectBudget.STATIC
        conditions.batterySaver -> VanEffectBudget.LOW
        conditions.thermalStatus >= THERMAL_MODERATE -> VanEffectBudget.LOW
        conditions.frameBudgetMissed -> VanEffectBudget.LOW
        !conditions.crossWindowBlurEnabled -> VanEffectBudget.REDUCED
        else -> VanEffectBudget.FULL
    }
}
