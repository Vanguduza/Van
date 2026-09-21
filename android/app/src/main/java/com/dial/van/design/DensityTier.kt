package com.dial.van.design

/**
 * VAN's three layout density tiers (DNA §2, §5).
 *
 * "Layouts recompose, not scale": a screen at [Wide] is not [Regular] with bigger numbers,
 * it is a different arrangement (two-pane, more columns of breathing room). This file only
 * decides *which* tier applies; the recomposition itself lives in each screen.
 *
 * Pure Kotlin so the width→tier decision is testable without an emulator or a `Configuration`
 * object — the failure mode this guards is a tablet or a folded-open device silently getting
 * the phone layout because nothing ever asked what width it actually had.
 */
enum class VanDensity {
    /** The floating overlay's expanded card (DNA §1: "low" density, spatial, compact). */
    Compact,

    /** Phone portrait — the default for every full-screen destination. */
    Regular,

    /** Landscape or ≥600dp: two-pane layouts, not a stretched single pane. */
    Wide,
    ;

    companion object {
        /** The breakpoint DNA §5 names for the two-pane cutover. */
        const val WIDE_BREAKPOINT_DP = 600

        /**
         * Choose a tier from the space actually available.
         *
         * The overlay always resolves to [Compact] regardless of [widthDp]: DNA §1 pins the
         * floating VAN surface to "low" density by grammar, not by measurement, so an
         * expanded overlay card on a wide device does not suddenly become a two-pane layout
         * mid-conversation.
         */
        fun from(widthDp: Int, isOverlay: Boolean): VanDensity = when {
            isOverlay -> Compact
            widthDp >= WIDE_BREAKPOINT_DP -> Wide
            else -> Regular
        }
    }
}
