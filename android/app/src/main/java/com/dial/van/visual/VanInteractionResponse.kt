package com.dial.van.visual

/** Pixel-independent, bounded physical response. No user/task state is encoded here. */
data class VanInteractionResponse(val leanDegrees: Float = 0f, val liftDp: Float = 0f)

object VanInteractionResponsePolicy {
    fun drag(dxPx: Float, dyPx: Float, density: Float): VanInteractionResponse {
        if (!dxPx.isFinite() || !dyPx.isFinite() || !density.isFinite() || density <= 0f) return VanInteractionResponse()
        return VanInteractionResponse((-dxPx / density * .10f).coerceIn(-2.5f, 2.5f),
            (-dyPx / density * .04f).coerceIn(-1.25f, 1.25f))
    }
    fun compatible(state: VanVisualState): Boolean = state.actionCode !in setOf(
        VanFiniteAction.POINT_TARGET.code, VanFiniteAction.POINT_LEFT.code, VanFiniteAction.POINT_RIGHT.code,
        VanFiniteAction.POINT_UP.code, VanFiniteAction.POINT_DOWN.code) && state.contextCode !in setOf(18,26)
}
