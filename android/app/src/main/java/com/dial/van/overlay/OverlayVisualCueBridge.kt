package com.dial.van.overlay

import com.dial.van.visual.VanEmbodimentReducer
import com.dial.van.visual.VanLiveVisualState

/**
 * Device-only presentation→animation bridge.
 *
 * The foreground service remains a WindowManager/lifecycle owner. This adapter
 * translates confirmed overlay presentation transitions into the existing reducer
 * instead of letting the service own character semantics or renderable components.
 */
internal object OverlayVisualCueBridge {
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
