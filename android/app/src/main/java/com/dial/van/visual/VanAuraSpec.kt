package com.dial.van.visual

/**
 * Blue electrical aura specification.
 *
 * Source of truth: `docs/VAN_GLASSMORPHIC_FLOATING_ASSISTANT_DESIGN.md` §2 and §7.
 *
 * §2 places the aura *between* Van and the glass shell, and forbids it from obscuring his
 * face or outfit. §7 sets the layer stack and the per-state intensity envelope reproduced in
 * [forState]. The aura reads as intelligent energy, never a superhero lightning effect.
 */
data class VanAuraSpec(
    /** §7 aura intensity, 0..1. */
    val intensity: Float,
    /** §7 arc activity, 0..1 — drives filament count and lifetime. */
    val arcActivity: Float,
    /** §7 layer 4 — micro-spark frequency, 0..1. */
    val sparkRate: Float,
    /** §7 layer 5 — soft elliptical cyan illumination under the body. */
    val groundGlow: Float,
    /** §7 layer 6 — occasional energy bridge between Van and his orb. */
    val orbLink: Float,
    /** §6 secondary accent for warning/approval; null keeps the aura purely cyan. */
    val alertAccent: Int?,
) {
    /** §2 hard ceiling: the aura must never obscure facial features or outfit details. */
    val faceSafe: Boolean get() = intensity <= MAX_INTENSITY

    companion object {
        /** §7's highest band is Working at 60–75%. */
        const val MAX_INTENSITY = 0.75f
    }
}

object VanAuraSpecs {

    /**
     * §7 state intensity guidance, implemented as the midpoint of each documented band:
     *
     * | State | Aura intensity | Arc activity |
     * |---|---:|---:|
     * | Idle | 20–30% | Minimal |
     * | Listening | 45–60% | Moderate |
     * | Thinking | 35–50% | Low / concentrated |
     * | Working | 60–75% | Moderate-high |
     * | Success | 35% | Brief |
     * | Warning | 40% + alert accent | Low |
     * | Approval | 30% | Minimal |
     * | Offline | 10–15% | None |
     */
    fun forState(state: VanDurableState, budget: VanEffectBudget = VanEffectBudget.FULL): VanAuraSpec {
        val base = when (state) {
            VanDurableState.IDLE,
            VanDurableState.ATTENTIVE,
            VanDurableState.CONNECTING,
            -> VanAuraSpec(0.25f, 0.05f, 0.05f, 0.20f, 0.10f, null)

            VanDurableState.LISTENING -> VanAuraSpec(0.52f, 0.50f, 0.18f, 0.30f, 0.55f, null)

            VanDurableState.THINKING,
            VanDurableState.SEARCHING,
            VanDurableState.DELEGATING,
            -> VanAuraSpec(0.42f, 0.20f, 0.12f, 0.22f, 0.25f, null)

            VanDurableState.WORKING -> VanAuraSpec(0.68f, 0.70f, 0.30f, 0.34f, 0.65f, null)

            VanDurableState.SPEAKING -> VanAuraSpec(0.45f, 0.25f, 0.10f, 0.26f, 0.30f, null)

            // §6 SUCCESS — cyan returns toward baseline, green is a brief secondary highlight.
            VanDurableState.SUCCESS ->
                VanAuraSpec(0.35f, 0.15f, 0.10f, 0.24f, 0.15f, VanGlassTokens.ACCENT_GREEN)

            // §6 WARNING — partial amber/red accenting, Van's identity stays cyan.
            VanDurableState.WARNING ->
                VanAuraSpec(0.40f, 0.15f, 0.08f, 0.22f, 0.12f, VanGlassTokens.ACCENT_AMBER)

            VanDurableState.ERROR ->
                VanAuraSpec(0.40f, 0.15f, 0.08f, 0.22f, 0.12f, VanGlassTokens.ACCENT_RED)

            // §6 APPROVAL REQUIRED — aura restrained so the controls stay dominant.
            VanDurableState.WAITING_FOR_OWNER ->
                VanAuraSpec(0.30f, 0.05f, 0.04f, 0.18f, 0.08f, VanGlassTokens.ACCENT_AMBER)

            VanDurableState.URGENT ->
                VanAuraSpec(0.30f, 0.05f, 0.04f, 0.18f, 0.08f, VanGlassTokens.ACCENT_RED)

            VanDurableState.WAITING -> VanAuraSpec(0.28f, 0.08f, 0.05f, 0.20f, 0.10f, null)

            // §6 OFFLINE / DEGRADED — aura dims, orb dims, but Van stays recognisable.
            VanDurableState.OFFLINE,
            VanDurableState.SLEEPING,
            -> VanAuraSpec(0.12f, 0f, 0f, 0.08f, 0f, null)

            VanDurableState.DEGRADED ->
                VanAuraSpec(0.15f, 0f, 0f, 0.10f, 0f, VanGlassTokens.ACCENT_AMBER)
        }

        // §11 fallback ladder trims decoration without touching intensity's state meaning.
        return base.copy(
            intensity = (base.intensity * budget.glowScale).coerceAtMost(VanAuraSpec.MAX_INTENSITY),
            arcActivity = base.arcActivity * budget.filamentScale,
            sparkRate = base.sparkRate * budget.filamentScale,
            orbLink = base.orbLink * budget.filamentScale,
        )
    }
}
