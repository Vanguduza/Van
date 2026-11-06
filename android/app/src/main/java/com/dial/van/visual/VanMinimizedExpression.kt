package com.dial.van.visual

/** Readable expression hints for the existing minimized Candidate B face fallback.
 *
 * This is not the final approved Rive expression rig. It adds real local visual response
 * to the present portrait without changing the image authority or any Rive input code.
 */
enum class VanSmallMouth { NEUTRAL, SMILE, CONCERN, SPEECH }

data class VanMinimizedExpression(
    val mouth: VanSmallMouth,
    /** Outer eyebrows raised when positive, lowered/knitted when negative. */
    val browLift: Float,
    /** 0.0 relaxed, 1.0 narrowed. */
    val eyeNarrow: Float,
    val speechOpening: Float,
    val viseme: Int,
)

object VanMinimizedExpressionMap {
    fun from(state: VanVisualState): VanMinimizedExpression {
        val durable = state.durableState
        val critical = durable == VanDurableState.WARNING ||
            durable == VanDurableState.ERROR ||
            durable == VanDurableState.URGENT ||
            durable == VanDurableState.WAITING_FOR_OWNER
        val base = when (durable) {
            VanDurableState.URGENT -> VanMinimizedExpression(VanSmallMouth.CONCERN, -0.90f, 0f, 0f, 0)
            VanDurableState.ERROR, VanDurableState.WARNING ->
                VanMinimizedExpression(VanSmallMouth.CONCERN, -0.65f, 0.25f, 0f, 0)
            VanDurableState.WAITING_FOR_OWNER ->
                VanMinimizedExpression(VanSmallMouth.NEUTRAL, 0.35f, 0f, 0f, 0)
            VanDurableState.SUCCESS ->
                VanMinimizedExpression(VanSmallMouth.SMILE, 0.25f, 0.0f, 0f, 0)
            VanDurableState.ATTENTIVE, VanDurableState.LISTENING ->
                VanMinimizedExpression(VanSmallMouth.NEUTRAL, 0.3f, 0f, 0f, 0)
            VanDurableState.THINKING, VanDurableState.SEARCHING ->
                VanMinimizedExpression(VanSmallMouth.NEUTRAL, 0.15f, 0.20f, 0f, 0)
            VanDurableState.OFFLINE, VanDurableState.SLEEPING ->
                VanMinimizedExpression(VanSmallMouth.NEUTRAL, -0.2f, 0.5f, 0f, 0)
            else -> VanMinimizedExpression(VanSmallMouth.NEUTRAL, 0f, 0f, 0f, 0)
        }
        if (!critical && state.speaking) {
            return base.copy(
                mouth = VanSmallMouth.SPEECH,
                speechOpening = if (state.mouthOpen.isFinite()) state.mouthOpen.coerceIn(0f, 1f) else 0f,
                viseme = when {
                    state.viseme < 0 -> 0
                    state.viseme > 4 -> 1
                    else -> state.viseme
                },
            )
        }
        return base
    }
}
