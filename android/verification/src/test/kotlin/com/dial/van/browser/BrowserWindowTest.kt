package com.dial.van.browser

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertNull
import kotlin.test.assertTrue

private fun candidate(
    revision: Int = 1,
    width: Int = 1080,
    height: Int = 2016,
    density: Float = 3f,
    rotation: Int = 0,
    mode: WindowMode = WindowMode.FULLSCREEN,
) = ViewportCandidate(
    revision = revision,
    androidWindowWidthPx = width,
    androidWindowHeightPx = height,
    contentWidthPx = width,
    contentHeightPx = height,
    density = density,
    fontScale = 1f,
    displayRotation = rotation,
    windowMode = mode,
    systemInsetsPx = Insets.NONE,
    browserChromeInsetsPx = Insets.NONE,
)

/**
 * Rev 1.5 §12.1 — the content rectangle, and the double subtraction that is invisible
 * until someone measures the remote page.
 */
class ContentViewportTest {

    @Test
    fun `chrome and system insets both come off`() {
        val (width, height) = ContentViewport.compute(
            windowWidthPx = 1080,
            windowHeightPx = 2016,
            systemInsets = Insets(left = 0, top = 96, right = 0, bottom = 48),
            chromeInsets = Insets(left = 0, top = 144, right = 0, bottom = 0),
        )
        assertEquals(1080, width)
        assertEquals(2016 - 96 - 48 - 144, height)
    }

    @Test
    fun `the keyboard and the navigation bar are not subtracted twice`() {
        // The IME inset is measured from the bottom of the window and already covers the
        // gesture bar it is drawn over. Adding them gives the page 48px less than it has,
        // and the remote Chromium reflows to a height that does not exist.
        val (_, withKeyboard) = ContentViewport.compute(
            windowWidthPx = 1080,
            windowHeightPx = 2016,
            systemInsets = Insets(0, 96, 0, 48),
            chromeInsets = Insets.NONE,
            keyboardInsetPx = 800,
        )
        assertEquals(2016 - 96 - 800, withKeyboard)
    }

    @Test
    fun `a window smaller than its insets reports zero rather than a negative`() {
        // A negative viewport travels to the server and becomes a Chromium resize to a
        // negative height. It happens during a transition, for one frame, and the session
        // does not come back.
        val (width, height) = ContentViewport.compute(
            windowWidthPx = 100,
            windowHeightPx = 100,
            systemInsets = Insets(80, 80, 80, 80),
            chromeInsets = Insets(80, 80, 80, 80),
        )
        assertEquals(0, width)
        assertEquals(0, height)
    }
}

/**
 * §0D.1 — how much chrome fits, decided from the window rather than the display.
 *
 * The enum is `BrowserWindowClass`, which already existed. These tests are about the
 * viewport candidate asking it the right question: with the *content* width, in dp,
 * after the insets.
 */
class ViewportChromeClassTest {

    @Test
    fun `the breakpoints are Android's own`() {
        assertEquals(BrowserWindowClass.COMPACT, BrowserWindowClass.forWidthDp(599))
        assertEquals(BrowserWindowClass.MEDIUM, BrowserWindowClass.forWidthDp(600))
        assertEquals(BrowserWindowClass.MEDIUM, BrowserWindowClass.forWidthDp(839))
        assertEquals(BrowserWindowClass.EXPANDED, BrowserWindowClass.forWidthDp(840))
    }

    @Test
    fun `a tablet in split screen gets a phone's chrome`() {
        // The whole reason this reads the window and not the display. A 2560px tablet at
        // density 2 is 1280dp and expanded; the same tablet giving the browser a quarter
        // of its width is 320dp, which is a phone. A layout that asked the display would
        // put a five-item toolbar into that column and the address field would have no
        // room left.
        val whole = candidate(width = 2560, density = 2f)
        assertEquals(BrowserWindowClass.EXPANDED, whole.chromeClass)
        assertEquals(BrowserWindowClass.MEDIUM, whole.copy(contentWidthPx = 1400).chromeClass)
        assertEquals(BrowserWindowClass.COMPACT, whole.copy(contentWidthPx = 640).chromeClass)
    }
}

/**
 * §12.3 — a Samsung pop-up window being dragged by its corner, and what reaches the server.
 */
class ResizeCoalescerTest {

    @Test
    fun `a smooth drag sends nothing remote while the finger is down`() {
        // This looks like a bug and is the design. A Samsung pop-up dragged by its corner
        // produces a callback per frame and never holds still, so the local stage carries
        // the whole drag — the decoded frame is scaled to the new rectangle and the window
        // follows the finger — and Chromium is renegotiated once, when it stops.
        val coalescer = ResizeCoalescer(initial = candidate(revision = 1))
        var sent = 0
        var now = 0L
        for (step in 1..60) {
            now += 16
            val width = 1080 - step * 4
            if (coalescer.onWindowChanged(candidate(revision = step + 1, width = width), now) != null) {
                sent += 1
            }
        }
        assertEquals(0, sent)

        val settled = coalescer.onTick(now + ResizeCoalescer.STABILITY_MS)
        assertNotNull(settled, "and exactly one when it stops")
        assertEquals(1080 - 60 * 4, settled.contentWidthPx)
    }

    @Test
    fun `a drag with pauses is capped at ten a second`() {
        // The case the cadence is actually for: bounds that hold still just long enough to
        // clear the debounce, over and over. Without the cap this renegotiates Chromium
        // twenty times a second and the page reflows through every one of them.
        val coalescer = ResizeCoalescer(initial = candidate(revision = 1))
        var sent = 0
        var now = 0L
        for (step in 1..20) {
            now += 50
            coalescer.onWindowChanged(candidate(revision = step + 1, width = 1080 - step * 20), now)
            now += 100
            if (coalescer.onTick(now) != null) sent += 1
        }
        // Three seconds of this: ten a second is thirty, and the pauses give fewer.
        assertTrue(sent <= 3 * 10, "sent $sent")
        assertTrue(sent >= 5, "the server does have to follow along: sent $sent")
    }

    @Test
    fun `a change is held until the bounds have been still`() {
        val coalescer = ResizeCoalescer()
        assertNull(coalescer.onWindowChanged(candidate(revision = 2, width = 900), 0L))
        assertNull(coalescer.onTick(50L), "still inside the stability window")
        assertNotNull(coalescer.onTick(120L))
    }

    @Test
    fun `a drag that ends inside the debounce still converges, inside the settle window`() {
        // The one that is easy to leave out and impossible to see in testing: the last
        // bounds arrive, nothing else ever happens, and Chromium stays at the
        // second-to-last size for the rest of the session.
        //
        // §12.3 allows 250ms for that final message. The stability rule delivers it in
        // 100, which is why there is no separate overdue branch: a mutation deleting one
        // changed nothing, because a pending change always post-dates the last send and
        // the cadence can never be what is holding it.
        val coalescer = ResizeCoalescer()
        var now = 0L
        for (step in 1..5) {
            now += 20
            coalescer.onWindowChanged(candidate(revision = step + 1, width = 1080 - step * 20), now)
        }
        assertNull(coalescer.onTick(now + 10))
        val settled = coalescer.onTick(now + ResizeCoalescer.STABILITY_MS)
        assertNotNull(settled, "the final bounds have to arrive")
        assertEquals(1080 - 5 * 20, settled.contentWidthPx)
        assertTrue(
            ResizeCoalescer.STABILITY_MS <= ResizeCoalescer.SETTLE_MS,
            "and inside the window §12.3 allows",
        )
    }

    @Test
    fun `releasing the window sends the last bounds immediately`() {
        val coalescer = ResizeCoalescer()
        coalescer.onWindowChanged(candidate(revision = 2, width = 800), 10L)
        val settled = coalescer.onSettled(20L)
        assertNotNull(settled)
        assertEquals(800, settled.contentWidthPx)
        assertNull(coalescer.onSettled(30L), "and nothing is sent twice")
    }

    @Test
    fun `a window dragged back to where it started sends nothing`() {
        val coalescer = ResizeCoalescer(initial = candidate(revision = 1, width = 1080))
        val first = coalescer.onWindowChanged(candidate(revision = 2, width = 900), 0L)
            ?: coalescer.onTick(200L)
        assertNotNull(first)
        // Out and back inside one debounce. The server is already at 900.
        coalescer.onWindowChanged(candidate(revision = 3, width = 700), 210L)
        assertNull(coalescer.onWindowChanged(candidate(revision = 4, width = 900), 220L))
        assertNull(coalescer.onTick(600L))
    }

    @Test
    fun `a one pixel inset rounding is not a resize`() {
        // Against the viewport the server is already at. A coalescer with no baseline
        // treats its first candidate as material, which is right for a rotation and
        // wrong for this.
        val coalescer = ResizeCoalescer(initial = candidate(revision = 1, width = 1080))
        assertNull(coalescer.onWindowChanged(candidate(revision = 2, width = 1081), 0L))
        assertNull(coalescer.onTick(500L))
    }

    @Test
    fun `the first candidate of a session is sent even without a baseline`() {
        // The other side of the test above: a coalescer that has never sent anything has
        // nothing to compare against, and holding the first viewport back would leave the
        // server at whatever size it guessed.
        val coalescer = ResizeCoalescer()
        coalescer.onWindowChanged(candidate(revision = 2, width = 1081), 0L)
        assertNotNull(coalescer.onTick(200L))
    }

    @Test
    fun `a rotation is material even at the same size`() {
        // A square window rotating keeps its pixel dimensions and is still a different
        // page: the remote layout depends on the orientation it is told about.
        val coalescer = ResizeCoalescer()
        coalescer.onWindowChanged(candidate(revision = 1, width = 1000, height = 1000), 0L)
        coalescer.onTick(300L)
        val rotated = candidate(revision = 2, width = 1000, height = 1000, rotation = 1)
        coalescer.onWindowChanged(rotated, 400L)
        assertNotNull(coalescer.onTick(700L))
    }

    @Test
    fun `a font scale change is material`() {
        val coalescer = ResizeCoalescer()
        coalescer.onWindowChanged(candidate(revision = 1), 0L)
        coalescer.onTick(300L)
        coalescer.onWindowChanged(candidate(revision = 2).copy(fontScale = 1.3f), 400L)
        assertNotNull(coalescer.onTick(700L))
    }
}

/**
 * §12.2 / §12.4 — the swap, and the gap before it.
 */
class ViewportSwapTest {

    @Test
    fun `input is withheld while a revision is unacknowledged`() {
        // §12.2 forbids transforming coordinates across an unacknowledged reflow. The
        // alternative is not "slightly wrong taps": the page has moved and the owner's
        // finger lands on whatever is now under it.
        val swap = ViewportSwap(candidate(revision = 1))
        assertTrue(swap.acceptsInput)
        swap.onSent(candidate(revision = 2, width = 800))
        assertFalse(swap.acceptsInput)
    }

    @Test
    fun `the acknowledgement alone does not swap the picture`() {
        // The server has resized Chromium; the frame in the decoder is still the old size.
        // Swapping here stretches the old picture to the new rectangle for as long as the
        // next frame takes to arrive.
        val swap = ViewportSwap(candidate(revision = 1))
        swap.onSent(candidate(revision = 2, width = 800))
        swap.onAcked(2)
        assertEquals(1080, swap.live.contentWidthPx)
        assertFalse(swap.acceptsInput)
    }

    @Test
    fun `the first frame for the new revision swaps everything at once`() {
        val swap = ViewportSwap(candidate(revision = 1))
        swap.onSent(candidate(revision = 2, width = 800))
        swap.onAcked(2)
        assertTrue(swap.onFrame(2))
        assertEquals(800, swap.live.contentWidthPx)
        assertTrue(swap.acceptsInput)
    }

    @Test
    fun `a trailing frame from the old size does not swap`() {
        val swap = ViewportSwap(candidate(revision = 1))
        swap.onSent(candidate(revision = 2, width = 800))
        swap.onAcked(2)
        assertFalse(swap.onFrame(1), "the tail of the previous size is drawn, not adopted")
        assertEquals(1080, swap.live.contentWidthPx)
        assertFalse(swap.acceptsInput)
    }

    @Test
    fun `a frame cannot swap a revision the server never acknowledged`() {
        // A host that sent frames for a revision it had not resized to would otherwise
        // move the touch transform to a layout that does not exist.
        val swap = ViewportSwap(candidate(revision = 1))
        swap.onSent(candidate(revision = 2, width = 800))
        assertFalse(swap.onFrame(2))
        assertEquals(1080, swap.live.contentWidthPx)
    }

    @Test
    fun `a revision must advance`() {
        val swap = ViewportSwap(candidate(revision = 5))
        val failure = runCatching { swap.onSent(candidate(revision = 5)) }.exceptionOrNull()
        assertNotNull(failure)
    }

    @Test
    fun `the held frame is letterboxed rather than stretched`() {
        // A page drawn at the wrong aspect ratio is a page the owner cannot read, which
        // defeats the point of holding the old frame at all.
        val swap = ViewportSwap(candidate(revision = 1, width = 1000, height = 1000))
        val box = swap.letterbox(frameWidthPx = 500, frameHeightPx = 1000)
        assertEquals(1f, box.scale)
        assertEquals(250, box.offsetXPx, "centred horizontally")
        assertEquals(0, box.offsetYPx)
    }

    @Test
    fun `a frame larger than the window is scaled down uniformly`() {
        val swap = ViewportSwap(candidate(revision = 1, width = 500, height = 500))
        val box = swap.letterbox(frameWidthPx = 2000, frameHeightPx = 1000)
        assertEquals(0.25f, box.scale)
        assertEquals(0, box.offsetXPx)
        assertEquals(125, box.offsetYPx)
    }

    @Test
    fun `a frame with no pixels does not divide by zero`() {
        val swap = ViewportSwap(candidate(revision = 1))
        val box = swap.letterbox(frameWidthPx = 0, frameHeightPx = 0)
        assertEquals(1f, box.scale)
    }
}
