package com.dial.van.visual

/** Local presentation choices never confer task, microphone or external action authority. */
enum class VanExpressionLevel { EXPRESSIVE, BALANCED, QUIET }
enum class VanDoubleTapAction { WORKSPACE, CHAT, NONE }

data class VanPresentationPreferences(
    val expression: VanExpressionLevel = VanExpressionLevel.EXPRESSIVE,
    val reducedMotion: Boolean = false,
    val idleOpacityPercent: Int = 100,
    val rememberDraft: Boolean = true,
    val doubleTap: VanDoubleTapAction = VanDoubleTapAction.WORKSPACE,
) {
    fun normalized() = copy(idleOpacityPercent = idleOpacityPercent.coerceIn(55, 100))
}

object VanPersonalPresentation {
    private val CRITICAL = setOf(VanDurableState.URGENT, VanDurableState.ERROR, VanDurableState.WARNING,
        VanDurableState.WAITING_FOR_OWNER, VanDurableState.OFFLINE, VanDurableState.DEGRADED)
    private val GUIDANCE = setOf(VanFiniteAction.CAUTION.code, VanFiniteAction.POINT_TARGET.code,
        VanFiniteAction.POINT_LEFT.code, VanFiniteAction.POINT_RIGHT.code,
        VanFiniteAction.POINT_UP.code, VanFiniteAction.POINT_DOWN.code)

    fun project(state: VanVisualState, preferences: VanPresentationPreferences): VanVisualState {
        if (state.durableState in CRITICAL || state.resolvedSemanticState in CRITICAL || state.actionCode in GUIDANCE) return state
        val quiet = preferences.expression == VanExpressionLevel.QUIET
        val restrainedGreeting = preferences.expression == VanExpressionLevel.BALANCED && state.actionCode == VanFiniteAction.HELLO_WAVE.code
        return if (quiet || restrainedGreeting) state.copy(actionCode = 0, contextCode = 0) else state
    }

    fun motionAllowed(state: VanVisualState, preferences: VanPresentationPreferences, visible: Boolean): Boolean =
        visible && !preferences.reducedMotion && !(preferences.expression == VanExpressionLevel.QUIET &&
            state.durableState in setOf(VanDurableState.IDLE, VanDurableState.SLEEPING) &&
            state.resolvedSemanticState !in CRITICAL && !state.speaking && !state.listening && state.actionCode == 0)

    fun opacity(state: VanVisualState, preferences: VanPresentationPreferences, passive: Boolean): Float =
        if (passive && state.durableState == VanDurableState.IDLE && state.resolvedSemanticState !in CRITICAL &&
            !state.speaking && !state.listening && state.actionCode == 0)
            preferences.normalized().idleOpacityPercent / 100f else 1f
}
