package com.dial.van.overlay

/** Equivalent to a bounded drag, without a fling or a dismiss-target side effect. */
enum class OverlayMoveDirection { LEFT, RIGHT, UP, DOWN }

object OverlayAccessibleMovement {
    fun target(position: OverlayPlacement, size: OverlaySize, screen: OverlayScreen,
               direction: OverlayMoveDirection, stepPx: Int, keyboardTopPx: Int?): OverlayPlacement =
        target(position, size, screen,
            when (direction) { OverlayMoveDirection.LEFT -> -1; OverlayMoveDirection.RIGHT -> 1; else -> 0 },
            when (direction) { OverlayMoveDirection.UP -> -1; OverlayMoveDirection.DOWN -> 1; else -> 0 },
            stepPx, keyboardTopPx)

    fun target(position: OverlayPlacement, size: OverlaySize, screen: OverlayScreen,
               dx: Int, dy: Int, stepPx: Int, keyboardTopPx: Int?): OverlayPlacement {
        require(dx in -1..1 && dy in -1..1 && (dx == 0 || dy == 0))
        val step = stepPx.coerceIn(1, maxOf(1, screen.widthPx, screen.heightPx)).toDouble()
        val safe = if (keyboardTopPx != null) screen.copy(bottomPx = minOf(screen.safeBottom,
            keyboardTopPx.coerceAtLeast(screen.safeTop))) else screen
        return VanOverlayController.clamp(position.x.toDouble() + dx * step,
            position.y.toDouble() + dy * step, size.widthPx, size.heightPx, safe)
    }
}
