package com.dial.van.overlay

import com.dial.van.visual.VanEmbodimentReducer
import com.dial.van.visual.VanLiveVisualState
import com.dial.van.visual.VanLiveInteractionResponse

/**
 * Device-only presentation→animation bridge.
 *
 * The foreground service remains a WindowManager/lifecycle owner. This adapter
 * translates confirmed overlay presentation transitions into the existing reducer
 * instead of letting the service own character semantics or renderable components.
 */
internal object OverlayVisualCueBridge {
    fun dragSample(dx: Float, dy: Float, density: Float) = VanLiveInteractionResponse.drag(dx,dy,density)
    fun restAfterInteraction() = VanLiveInteractionResponse.release()

    fun publishPresentationChange(
        previous: VanOverlayPresentation,
        next: VanOverlayPresentation,
    ) {
        val expanding = OverlayPresentationMotion.expanding(previous, next) ?: return
        val effect = VanEmbodimentReducer.forOverlayTransition(expanding)
        if (effect is VanEmbodimentReducer.Effect.ToAction) {
            VanLiveVisualState.action(effect.action)
        }
    }
}
