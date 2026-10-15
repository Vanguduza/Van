package com.dial.van.next.chart.scene

/**
 * The engine's output: a flat list of drawing commands in pixel space, with semantic
 * style roles instead of colours. A renderer (Android Canvas today, any other later)
 * replays the list and maps roles to the active theme's tokens, so the engine never knows
 * a colour and dark/light parity is decided in one place (§2.3, §12.6 token-only styling).
 *
 * Because the scene is data, it is tested on the JVM: "the stop line is drawn at 1.0780",
 * "a stale feed shows the stale badge", "a draft never uses the confirmed-protection style".
 */
enum class StyleRole {
    GRID, AXIS_TEXT, CANDLE_UP, CANDLE_DOWN, WICK_UP, WICK_DOWN, VOLUME_UP, VOLUME_DOWN,
    LINE_PRIMARY, AREA_FILL,
    INDICATOR_1, INDICATOR_2, INDICATOR_3, INDICATOR_BAND,
    LAST_PRICE, CROSSHAIR, CROSSHAIR_LABEL,
    DRAWING, DRAWING_SELECTED,
    POSITION_ENTRY, POSITION_STOP_CONFIRMED, POSITION_STOP_UNCONFIRMED, POSITION_TARGET, PENDING_ORDER,
    DRAFT_PROPOSAL,
    QUALITY_BADGE, EVENT_MARKER, REPLAY_CURSOR,
    /** Ruler line and its reading. */
    MEASURE,
    /** Plain-word state notices that are not data quality: loading, layers hidden. */
    NOTICE,
}

sealed interface DrawCmd {
    val role: StyleRole
    data class Line(val x1: Float, val y1: Float, val x2: Float, val y2: Float, override val role: StyleRole, val dashed: Boolean = false) : DrawCmd
    data class Rect(val left: Float, val top: Float, val right: Float, val bottom: Float, override val role: StyleRole, val filled: Boolean = true) : DrawCmd
    /** Polyline with NaN gaps already split out by the builder. */
    data class Polyline(val xs: FloatArray, val ys: FloatArray, override val role: StyleRole) : DrawCmd {
        override fun equals(other: Any?) = other is Polyline && role == other.role && xs.contentEquals(other.xs) && ys.contentEquals(other.ys)
        override fun hashCode() = 31 * xs.contentHashCode() + ys.contentHashCode()
    }
    data class Text(val x: Float, val y: Float, val text: String, override val role: StyleRole, val align: Align = Align.LEFT) : DrawCmd
    /** Clip subsequent commands to a rect until [Unclip]. */
    data class Clip(val left: Float, val top: Float, val right: Float, val bottom: Float) : DrawCmd { override val role get() = StyleRole.GRID }
    data object Unclip : DrawCmd { override val role get() = StyleRole.GRID }
}

enum class Align { LEFT, CENTER, RIGHT }

class DisplayList(val commands: List<DrawCmd>) {
    fun ofRole(role: StyleRole) = commands.filter { it.role == role }
    val size: Int get() = commands.size
}
