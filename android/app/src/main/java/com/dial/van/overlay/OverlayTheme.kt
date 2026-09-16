package com.dial.van.overlay

/**
 * Chrome constants for the floating overlay.
 *
 * Shared with the JVM preview renderer so the previews the owner reviews cannot drift from
 * what the service actually draws on device. Geometry follows Rev 2.1 §11.
 */
object OverlayTheme {
    const val SURFACE_ARGB: Int = 0xE60B1118.toInt()
    const val SURFACE_BORDER_ARGB: Int = 0x5900E5FF
    const val DEGRADED_BORDER_ARGB: Int = 0x66FFB300
    const val OFFLINE_BORDER_ARGB: Int = 0x5978909C

    const val CORNER_DP: Int = 20
    const val COMPACT_AVATAR_DP: Int = 76
    const val EXPANDED_AVATAR_DP: Int = 64
    const val COMPACT_PADDING_DP: Int = 4

    /**
     * Resting hit target and character visual height.
     * Hit must clear Zone C at 1.70× mid radius around a 92dp body (~168dp).
     */
    const val RESTING_HIT_DP: Int = 168
    const val RESTING_AVATAR_DP: Int = 92

    /** Compact actions panel (§11.3). */
    const val COMPACT_WIDTH_DP: Int = 280
    const val COMPACT_CAPSULE_HEIGHT_DP: Int = 108
    const val EXPANDED_WIDTH_DP: Int = 320
    const val EXPANDED_HEIGHT_DP: Int = 148

    /** Docked hit target. Character visual height; face stays on-screen (§11.2). */
    const val DOCK_HIT_DP: Int = 88
    const val DOCK_CHARACTER_DP: Int = 76
    const val DOCK_WIDTH_DP: Int = 64

    /** When glass condenses, VAN overlaps the panel by this much. */
    const val VAN_GLASS_OVERLAP_DP: Int = 20

    val COMPACT_ACTIONS: List<String> = listOf("Ask", "Projects", "Tasks", "Decisions")
}
