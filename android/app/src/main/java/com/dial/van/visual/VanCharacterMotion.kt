package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.sin

/**
 * Small renderer-agnostic motion cues that keep a static owner-art pose physically alive.
 *
 * The procedural Canvas rig already has articulated bob/blink/gaze/mouth motion, and the future
 * Rive artboard owns its internal animation. Owner bitmap poses need a restrained whole-character
 * transform so the floating bot never becomes a frozen sticker while the field moves around it.
 *
 * Values are intentionally tiny. The field carries semantic energy; VAN remains the stable anchor.
 */
data class VanCharacterMotionFrame(
    val offsetXDp: Float,
    val offsetYDp: Float,
    val rotationDeg: Float,
    val scale: Float,
)

object VanCharacterMotion {
    private const val TAU = (2.0 * PI).toFloat()

    fun sample(
        state: VanVisualState,
        phase: Float,
        reducedMotion: Boolean,
    ): VanCharacterMotionFrame {
        if (reducedMotion) {
            return VanCharacterMotionFrame(
                offsetXDp = state.attentionX.coerceIn(-1f, 1f) * 0.35f,
                offsetYDp = 0f,
                rotationDeg = 0f,
                scale = 1f,
            )
        }

        val p = wrap01(phase)
        val profile = profile(state.durableState)
        val fundamental = sin(TAU * p)
        val secondary = sin(TAU * 2f * p + 0.73f)
        val tertiary = sin(TAU * 3f * p + 1.61f)
        val attentionX = state.attentionX.coerceIn(-1f, 1f)
        val attentionY = state.attentionY.coerceIn(-1f, 1f)

        val alertTremor = if (profile.alertTremor > 0f) {
            tertiary * profile.alertTremor * (0.35f + 0.65f * state.urgency.coerceIn(0f, 1f))
        } else {
            0f
        }

        return VanCharacterMotionFrame(
            offsetXDp = attentionX * profile.attentionLeanDp + secondary * profile.driftXDp + alertTremor,
            offsetYDp = fundamental * profile.bobDp + attentionY * 0.25f,
            rotationDeg = fundamental * profile.swayDeg + attentionX * profile.attentionTurnDeg + alertTremor * 0.20f,
            scale = 1f + secondary * profile.breathScale,
        )
    }

    private data class Profile(
        val bobDp: Float,
        val driftXDp: Float,
        val swayDeg: Float,
        val breathScale: Float,
        val attentionLeanDp: Float,
        val attentionTurnDeg: Float,
        val alertTremor: Float,
    )

    private fun profile(state: VanDurableState): Profile = when (state) {
        VanDurableState.SLEEPING -> Profile(0.45f, 0.10f, 0.20f, 0.0025f, 0.20f, 0.20f, 0f)
        VanDurableState.OFFLINE -> Profile(0.30f, 0.08f, 0.12f, 0.0015f, 0.10f, 0.10f, 0f)
        VanDurableState.IDLE,
        VanDurableState.WAITING,
        -> Profile(0.85f, 0.24f, 0.42f, 0.0040f, 0.45f, 0.38f, 0f)

        VanDurableState.ATTENTIVE,
        VanDurableState.LISTENING,
        -> Profile(0.72f, 0.18f, 0.34f, 0.0035f, 0.85f, 0.65f, 0f)

        VanDurableState.THINKING,
        VanDurableState.CONNECTING,
        -> Profile(0.62f, 0.36f, 0.56f, 0.0038f, 0.55f, 0.48f, 0f)

        VanDurableState.SEARCHING,
        VanDurableState.WORKING,
        VanDurableState.DELEGATING,
        -> Profile(0.92f, 0.34f, 0.48f, 0.0045f, 0.55f, 0.45f, 0f)

        VanDurableState.SPEAKING -> Profile(0.70f, 0.20f, 0.36f, 0.0038f, 0.65f, 0.55f, 0f)
        VanDurableState.WAITING_FOR_OWNER -> Profile(0.48f, 0.15f, 0.28f, 0.0028f, 0.45f, 0.38f, 0f)
        VanDurableState.SUCCESS -> Profile(1.00f, 0.30f, 0.52f, 0.0050f, 0.55f, 0.45f, 0f)
        VanDurableState.DEGRADED -> Profile(0.38f, 0.10f, 0.20f, 0.0020f, 0.30f, 0.25f, 0.08f)
        VanDurableState.WARNING -> Profile(0.54f, 0.16f, 0.30f, 0.0028f, 0.45f, 0.38f, 0.16f)
        VanDurableState.ERROR -> Profile(0.44f, 0.12f, 0.24f, 0.0022f, 0.35f, 0.30f, 0.22f)
        VanDurableState.URGENT -> Profile(0.62f, 0.18f, 0.34f, 0.0030f, 0.50f, 0.42f, 0.26f)
    }

    internal fun wrap01(value: Float): Float {
        val mod = value % 1f
        return if (mod < 0f) mod + 1f else mod
    }
}
