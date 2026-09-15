package com.dial.van.overlay

/**
 * Chrome constants for the floating overlay.
 *
 * Shared with the JVM preview renderer so the previews the owner reviews cannot drift from
 * what the service actually draws on device.
 */
object OverlayTheme {
    const val SURFACE_ARGB: Int = 0xE60B1118.toInt()
    const val SURFACE_BORDER_ARGB: Int = 0x5900E5FF
    const val DEGRADED_BORDER_ARGB: Int = 0x66FFB300
    const val OFFLINE_BORDER_ARGB: Int = 0x5978909C

    const val CORNER_DP: Int = 20
    const val COMPACT_AVATAR_DP: Int = 76
    const val EXPANDED_AVATAR_DP: Int = 64
    const val EXPANDED_WIDTH_DP: Int = 248
    const val COMPACT_PADDING_DP: Int = 4
}
