package com.dial.van.overlay

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

class WorkboardPlacementTest {
    private fun plan(screen: OverlayScreen, rect: OverlayRect, ime: Int? = null,
                     desired: OverlaySize = OverlaySize(380, 520), manual: OverlayPlacement? = null) =
        WorkboardPlacement.plan(screen, rect, desired, OverlaySize(240, 200), ime,
            preferredManualPosition = manual)
    private fun assertSafe(layout: WorkboardLayout, screen: OverlayScreen, ime: Int? = null) {
        val safe = WorkboardPlacement.available(screen, ime, 8)
        assertTrue(layout.position.x >= safe.safeLeft)
        assertTrue(layout.position.y >= safe.safeTop)
        assertTrue(layout.size.widthPx >= 1 && layout.size.heightPx >= 1)
        assertTrue(layout.position.x.toLong() + layout.size.widthPx <= safe.safeRight)
        assertTrue(layout.position.y.toLong() + layout.size.heightPx <= safe.safeBottom)
    }
    @Test fun leftEdgeOpensIntoAvailableRightSpace() {
        val result = plan(OverlayScreen(1_200, 900), OverlayRect(20.0, 250.0, 180.0, 410.0))
        assertEquals(WorkboardSide.RIGHT, result.side); assertTrue(result.position.x >= 188)
    }
    @Test fun rightEdgeOpensToTheLeft() {
        val result = plan(OverlayScreen(1_200, 900), OverlayRect(1_020.0, 250.0, 1_180.0, 410.0))
        assertEquals(WorkboardSide.LEFT, result.side); assertTrue(result.position.x + result.size.widthPx <= 1_012)
    }
    @Test fun nearBottomPhoneOpensAboveTheAvatar() {
        val result = plan(OverlayScreen(420, 900), OverlayRect(210.0, 700.0, 394.0, 884.0))
        assertEquals(WorkboardSide.ABOVE, result.side)
        assertTrue(result.position.y + result.size.heightPx <= 692)
    }
    @Test fun nearTopPhoneOpensBelowInsteadOfOffscreen() {
        val result = plan(OverlayScreen(420, 900), OverlayRect(10.0, 30.0, 194.0, 214.0))
        assertEquals(WorkboardSide.BELOW, result.side); assertTrue(result.position.y >= 222)
    }
    @Test fun keyboardTopDefinesTheActualUsableViewport() {
        val screen = OverlayScreen(420, 900, topPx = 28, bottomPx = 872)
        val result = plan(screen, OverlayRect(200.0, 700.0, 384.0, 884.0), 440)
        assertSafe(result, screen, 440); assertTrue(result.position.y + result.size.heightPx <= 432)
    }
    @Test fun absentKeyboardDoesNotReserveAStaleKeyboardHeight() {
        val result = plan(OverlayScreen(420, 900), OverlayRect(10.0, 40.0, 194.0, 224.0))
        assertEquals(520, result.size.heightPx)
    }
    @Test fun landscapeAndInsetCutoutsAreRespected() {
        val screen = OverlayScreen(960, 420, leftPx = 48, topPx = 24, rightPx = 930, bottomPx = 400)
        assertSafe(plan(screen, OverlayRect(700.0, 200.0, 884.0, 384.0)), screen)
    }
    @Test fun resizeKeepsAnIntentionalDragPositionWhenPossible() {
        val screen = OverlayScreen(1_200, 900)
        val result = plan(screen, OverlayRect(0.0, 0.0, 184.0, 184.0), manual = OverlayPlacement(550, 280))
        assertEquals(WorkboardSide.MANUAL, result.side); assertEquals(OverlayPlacement(550, 280), result.position)
    }
    @Test fun manualPlacementStillMovesOutOfAKeyboard() {
        val screen = OverlayScreen(420, 900)
        assertSafe(plan(screen, OverlayRect(20.0, 30.0, 204.0, 214.0), 410, manual = OverlayPlacement(100, 600)), screen, 410)
    }
    @Test fun smallerRemainingAreaBecomesScrollableNotOffscreen() {
        val screen = OverlayScreen(320, 200, topPx = 24, bottomPx = 182)
        val result = plan(screen, OverlayRect(100.0, 80.0, 284.0, 264.0))
        assertSafe(result, screen); assertTrue(result.size.heightPx <= 142)
        assertEquals(WorkboardSide.AVAILABLE_SPACE, result.side)
    }
    @Test fun fallbackDoesNotLetHugeFontScaledHeightEscape() {
        val screen = OverlayScreen(360, 620)
        assertSafe(plan(screen, OverlayRect(160.0, 250.0, 344.0, 434.0), desired = OverlaySize(500, 2_000)), screen)
    }
    @Test fun degenerateOrNonfiniteAnchorFailsToBoundedLayout() {
        for (anchor in listOf(OverlayRect(Double.NaN, Double.NaN, Double.NaN, Double.NaN), OverlayRect(400.0, 900.0, -10.0, -30.0))) {
            assertSafe(plan(OverlayScreen(360, 800), anchor), OverlayScreen(360, 800))
        }
    }
    @Test fun repeatedLayoutHasNoPlacementOscillation() {
        val screen = OverlayScreen(480, 900); val anchor = OverlayRect(250.0, 600.0, 434.0, 784.0)
        val expected = plan(screen, anchor, 560)
        repeat(100) { assertEquals(expected, plan(screen, anchor, 560)) }
    }
    @Test fun twentyThousandActualSizeInsetsKeyboardScenariosStayOnScreen() {
        val random = Random(405)
        repeat(20_000) {
            val w = random.nextInt(160, 2_400); val h = random.nextInt(120, 2_500)
            val screen = OverlayScreen(w, h, random.nextInt(0, w / 8), random.nextInt(0, h / 8),
                w - random.nextInt(0, w / 8), h - random.nextInt(0, h / 8))
            val x = random.nextInt(-100, w + 100).toDouble(); val y = random.nextInt(-100, h + 100).toDouble()
            val ime = if (random.nextBoolean()) random.nextInt(screen.safeTop + 2, screen.safeBottom + 1) else null
            val actual = plan(screen, OverlayRect(x, y, x + 184, y + 184), ime,
                desired = OverlaySize(random.nextInt(180, 1_100), random.nextInt(160, 1_600)))
            assertSafe(actual, screen, ime)
        }
    }
    @Test fun fullscreenBackgroundBelowOurKnownWindowDoesNotFreezeAura() {
        assertEquals(false, OverlayWindowAwareness.externalFullscreenCoversOverlay(true, false, 4, 8))
    }
    @Test fun higherOrUnknownFullscreenWindowRetainsConservativePause() {
        assertEquals(true, OverlayWindowAwareness.externalFullscreenCoversOverlay(true, false, 8, 4))
        assertEquals(true, OverlayWindowAwareness.externalFullscreenCoversOverlay(true, false, 8, null))
        assertEquals(true, OverlayWindowAwareness.externalFullscreenCoversOverlay(true, false, 8, 8))
    }
    @Test fun normalOrSystemBarsVisibleWindowsDoNotPretendFullOcclusion() {
        assertEquals(false, OverlayWindowAwareness.externalFullscreenCoversOverlay(false, false, 8, null))
        assertEquals(false, OverlayWindowAwareness.externalFullscreenCoversOverlay(true, true, 8, null))
    }
    @Test fun firstOpenAndFurtherExpansionRetainTheSameRestingAnchor() {
        val session = WorkboardPlacementSession(); session.opened(OverlayPlacement(200, 400), OverlaySize(184, 184))
        val first = session.anchor; session.opened(OverlayPlacement(20, 30), OverlaySize(380, 520))
        assertEquals(first, session.anchor); assertEquals(OverlayPlacement(200, 400), session.close())
        assertNull(session.anchor); assertNull(session.manualPosition)
    }
    @Test fun intentionalBoardDragDoesNotDestroyTheRestingCharacterLocation() {
        val session = WorkboardPlacementSession(); session.opened(OverlayPlacement(300, 500), OverlaySize(184, 184))
        session.moved(OverlayPlacement(20, 80)); assertEquals(OverlayPlacement(20, 80), session.manualPosition)
        assertEquals(OverlayPlacement(300, 500), session.close()); session.opened(OverlayPlacement(40, 70), OverlaySize(72, 72))
        assertNotNull(session.anchor); assertNull(session.manualPosition)
    }
}
