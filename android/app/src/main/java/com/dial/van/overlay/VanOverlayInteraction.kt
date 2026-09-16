package com.dial.van.overlay

/** UI presentation is deliberately orthogonal to VAN activity/health/speech. */
enum class VanOverlayPresentation {
    FULL_FLOATING,
    WORKBOARD_COMPACT,
    WORKBOARD_EXPANDED,
    WORKBOARD_MAXIMIZED,
    MINIMIZED,
    DOCKED,
}

enum class VanQuickControlsState { HIDDEN, VISIBLE }

data class VanOverlayUiState(
    val presentation: VanOverlayPresentation = VanOverlayPresentation.FULL_FLOATING,
    val quickControls: VanQuickControlsState = VanQuickControlsState.HIDDEN,
    val dragging: Boolean = false,
    val dismissTargetVisible: Boolean = false,
    val dismissTargetArmed: Boolean = false,
    val xPx: Int = 0,
    val yPx: Int = 0,
)

sealed interface VanGestureEvent {
    data object SingleTap : VanGestureEvent
    data object DoubleTap : VanGestureEvent
    data object LongPress : VanGestureEvent
    data class DragStart(val screenX: Float, val screenY: Float) : VanGestureEvent
    data class DragDelta(val dx: Float, val dy: Float) : VanGestureEvent
    data class DragEnd(val screenX: Float, val screenY: Float) : VanGestureEvent
}

sealed interface VanOverlayEffect {
    data object OpenCommandCentre : VanOverlayEffect
    data object OpenChat : VanOverlayEffect
    data object BeginVoice : VanOverlayEffect
    data object CloseOverlay : VanOverlayEffect
}

data class VanOverlayReduction(
    val state: VanOverlayUiState,
    val effect: VanOverlayEffect? = null,
)

/** Pure reducer used by service code and unit tests. */
object VanOverlayReducer {
    fun onVanTapped(state: VanOverlayUiState): VanOverlayUiState = when (state.presentation) {
        VanOverlayPresentation.FULL_FLOATING -> state.copy(
            presentation = VanOverlayPresentation.WORKBOARD_COMPACT,
            quickControls = VanQuickControlsState.HIDDEN,
        )

        VanOverlayPresentation.WORKBOARD_COMPACT,
        VanOverlayPresentation.WORKBOARD_EXPANDED,
        VanOverlayPresentation.WORKBOARD_MAXIMIZED,
        -> state.copy(
            presentation = VanOverlayPresentation.FULL_FLOATING,
            quickControls = VanQuickControlsState.HIDDEN,
        )

        VanOverlayPresentation.MINIMIZED,
        VanOverlayPresentation.DOCKED,
        -> state.copy(
            presentation = VanOverlayPresentation.FULL_FLOATING,
            quickControls = VanQuickControlsState.HIDDEN,
        )
    }

    fun onGesture(state: VanOverlayUiState, event: VanGestureEvent): VanOverlayReduction = when (event) {
        VanGestureEvent.SingleTap -> VanOverlayReduction(onVanTapped(state))
        VanGestureEvent.DoubleTap -> VanOverlayReduction(
            state.copy(quickControls = VanQuickControlsState.HIDDEN),
            VanOverlayEffect.OpenCommandCentre,
        )
        VanGestureEvent.LongPress -> VanOverlayReduction(
            state.copy(quickControls = VanQuickControlsState.VISIBLE),
        )
        is VanGestureEvent.DragStart -> VanOverlayReduction(
            state.copy(
                dragging = true,
                dismissTargetVisible = true,
                quickControls = VanQuickControlsState.HIDDEN,
            ),
        )
        is VanGestureEvent.DragDelta -> VanOverlayReduction(
            state.copy(
                xPx = state.xPx + event.dx.toInt(),
                yPx = state.yPx + event.dy.toInt(),
            ),
        )
        is VanGestureEvent.DragEnd -> VanOverlayReduction(
            state.copy(
                dragging = false,
                dismissTargetVisible = false,
                dismissTargetArmed = false,
            ),
            effect = if (state.dismissTargetArmed) VanOverlayEffect.CloseOverlay else null,
        )
    }

    fun showQuickControls(state: VanOverlayUiState) = state.copy(
        quickControls = VanQuickControlsState.VISIBLE,
    )

    fun hideQuickControls(state: VanOverlayUiState) = state.copy(
        quickControls = VanQuickControlsState.HIDDEN,
    )

    fun minimize(state: VanOverlayUiState) = state.copy(
        presentation = VanOverlayPresentation.MINIMIZED,
        quickControls = VanQuickControlsState.HIDDEN,
    )

    fun dock(state: VanOverlayUiState) = state.copy(
        presentation = VanOverlayPresentation.DOCKED,
        quickControls = VanQuickControlsState.HIDDEN,
    )

    fun expand(state: VanOverlayUiState) = state.copy(
        presentation = VanOverlayPresentation.WORKBOARD_EXPANDED,
        quickControls = VanQuickControlsState.HIDDEN,
    )

    fun maximize(state: VanOverlayUiState) = state.copy(
        presentation = VanOverlayPresentation.WORKBOARD_MAXIMIZED,
        quickControls = VanQuickControlsState.HIDDEN,
    )

    fun compact(state: VanOverlayUiState) = state.copy(
        presentation = VanOverlayPresentation.WORKBOARD_COMPACT,
        quickControls = VanQuickControlsState.HIDDEN,
    )

    fun armDismiss(state: VanOverlayUiState, armed: Boolean) = state.copy(
        dismissTargetArmed = armed,
    )
}
