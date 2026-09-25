package com.dial.van.visual

import kotlin.math.PI
import kotlin.math.sin

/**
 * Renderer-agnostic continuous body motion.
 *
 * Owner-art poses cannot articulate internal joints like Rive, so this transform deliberately uses
 * several asynchronous harmonics to keep the visible character alive. Amplitudes are strong enough
 * to read on a phone but remain below mascot/bounce territory. Board presentation never enters this
 * model; only presence and time do, so opening a workboard cannot freeze or replace VAN's activity.
 */
/**
 * P4-VIS-004 — `headCounterDeg` used to sit here and is gone.
 *
 * It was computed on every frame and consumed by nothing. The only production caller of
 * this sampler is [VanOwnerArtAvatar], which renders an owner-supplied bitmap: a bitmap has
 * no separable head, so there was nothing to counter-rotate. The procedural Canvas
 * character *does* have a separable head, but it already carries its own head motion inside
 * `VanScene` (`headBob` and `actionHeadDrop`), so wiring this value in there would have
 * created a second, parallel source of head motion beside the one that already works —
 * which is the duplication pattern this audit kept finding rather than a fix for it.
 *
 * So it is deleted. If a renderer with a separable head and no head motion of its own ever
 * ships, this is a four-line function to write against that renderer's actual rig.
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
                offsetXDp = state.attentionX.coerceIn(-1f, 1f) * 0.45f,
                offsetYDp = 0f,
                rotationDeg = state.attentionX.coerceIn(-1f, 1f) * 0.12f,
                scale = 1f,
            )
        }

        val p = wrap01(phase)
        val profile = profile(state.durableState)
        val hover = sin(TAU * p)
        val breath = sin(TAU * (p * 1.31f) + 0.73f)
        val drift = sin(TAU * (p * 0.57f) + 1.61f)
        val settle = sin(TAU * (p * 2.17f) + 0.24f)
        val attentionX = state.attentionX.coerceIn(-1f, 1f)
        val attentionY = state.attentionY.coerceIn(-1f, 1f)

        // Critical states become tenser, never violently shaky.
        val alertTension = if (profile.alertTension > 0f) {
            settle * profile.alertTension * (0.30f + 0.70f * state.urgency.coerceIn(0f, 1f))
        } else {
            0f
        }

        val y = hover * profile.bobDp + breath * profile.breathLiftDp + attentionY * 0.30f
        val rotation = drift * profile.swayDeg + attentionX * profile.attentionTurnDeg + alertTension

        return VanCharacterMotionFrame(
            offsetXDp = attentionX * profile.attentionLeanDp + drift * profile.driftXDp + alertTension * 0.35f,
            offsetYDp = y,
            rotationDeg = rotation,
            scale = 1f + breath * profile.breathScale,
        )
    }

    private data class Profile(
        val bobDp: Float,
        val breathLiftDp: Float,
        val driftXDp: Float,
        val swayDeg: Float,
        val breathScale: Float,
        val attentionLeanDp: Float,
        val attentionTurnDeg: Float,
        val alertTension: Float,
    )

    private fun profile(state: VanDurableState): Profile = when (state) {
        VanDurableState.SLEEPING -> Profile(0.75f, 0.38f, 0.16f, 0.24f, 0.0035f, 0.18f, 0.18f, 0f)
        // Owner direction (2026-09-25): offline VAN is subdued, not frozen. At a 0.42 dp bob
        // over six seconds he read on the S24 as a still picture, which says "broken", not
        // "can't reach home". He breathes like a quiet idle; the slate aura says offline.
        VanDurableState.OFFLINE -> Profile(1.15f, 0.46f, 0.30f, 0.46f, 0.0052f, 0.45f, 0.40f, 0f)
        VanDurableState.IDLE,
        VanDurableState.WAITING,
        -> Profile(1.65f, 0.52f, 0.42f, 0.62f, 0.0065f, 0.55f, 0.48f, 0f)

        VanDurableState.ATTENTIVE,
        VanDurableState.LISTENING,
        -> Profile(1.20f, 0.44f, 0.30f, 0.48f, 0.0052f, 1.05f, 0.82f, 0f)

        VanDurableState.THINKING,
        VanDurableState.CONNECTING,
        -> Profile(0.92f, 0.42f, 0.52f, 0.72f, 0.0055f, 0.62f, 0.58f, 0f)

        VanDurableState.SEARCHING,
        -> Profile(1.10f, 0.46f, 0.72f, 0.82f, 0.0058f, 0.82f, 0.78f, 0f)

        VanDurableState.WORKING,
        VanDurableState.DELEGATING,
        -> Profile(1.32f, 0.50f, 0.48f, 0.62f, 0.0062f, 0.68f, 0.58f, 0f)

        VanDurableState.SPEAKING -> Profile(1.05f, 0.48f, 0.36f, 0.54f, 0.0058f, 0.78f, 0.68f, 0f)
        VanDurableState.WAITING_FOR_OWNER -> Profile(0.82f, 0.34f, 0.24f, 0.38f, 0.0040f, 0.62f, 0.55f, 0f)
        VanDurableState.SUCCESS -> Profile(1.48f, 0.55f, 0.46f, 0.72f, 0.0070f, 0.68f, 0.58f, 0f)
        VanDurableState.DEGRADED -> Profile(0.70f, 0.30f, 0.20f, 0.28f, 0.0032f, 0.42f, 0.38f, 0.10f)
        VanDurableState.WARNING -> Profile(0.88f, 0.34f, 0.24f, 0.36f, 0.0038f, 0.55f, 0.48f, 0.18f)
        VanDurableState.ERROR -> Profile(0.72f, 0.30f, 0.20f, 0.30f, 0.0032f, 0.48f, 0.42f, 0.24f)
        VanDurableState.URGENT -> Profile(0.95f, 0.36f, 0.28f, 0.42f, 0.0042f, 0.62f, 0.54f, 0.30f)
    }

    internal fun wrap01(value: Float): Float {
        val mod = value % 1f
        return if (mod < 0f) mod + 1f else mod
    }
}
