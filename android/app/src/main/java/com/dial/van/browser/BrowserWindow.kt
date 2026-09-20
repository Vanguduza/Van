package com.dial.van.browser

import kotlin.math.abs
import kotlin.math.max
import kotlin.math.roundToInt

/**
 * Rev 1.5 §§0D.1, 12 — the window VAN Browser is drawn in, and how a change to it reaches
 * the remote Chromium without breaking the picture in between.
 *
 * All of this is arithmetic over window bounds, which is why it is here and not in the
 * Activity: a Samsung pop-up window being dragged by its corner produces a resize callback
 * per frame, and the difference between a browser that survives that and one that
 * renegotiates a remote browser sixty times a second is a debounce, a cadence and an
 * atomic swap — three decisions that are testable and none of which needs a display.
 *
 * ADR-RB-022 is the constraint the whole file serves: **a resize is not a new session.**
 * Nothing here creates, ends or reconnects anything; it produces viewport candidates and
 * decides what to draw until one is acknowledged.
 */

/** §12.4 — informational only. Never a basis for authority. */
enum class WindowMode {
    FULLSCREEN,
    SPLIT,
    FREEFORM_POPUP,
    DESKTOP_FREEFORM,
    UNKNOWN_RESIZABLE,
}

/**
 * §12.4 — one candidate viewport, whole.
 *
 * Every field the server needs to resize Chromium travels together and is acknowledged
 * together. A candidate that arrived in pieces would let the server resize the window to
 * one revision's width and the capture to another's.
 */
data class ViewportCandidate(
    val revision: Int,
    val androidWindowWidthPx: Int,
    val androidWindowHeightPx: Int,
    val contentWidthPx: Int,
    val contentHeightPx: Int,
    val density: Float,
    val fontScale: Float,
    val displayRotation: Int,
    val windowMode: WindowMode,
    val systemInsetsPx: Insets,
    val browserChromeInsetsPx: Insets,
) {
    val contentWidthDp: Int get() = (contentWidthPx / density).roundToInt()

    /**
     * How much chrome fits, from the *window* rather than the display.
     *
     * `BrowserWindowClass` already existed in `BrowserModels.kt` with these breakpoints.
     * A second enum here would have been two answers to "is this narrow", and they would
     * have diverged the first time one of them moved.
     */
    val chromeClass: BrowserWindowClass get() = BrowserWindowClass.forWidthDp(contentWidthDp)

    /** Whether this differs from [other] by enough to be worth a remote resize. */
    fun differsMateriallyFrom(other: ViewportCandidate?, minimumPx: Int = MINIMUM_DELTA_PX): Boolean {
        if (other == null) return true
        return abs(contentWidthPx - other.contentWidthPx) >= minimumPx ||
            abs(contentHeightPx - other.contentHeightPx) >= minimumPx ||
            displayRotation != other.displayRotation ||
            density != other.density ||
            fontScale != other.fontScale
    }

    companion object {
        /**
         * Below this, a resize is not worth a round trip.
         *
         * A one-pixel change comes from rounding an inset, and renegotiating Chromium for
         * it costs a reflow the owner sees. Not zero and not large: eight pixels is under
         * a line of text at any density VAN supports.
         */
        const val MINIMUM_DELTA_PX = 8
    }
}

data class Insets(val left: Int, val top: Int, val right: Int, val bottom: Int) {
    companion object {
        val NONE = Insets(0, 0, 0, 0)
    }
}

/**
 * §12.1 — the content rectangle, after everything that is not the page has taken its share.
 *
 * Computed rather than measured because the order matters and getting it wrong is silent:
 * subtracting the keyboard from a height that already excluded the navigation bar shrinks
 * the page twice, and the owner sees a remote browser that thinks the screen is smaller
 * than it is.
 */
object ContentViewport {

    fun compute(
        windowWidthPx: Int,
        windowHeightPx: Int,
        systemInsets: Insets,
        chromeInsets: Insets,
        keyboardInsetPx: Int = 0,
    ): Pair<Int, Int> {
        val width = windowWidthPx - systemInsets.left - systemInsets.right -
            chromeInsets.left - chromeInsets.right
        // The keyboard and the navigation bar overlap: the IME inset already includes the
        // gesture bar it is drawn over. Taking the larger of the two rather than the sum
        // is what stops the page losing that strip twice.
        val bottom = max(systemInsets.bottom, keyboardInsetPx)
        val height = windowHeightPx - systemInsets.top - bottom -
            chromeInsets.top - chromeInsets.bottom
        return max(0, width) to max(0, height)
    }
}

/**
 * §12.3 — what to send to the server while the owner is dragging a window corner.
 *
 * Two stages, and the first one never leaves the phone: the decoded frame is scaled to the
 * new rectangle immediately, so the window follows the finger. The second is bounded — a
 * candidate only after the bounds have been still for [STABILITY_MS], at most one remote
 * resize per [MIN_INTERVAL_MS], and a final settle within [SETTLE_MS] of the last change
 * so a drag that ends inside the debounce still converges.
 *
 * A consequence worth stating because it looks like a bug: a perfectly smooth drag sends
 * **nothing** remote while the finger is down. There is never [STABILITY_MS] of stillness,
 * so the local stage carries the whole drag and one candidate follows when it stops. The
 * cadence bounds the case that actually produces many messages — a drag with pauses in it,
 * or an inset storm during a fold — rather than the smooth one.
 *
 * The settle is the part that is easy to leave out and impossible to notice in testing: a
 * drag ending mid-debounce with no final message leaves Chromium at the second-to-last
 * size forever, and the owner has a browser that is permanently a few pixels wrong.
 */
class ResizeCoalescer(
    /**
     * The viewport the server is already at, so the first callback after a rotation is
     * compared against something. Constructed without one, every first candidate is
     * material — including a one-pixel inset rounding, which is the case
     * [ViewportCandidate.MINIMUM_DELTA_PX] exists to drop.
     */
    initial: ViewportCandidate? = null,
    private val minIntervalMs: Long = MIN_INTERVAL_MS,
    private val stabilityMs: Long = STABILITY_MS,
) {

    private var pending: ViewportCandidate? = null
    private var lastChangeAtMs: Long = 0L
    private var lastSentAtMs: Long = 0L
    private var hasSent: Boolean = false
    private var lastSent: ViewportCandidate? = initial

    /** A new window rectangle. Returns a candidate to send now, or null to keep waiting. */
    fun onWindowChanged(candidate: ViewportCandidate, nowMs: Long): ViewportCandidate? {
        if (!candidate.differsMateriallyFrom(lastSent)) {
            // Back to where it already is. Drop the pending change rather than sending a
            // resize to the size the server is already at.
            pending = null
            return null
        }
        if (pending == null || candidate.differsMateriallyFrom(pending, minimumPx = 1)) {
            pending = candidate
            lastChangeAtMs = nowMs
        }
        return emitIfDue(nowMs)
    }

    /**
     * The clock moved and no new bounds arrived. Returns the settle message when one is
     * due.
     *
     * The caller drives this from whatever timer it already has; the decision of whether
     * anything is due is here, where it can be executed.
     */
    fun onTick(nowMs: Long): ViewportCandidate? = emitIfDue(nowMs)

    /** The drag ended. Whatever is pending goes now, cadence or not. */
    fun onSettled(nowMs: Long): ViewportCandidate? {
        val candidate = pending ?: return null
        return send(candidate, nowMs)
    }

    private fun emitIfDue(nowMs: Long): ViewportCandidate? {
        val candidate = pending ?: return null
        val sinceLastChange = nowMs - lastChangeAtMs
        if (sinceLastChange < stabilityMs) return null
        // `hasSent` rather than a sentinel timestamp: `Long.MIN_VALUE` here overflows
        // the subtraction to a negative, so the very first candidate of a session was
        // held by a rate limit it had never used. It read as "the resize protocol does
        // nothing", which is exactly what the drag test caught.
        if (hasSent && nowMs - lastSentAtMs < minIntervalMs) return null
        return send(candidate, nowMs)
    }

    private fun send(candidate: ViewportCandidate, nowMs: Long): ViewportCandidate {
        pending = null
        lastSent = candidate
        lastSentAtMs = nowMs
        hasSent = true
        return candidate
    }

    companion object {
        /** §12.3 — at most ten remote resizes a second while a drag is in progress. */
        const val MIN_INTERVAL_MS = 100L

        /** §12.3 — 80-120ms. The middle, so neither bound is a cliff. */
        const val STABILITY_MS = 100L

        /**
         * §12.3's "final settle message <= 250 ms after final bounds", satisfied by
         * [STABILITY_MS] rather than by a rule of its own.
         *
         * A first version had a separate overdue branch that sent regardless of cadence
         * once a pending change reached this age. A mutation deleting it changed nothing,
         * and the reason is structural: a pending change is only created by
         * `onWindowChanged`, which also stamps the change time, so a pending candidate
         * always post-dates the last send. `sinceLastChange >= 250` therefore implies
         * `now - lastSent >= 250`, and the cadence — 100ms — can never be what is holding
         * it. The branch could not execute. It was removed rather than the mutation
         * weakened, and this constant stays as the bound the stability rule satisfies:
         * the settle arrives 100ms after the final bounds, inside the 250 §12.3 allows.
         */
        const val SETTLE_MS = 250L
    }
}

/**
 * §12.2 / §12.4 — what the owner is looking at between sending a revision and the first
 * frame that answers it.
 *
 * Three things swap at once when that frame arrives: the render transform, the touch
 * transform and the reported viewport. Swapping them separately is the bug this class
 * exists to prevent — a render transform updated before the touch transform means every
 * tap during the gap lands at the old scale, on a page that has already reflowed, and the
 * owner's finger is somewhere they did not aim.
 *
 * Until then the previous frame is scaled and letterboxed, and §12.2 forbids transforming
 * input across an unacknowledged reflow: `acceptsInput` is false, not "best effort".
 */
class ViewportSwap(initial: ViewportCandidate) {

    /** What the server has acknowledged and is producing frames for. */
    var live: ViewportCandidate = initial
        private set

    /** Sent, not yet acknowledged. */
    var inFlight: ViewportCandidate? = null
        private set

    private var acknowledged: Int = initial.revision

    /** §12.2 — input is withheld across an unacknowledged reflow rather than transformed. */
    val acceptsInput: Boolean get() = inFlight == null

    fun onSent(candidate: ViewportCandidate) {
        require(candidate.revision > live.revision) {
            "browser_viewport_revision_must_advance"
        }
        inFlight = candidate
    }

    /**
     * The server acknowledged a revision. The picture does not change yet.
     *
     * Acknowledgement and the first frame are different moments and §12.4 names both: the
     * server has resized Chromium, but the frame in the decoder is still the old size.
     * Swapping here would stretch the old picture to the new rectangle for as long as the
     * next frame takes.
     */
    fun onAcked(revision: Int) {
        if (revision > acknowledged) acknowledged = revision
    }

    /**
     * A frame arrived carrying the revision it was rendered at. Returns true if this is
     * the swap.
     *
     * A frame for a revision older than the one in flight is the tail of the previous
     * size and is drawn letterboxed, not swapped to.
     */
    fun onFrame(revision: Int): Boolean {
        val candidate = inFlight ?: return false
        if (revision < candidate.revision) return false
        if (acknowledged < candidate.revision) return false
        live = candidate
        inFlight = null
        return true
    }

    /**
     * How to draw the current frame in the window it is being shown in.
     *
     * Uniform scale with letterboxing, never a stretch: a remote page drawn at the wrong
     * aspect ratio is a page the owner cannot read, and the whole point of holding the old
     * frame is that it stays legible until the new one arrives.
     */
    fun letterbox(frameWidthPx: Int, frameHeightPx: Int): Letterbox {
        val target = live
        if (frameWidthPx <= 0 || frameHeightPx <= 0) return Letterbox(1f, 0, 0)
        val scale = minOf(
            target.contentWidthPx.toFloat() / frameWidthPx,
            target.contentHeightPx.toFloat() / frameHeightPx,
        )
        val drawnWidth = (frameWidthPx * scale).roundToInt()
        val drawnHeight = (frameHeightPx * scale).roundToInt()
        return Letterbox(
            scale = scale,
            offsetXPx = (target.contentWidthPx - drawnWidth) / 2,
            offsetYPx = (target.contentHeightPx - drawnHeight) / 2,
        )
    }
}

data class Letterbox(val scale: Float, val offsetXPx: Int, val offsetYPx: Int)
