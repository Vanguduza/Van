package com.dial.van.visual

/** Avoid redundant native input wakeups; still mode owns a finite pose update, not an idle loop. */
class VanRiveUpdateGate {
    private var previous: VanVisualState? = null
    private var previousAnimated: Boolean? = null
    private var suspended = true

    fun next(state: VanVisualState, animate: Boolean, animated: Boolean): VanVisualState? {
        if (!animate) { suspended = true; return null }
        val desired = if (animated) state else state.copy(
            speaking = false, listening = false, attentionX = 0f, attentionY = 0f,
            mouthOpen = 0f, viseme = 0, actionCode = 0, contextCode = 0,
        )
        if (!suspended && desired == previous && animated == previousAnimated) return null
        previous = desired; previousAnimated = animated; suspended = false
        return desired
    }

    fun reset() { previous = null; previousAnimated = null; suspended = true }

    companion object {
        /** Max original state blend420ms, settled invisibly on the native render thread. */
        const val STATIC_SETTLE_STEPS = 27
        const val STATIC_STEP_SECONDS = 1f / 60f
    }
}
