package com.dial.van.overlay

/** Intent decisions only. No window, command, microphone or navigation side effects. */
enum class OverlayDismissStep { HIDE_KEYBOARD, RETURN_TO_CHARACTER, NONE }

object OverlayUsabilityPolicy {
    fun dismiss(isWorkboard: Boolean, keyboardVisible: Boolean): OverlayDismissStep = when {
        !isWorkboard -> OverlayDismissStep.NONE
        keyboardVisible -> OverlayDismissStep.HIDE_KEYBOARD
        else -> OverlayDismissStep.RETURN_TO_CHARACTER
    }

    fun canSubmit(draft: String, submitting: Boolean): Boolean = draft.isNotBlank() && !submitting

    /** A long final answer must expose its bottom, not repeatedly scroll to its top. */
    fun tailOverflow(itemOffsetPx: Int, itemSizePx: Int, viewportEndPx: Int): Int =
        (itemOffsetPx.toLong() + itemSizePx.coerceAtLeast(0) - viewportEndPx)
            .coerceIn(0L, Int.MAX_VALUE.toLong()).toInt()

    /** Pending capture is not the same thing as a live microphone. */
    fun voiceStatus(listening: Boolean, speaking: Boolean, turnPending: Boolean): String = when {
        listening -> "Microphone on — listening"
        speaking -> "VAN is speaking"
        turnPending -> "Processing your voice — microphone is off"
        else -> "Microphone off"
    }

    fun quickControlsWidth(availableDp: Float): Float =
        availableDp.takeIf { it.isFinite() && it > 0 }?.coerceAtMost(360f) ?: 184f

    fun quickControlsHeight(availableDp: Float): Float =
        availableDp.takeIf { it.isFinite() && it > 0 }?.coerceAtMost(336f) ?: 336f
}

enum class ConversationScrollIntent { NONE, IMMEDIATE, ANIMATE }

/**
 * Content growth does not count as the owner scrolling away. A single explicit
 * Latest action resumes following; the complete list is retained, not takeLast(8).
 * The Compose adapter identifies programmatic scrolls and passes only owner input.
 */
class ConversationFollowPolicy {
    var following: Boolean = true; private set
    var unread: Boolean = false; private set
    private var initialized = false
    private var tailId: String? = null
    private var tailRevision: String? = null

    fun ownerViewport(atLatest: Boolean, interacting: Boolean) {
        if (!initialized) return
        if (interacting) following = atLatest
        if (atLatest) { following = true; unread = false }
    }

    fun content(id: String?, revision: String?, ownerMessage: Boolean, ownerInteracting: Boolean): ConversationScrollIntent {
        if (id == null) {
            initialized = false; tailId = null; tailRevision = null; following = true; unread = false
            return ConversationScrollIntent.NONE
        }
        val first = !initialized
        val appended = tailId != id
        val changed = appended || tailRevision != revision
        initialized = true; tailId = id; tailRevision = revision
        if (!changed && !first) return ConversationScrollIntent.NONE
        if (first || (appended && ownerMessage)) following = true
        if (ownerInteracting) { unread = true; following = false; return ConversationScrollIntent.NONE }
        if (!following) { unread = true; return ConversationScrollIntent.NONE }
        unread = false
        return if (first) ConversationScrollIntent.IMMEDIATE else ConversationScrollIntent.ANIMATE
    }

    fun latest(): ConversationScrollIntent {
        initialized = true; following = true; unread = false
        return ConversationScrollIntent.ANIMATE
    }
}

