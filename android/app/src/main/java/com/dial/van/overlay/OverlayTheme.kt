package com.dial.van.overlay

/** Shared geometry/touch constants for the Rev 3 floating assistant. */
object OverlayTheme {
    const val SURFACE_ARGB: Int = 0xE6071722.toInt()
    const val SURFACE_BORDER_ARGB: Int = 0x7062EAF7
    const val DEGRADED_BORDER_ARGB: Int = 0x66FFB300
    const val OFFLINE_BORDER_ARGB: Int = 0x5978909C

    const val CORNER_DP: Int = 22

    /** Full floating VAN and living field. */
    const val RESTING_HIT_DP: Int = 184
    const val RESTING_AVATAR_DP: Int = 96

    /** Workboard sizing. Height is bounded by presentation, content remains scrollable. */
    const val COMPACT_WIDTH_DP: Int = 300
    const val COMPACT_HEIGHT_DP: Int = 188
    const val EXPANDED_WIDTH_DP: Int = 356
    const val EXPANDED_HEIGHT_DP: Int = 420
    const val MAXIMIZED_HORIZONTAL_MARGIN_DP: Int = 12
    const val MAXIMIZED_HEIGHT_FRACTION: Float = 0.86f

    /** Circular minimized portrait: face is the representation, not a generic dot. */
    const val MINIMIZED_VISUAL_DP: Int = 62
    const val MINIMIZED_TOUCH_DP: Int = 72

    /** Intentional edge dock remains distinct from minimize. */
    const val DOCK_HIT_DP: Int = 88
    const val DOCK_CHARACTER_DP: Int = 76
    const val DOCK_WIDTH_DP: Int = 68

    const val VAN_GLASS_OVERLAP_DP: Int = 20

    /** Bottom-centre native-style dismiss target used only while dragging. */
    const val DISMISS_VISUAL_DP: Int = 72
    const val DISMISS_HIT_DP: Int = 112
    const val DISMISS_BOTTOM_MARGIN_DP: Int = 24

    val COMPACT_ACTIONS: List<String> = listOf("Chat", "Voice", "Projects", "Tasks", "Decisions")
    val QUICK_CONTROLS: List<String> = listOf("Chat", "Voice", "Minimize", "Command Centre", "Dock", "Close")
}
