package com.dial.van.overlay

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Owner direction (2026-09-25): the workboard opens beside VAN, not around him. VAN on the
 * right of the screen, the board on his left; VAN on the left, the board on his right. The
 * board's controls are never under VAN's own touch area, and nothing lands off screen.
 */
class WorkboardPlacementTest {

    /** A Galaxy S24 Ultra: 1440 x 3120 px at 3.5x, so about 411 dp wide. */
    private val s24 = OverlayScreen(widthPx = 1440, heightPx = 3120)
    private val dp: (Int) -> Int = { (it * 3.5f).toInt() }

    private val boards = listOf(
        VanOverlayPresentation.WORKBOARD_COMPACT,
        VanOverlayPresentation.WORKBOARD_EXPANDED,
        VanOverlayPresentation.WORKBOARD_MAXIMIZED,
    )

    private fun layout(presentation: VanOverlayPresentation, x: Int, y: Int = 900, quick: Boolean = false) =
        WorkboardPlacement.forPresentation(presentation, quick, x, y, s24, dp)

    private fun rightEdgeX() = s24.widthPx - dp(OverlayTheme.RESTING_HIT_DP)

    @Test
    fun `VAN on the right opens the board on his left`() {
        for (board in boards) {
            val placed = layout(board, x = rightEdgeX())
            assertEquals(WorkboardSide.LEFT, placed.side, board.name)
            val rect = assertNotNull(placed.board)
            assertTrue(rect.x < placed.van.x, "${board.name} board is not left of VAN")
        }
    }

    @Test
    fun `VAN on the left opens the board on his right`() {
        for (board in boards) {
            val placed = layout(board, x = 0)
            assertEquals(WorkboardSide.RIGHT, placed.side, board.name)
            val rect = assertNotNull(placed.board)
            assertTrue(rect.right > placed.van.right, "${board.name} board is not right of VAN")
        }
    }

    @Test
    fun `the side follows which half of the screen VAN is on`() {
        val box = dp(OverlayTheme.RESTING_HIT_DP)
        val justLeft = s24.widthPx / 2 - box / 2 - 1
        val justRight = s24.widthPx / 2 - box / 2 + 1
        assertEquals(WorkboardSide.RIGHT, layout(VanOverlayPresentation.WORKBOARD_COMPACT, justLeft).side)
        assertEquals(WorkboardSide.LEFT, layout(VanOverlayPresentation.WORKBOARD_COMPACT, justRight).side)
    }

    @Test
    fun `VAN and the board are always wholly on screen`() {
        val box = dp(OverlayTheme.RESTING_HIT_DP)
        for (board in boards) {
            for (x in listOf(0, 200, 500, 628, 800, 1100, rightEdgeX())) {
                for (y in listOf(0, 900, s24.heightPx - box)) {
                    val placed = layout(board, x, y)
                    val rect = assertNotNull(placed.board)
                    val where = "${board.name} at ($x,$y)"
                    assertTrue(placed.windowX >= 0 && placed.windowY >= 0, "window off the top-left, $where")
                    assertTrue(placed.windowX + placed.windowWidth <= s24.widthPx, "window off the right, $where")
                    assertTrue(placed.windowY + placed.windowHeight <= s24.heightPx, "window off the bottom, $where")
                    assertTrue(rect.x >= 0 && rect.right <= placed.windowWidth, "board outside window, $where")
                    assertTrue(rect.width >= dp(OverlayTheme.WORKBOARD_MIN_WIDTH_DP), "board too narrow, $where")
                }
            }
        }
    }

    @Test
    fun `the board never covers VAN's body, which is all that takes his touch`() {
        val body = dp(OverlayTheme.FLOATING_BODY_WIDTH_DP)
        for (board in boards) {
            for (x in listOf(0, 300, 628, 900, rightEdgeX())) {
                val placed = layout(board, x)
                val rect = assertNotNull(placed.board)
                val bodyLeft = placed.van.x + (placed.van.width - body) / 2
                val bodyRight = bodyLeft + body
                assertTrue(rect.right <= bodyLeft || rect.x >= bodyRight, "${board.name} at $x covers VAN")
            }
        }
    }

    @Test
    fun `VAN stays where he is when there is room beside him`() {
        val atEdge = rightEdgeX()
        val placed = layout(VanOverlayPresentation.WORKBOARD_COMPACT, atEdge, 900)
        assertEquals(atEdge, placed.vanScreenX)
        assertEquals(900, placed.vanScreenY)
    }

    @Test
    fun `quick controls open beside VAN like a board`() {
        val placed = layout(VanOverlayPresentation.FULL_FLOATING, rightEdgeX(), quick = true)
        assertEquals(WorkboardSide.LEFT, placed.side)
        val rect = assertNotNull(placed.board)
        assertEquals(dp(OverlayTheme.QUICK_CONTROLS_WIDTH_DP), rect.width)
        assertTrue(placed.windowX >= 0)
    }

    @Test
    fun `VAN alone, minimized or docked has no board and a window that is just him`() {
        for (presentation in listOf(
            VanOverlayPresentation.FULL_FLOATING,
            VanOverlayPresentation.MINIMIZED,
            VanOverlayPresentation.DOCKED,
        )) {
            val placed = layout(presentation, 300, 700)
            assertNull(placed.board, presentation.name)
            assertEquals(300, placed.windowX)
            assertEquals(700, placed.windowY)
        }
    }

    @Test
    fun `a screen too narrow for VAN and a board still keeps both on it`() {
        // A foldable's cover display.
        val narrow = OverlayScreen(widthPx = 900, heightPx = 2000)
        val placed = WorkboardPlacement.forPresentation(
            VanOverlayPresentation.WORKBOARD_EXPANDED, false, 400, 600, narrow, dp,
        )
        assertTrue(placed.windowX >= 0)
        assertTrue(placed.windowX + placed.windowWidth <= narrow.widthPx)
    }
}
