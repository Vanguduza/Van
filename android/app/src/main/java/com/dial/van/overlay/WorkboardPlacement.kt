package com.dial.van.overlay

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min

/** Existing workboard only. No application-content inspection or accessibility privilege. */
enum class WorkboardSide { RIGHT, LEFT, BELOW, ABOVE, AVAILABLE_SPACE, MANUAL }

data class WorkboardLayout(val position: OverlayPlacement, val size: OverlaySize, val side: WorkboardSide)

object WorkboardPlacement {
    fun isBoard(presentation: VanOverlayPresentation): Boolean = presentation in setOf(
        VanOverlayPresentation.WORKBOARD_COMPACT, VanOverlayPresentation.WORKBOARD_EXPANDED,
        VanOverlayPresentation.WORKBOARD_MAXIMIZED,
    )

    fun available(screen: OverlayScreen, keyboardTopPx: Int?, marginPx: Int): OverlayScreen {
        val margin = marginPx.coerceAtLeast(0)
            .coerceAtMost(min(screen.safeWidth, screen.safeHeight).coerceAtLeast(0) / 4)
        val left = screen.safeLeft + margin
        val right = max(left + 1, screen.safeRight - margin).coerceAtMost(screen.widthPx.coerceAtLeast(1))
        val top = screen.safeTop + margin
        val imeBottom = keyboardTopPx?.takeIf { it in (screen.safeTop + 1)..screen.safeBottom }
            ?.let { it - margin } ?: (screen.safeBottom - margin)
        val bottom = max(top + 1, min(screen.safeBottom - margin, imeBottom))
            .coerceAtMost(screen.heightPx.coerceAtLeast(1))
        return OverlayScreen(screen.widthPx.coerceAtLeast(1), screen.heightPx.coerceAtLeast(1),
            left.coerceAtMost(right - 1), top.coerceAtMost(bottom - 1), right, bottom)
    }

    /**
     * Prefer an adjacent free rectangle rather than inheriting the avatar's top-left.
     * Above/below and left/right compete by usable area, then distance. If none can
     * fit the minimum readable board, use the bounded remaining viewport and scroll.
     */
    fun plan(
        screen: OverlayScreen,
        anchor: OverlayRect,
        desired: OverlaySize,
        minimum: OverlaySize,
        keyboardTopPx: Int? = null,
        gapPx: Int = 8,
        marginPx: Int = 8,
        preferredManualPosition: OverlayPlacement? = null,
    ): WorkboardLayout {
        val safe = available(screen, keyboardTopPx, marginPx)
        val width = desired.widthPx.coerceIn(1, safe.safeWidth.coerceAtLeast(1))
        val height = desired.heightPx.coerceIn(1, safe.safeHeight.coerceAtLeast(1))
        val minW = minimum.widthPx.coerceIn(1, width)
        val minH = minimum.heightPx.coerceIn(1, height)
        val gap = gapPx.coerceIn(0, min(safe.safeWidth, safe.safeHeight).coerceAtLeast(0) / 3)
        fun finite(v: Double, default: Double) = if (v.isFinite()) v else default
        val ax0 = finite(anchor.left, safe.safeLeft.toDouble()).coerceIn(safe.safeLeft.toDouble(), safe.safeRight.toDouble())
        val ay0 = finite(anchor.top, safe.safeTop.toDouble()).coerceIn(safe.safeTop.toDouble(), safe.safeBottom.toDouble())
        val ax1 = finite(anchor.right, ax0).coerceIn(ax0, safe.safeRight.toDouble())
        val ay1 = finite(anchor.bottom, ay0).coerceIn(ay0, safe.safeBottom.toDouble())
        val cx = (ax0 + ax1) / 2; val cy = (ay0 + ay1) / 2
        if (preferredManualPosition != null) {
            return WorkboardLayout(VanOverlayController.clamp(preferredManualPosition.x,
                preferredManualPosition.y, width, height, safe), OverlaySize(width, height), WorkboardSide.MANUAL)
        }
        data class Region(val side: WorkboardSide, val left: Int, val top: Int, val right: Int, val bottom: Int)
        val regions = listOf(
            Region(WorkboardSide.RIGHT, (ax1 + gap).toInt(), safe.safeTop, safe.safeRight, safe.safeBottom),
            Region(WorkboardSide.LEFT, safe.safeLeft, safe.safeTop, (ax0 - gap).toInt(), safe.safeBottom),
            Region(WorkboardSide.BELOW, safe.safeLeft, (ay1 + gap).toInt(), safe.safeRight, safe.safeBottom),
            Region(WorkboardSide.ABOVE, safe.safeLeft, safe.safeTop, safe.safeRight, (ay0 - gap).toInt()),
        )
        val candidates = regions.mapNotNull { region ->
            val w = min(width, region.right - region.left); val h = min(height, region.bottom - region.top)
            if (w < minW || h < minH) return@mapNotNull null
            val rawX = when (region.side) { WorkboardSide.LEFT -> region.right - w.toDouble()
                WorkboardSide.RIGHT -> region.left.toDouble(); else -> cx - w / 2.0 }
            val rawY = when (region.side) { WorkboardSide.ABOVE -> region.bottom - h.toDouble()
                WorkboardSide.BELOW -> region.top.toDouble(); else -> cy - min(h / 2.0, (ay1 - ay0) / 2.0) }
            val x = rawX.coerceIn(region.left.toDouble(), (region.right - w).toDouble()).toInt()
            val y = rawY.coerceIn(region.top.toDouble(), (region.bottom - h).toDouble()).toInt()
            val area = w.toDouble() * h / (width.toDouble() * height)
            val distance = abs(x + w / 2.0 - cx) + abs(y + h / 2.0 - cy)
            val score = area * 1_000_000.0 - distance
            WorkboardLayout(OverlayPlacement(x, y), OverlaySize(w, h), region.side) to score
        }
        return candidates.maxByOrNull { it.second }?.first ?: WorkboardLayout(
            VanOverlayController.clamp(cx - width / 2.0, cy - height / 2.0, width, height, safe),
            OverlaySize(width, height), WorkboardSide.AVAILABLE_SPACE,
        )
    }
}

/** Preserve the resting avatar position through open/resize/collapse; drag is intentional. */
class WorkboardPlacementSession {
    var anchor: OverlayRect? = null
        private set
    var restingPosition: OverlayPlacement? = null
        private set
    var manualPosition: OverlayPlacement? = null
        private set

    fun opened(position: OverlayPlacement, size: OverlaySize) {
        if (anchor != null) return
        restingPosition = position
        anchor = OverlayRect(position.x.toDouble(), position.y.toDouble(),
            position.x.toDouble() + size.widthPx.coerceAtLeast(1), position.y.toDouble() + size.heightPx.coerceAtLeast(1))
    }
    fun moved(position: OverlayPlacement) { if (anchor != null) manualPosition = position }
    fun close(): OverlayPlacement? {
        val previous = restingPosition
        anchor = null; restingPosition = null; manualPosition = null
        return previous
    }
}
