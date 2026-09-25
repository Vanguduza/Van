package com.dial.van.overlay

/**
 * Where a workboard opens: beside VAN, never around him.
 *
 * Owner direction (2026-09-25): the workboard used to be a glass panel with VAN drawn inside
 * its left edge, and VAN's 184 dp drag-and-tap box lay over the panel's first column of
 * chips, so "Chat", "Voice" and "Projects" went to VAN instead of doing anything. The window
 * also kept VAN's x when it widened, so near the right edge most of the board, and all of a
 * maximized one, was off screen.
 *
 * Now VAN stays where he is and the board opens on the side facing the middle of the screen:
 * VAN on the right half, the board on his left; VAN on the left half, the board on his right.
 * It may tuck into the empty part of VAN's square box but never over his body. When that
 * side cannot hold the narrowest useful board, VAN is nudged inward rather than the board
 * being squeezed or pushed off screen. The window is the union of the two, so the service
 * moves it and tells the surface where each sits inside it.
 *
 * Pure, so it is executed in `android/verification`.
 */
enum class WorkboardSide { LEFT, RIGHT }

/** A rectangle in pixels, relative to the overlay window. */
data class OverlayRect(val x: Int, val y: Int, val width: Int, val height: Int) {
    val right: Int get() = x + width
    val bottom: Int get() = y + height
}

data class WorkboardLayout(
    val windowX: Int,
    val windowY: Int,
    val windowWidth: Int,
    val windowHeight: Int,
    /** VAN's square box inside the window. */
    val van: OverlayRect,
    /** The board inside the window; null when none is open. */
    val board: OverlayRect?,
    val side: WorkboardSide,
) {
    /** Where VAN's box is on screen, which is what the overlay remembers and drags. */
    val vanScreenX: Int get() = windowX + van.x
    val vanScreenY: Int get() = windowY + van.y
}

/** How big a board wants to be, and the narrowest it is still useful at. */
data class BoardSize(val width: Int, val height: Int, val minWidth: Int)

/** VAN's square box and how wide his body is inside it. */
data class VanBody(val box: Int, val bodyWidth: Int)

object WorkboardPlacement {

    /**
     * The whole window for [presentation], with VAN's box at ([vanX], [vanY]) on screen.
     *
     * Every board is sized here, in one place: the compact and expanded boards at their
     * design size, the maximized one as large as the screen allows beside VAN, and the quick
     * controls like a small board. Minimized and docked VAN are their own windows, so for
     * them this is VAN alone.
     */
    fun forPresentation(
        presentation: VanOverlayPresentation,
        quickControlsVisible: Boolean,
        vanX: Int,
        vanY: Int,
        screen: OverlayScreen,
        dp: (Int) -> Int,
    ): WorkboardLayout {
        val box = dp(OverlayTheme.RESTING_HIT_DP)
        val minW = dp(OverlayTheme.WORKBOARD_MIN_WIDTH_DP)
        val size = when (presentation) {
            VanOverlayPresentation.WORKBOARD_COMPACT ->
                BoardSize(dp(OverlayTheme.COMPACT_WIDTH_DP), dp(OverlayTheme.COMPACT_HEIGHT_DP), minW)
            VanOverlayPresentation.WORKBOARD_EXPANDED ->
                BoardSize(dp(OverlayTheme.EXPANDED_WIDTH_DP), dp(OverlayTheme.EXPANDED_HEIGHT_DP), minW)
            VanOverlayPresentation.WORKBOARD_MAXIMIZED -> BoardSize(
                screen.widthPx,
                (screen.heightPx * OverlayTheme.MAXIMIZED_HEIGHT_FRACTION).toInt(),
                minW,
            )
            VanOverlayPresentation.FULL_FLOATING -> if (quickControlsVisible) {
                val w = dp(OverlayTheme.QUICK_CONTROLS_WIDTH_DP)
                val h = dp(OverlayTheme.QUICK_CONTROLS_HEIGHT_DP)
                BoardSize(w, h, w)
            } else {
                null
            }
            VanOverlayPresentation.MINIMIZED, VanOverlayPresentation.DOCKED -> null
        } ?: return resting(vanX, vanY, box)
        return beside(
            screen = screen,
            vanX = vanX,
            vanY = vanY,
            van = VanBody(box, dp(OverlayTheme.FLOATING_BODY_WIDTH_DP)),
            size = size,
            gap = dp(OverlayTheme.WORKBOARD_GAP_DP),
            margin = dp(OverlayTheme.WORKBOARD_MARGIN_DP),
        )
    }

    /** VAN alone: the window is his box. */
    fun resting(vanX: Int, vanY: Int, vanBox: Int): WorkboardLayout = WorkboardLayout(
        windowX = vanX,
        windowY = vanY,
        windowWidth = vanBox,
        windowHeight = vanBox,
        van = OverlayRect(0, 0, vanBox, vanBox),
        board = null,
        side = WorkboardSide.RIGHT,
    )

    /**
     * A board of up to [size] beside VAN's box at ([vanX], [vanY]), on the side facing the
     * middle of the screen. The board keeps [gap] clear of VAN's body and [margin] clear of
     * the screen edge, and is centred on VAN vertically as far as the screen allows.
     */
    fun beside(
        screen: OverlayScreen,
        vanX: Int,
        vanY: Int,
        van: VanBody,
        size: BoardSize,
        gap: Int,
        margin: Int,
    ): WorkboardLayout {
        val box = van.box
        var vx = vanX.coerceIn(0, (screen.widthPx - box).coerceAtLeast(0))
        val vy = vanY.coerceIn(0, (screen.heightPx - box).coerceAtLeast(0))
        val tuck = ((box - van.bodyWidth) / 2 - gap).coerceAtLeast(0)
        val side = if (vx + box / 2 > screen.widthPx / 2) WorkboardSide.LEFT else WorkboardSide.RIGHT

        fun room(x: Int) = when (side) {
            WorkboardSide.RIGHT -> screen.widthPx - margin - (x + box - tuck)
            WorkboardSide.LEFT -> x + tuck - margin
        }
        val widest = (screen.widthPx - 2 * margin).coerceAtLeast(1)
        val want = minOf(size.width, maxOf(room(vx), minOf(size.minWidth, size.width)), widest)
        if (room(vx) < want) {
            // Too close to the middle for even the narrowest board: VAN steps back toward
            // his own edge until it fits.
            vx = when (side) {
                WorkboardSide.RIGHT -> (screen.widthPx - margin - want - box + tuck).coerceAtLeast(0)
                WorkboardSide.LEFT -> (margin + want - tuck).coerceAtMost((screen.widthPx - box).coerceAtLeast(0))
            }
        }
        val w = minOf(want, room(vx)).coerceAtLeast(1)
        val h = minOf(size.height, (screen.heightPx - 2 * margin).coerceAtLeast(1))
        val bx = when (side) {
            WorkboardSide.RIGHT -> vx + box - tuck
            WorkboardSide.LEFT -> vx + tuck - w
        }
        val by = (vy + box / 2 - h / 2).coerceIn(margin, (screen.heightPx - margin - h).coerceAtLeast(margin))

        val left = minOf(vx, bx)
        val top = minOf(vy, by)
        val right = maxOf(vx + box, bx + w)
        val bottom = maxOf(vy + box, by + h)
        return WorkboardLayout(
            windowX = left,
            windowY = top,
            windowWidth = right - left,
            windowHeight = bottom - top,
            van = OverlayRect(vx - left, vy - top, box, box),
            board = OverlayRect(bx - left, by - top, w, h),
            side = side,
        )
    }
}
