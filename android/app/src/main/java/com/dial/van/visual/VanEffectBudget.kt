package com.dial.van.visual

/**
 * Battery, thermal and reduced-motion fallback ladder.
 *
 * Source of truth: `docs/VAN_VISUAL_PRODUCTION_SYSTEM_REV_2_1_MASTER_BLUEPRINT.md`.
 *
 * Decoration is surrendered in a fixed order: filament frequency, bloom radius, animated
 * refraction, then live blur. Reduced motion is a designed still field, not the STATIC floor.
 * Critical state indicators are never removed, and no state may rely on colour alone.
 */
enum class VanEffectBudget(
    /** Filament / broken-arc energy. */
    val filamentScale: Float,
    /** Outer-field radius. */
    val bloomScale: Float,
    /** Animated refraction across the glass. */
    val allowRefraction: Boolean,
    /** Live backdrop blur. */
    val allowLiveBlur: Boolean,
    /** Motion at all; false holds a designed still pose and still field. */
    val allowMotion: Boolean,
    val glowScale: Float,
) {
    FULL(1.0f, 1.0f, true, true, true, 1.0f),

    /** Mild constraint: fewer filaments, everything else intact. */
    REDUCED(0.55f, 0.85f, true, true, true, 0.9f),

    /**
     * Accessibility still mode: motion stops, but the field, filaments and glass layers remain
     * as a composed still — not an impoverished STATIC leftover.
     */
    REDUCED_MOTION(0.70f, 0.78f, false, true, false, 0.88f),

    /** Heavier constraint: no refraction, tighter field, blur dropped. */
    LOW(0.40f, 0.65f, false, false, true, 0.80f),

    /** Thermal / severe floor — still field and one filament, state still fully readable. */
    STATIC(0.35f, 0.55f, false, false, false, 0.70f),
    ;

    /** Never remove critical state indicators. */
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
        conditions.reducedMotion -> VanEffectBudget.REDUCED_MOTION
        conditions.thermalStatus >= THERMAL_SEVERE -> VanEffectBudget.STATIC
        conditions.batterySaver -> VanEffectBudget.LOW
        conditions.thermalStatus >= THERMAL_MODERATE -> VanEffectBudget.LOW
        conditions.frameBudgetMissed -> VanEffectBudget.LOW
        !conditions.crossWindowBlurEnabled -> VanEffectBudget.REDUCED
        else -> VanEffectBudget.FULL
    }
}
