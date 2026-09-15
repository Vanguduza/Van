package com.dial.van.visual

/**
 * Status presentation rules for the interim Canvas character.
 *
 * Identity colours (hair, skin, eyes, visor, jacket) are locked by
 * `docs/VAN_CHARACTER_VISUAL_IDENTITY.md`; only the *status* layer varies, and only within
 * the bounds the acceptance matrix allows: truthful muting when offline or degraded,
 * urgency cues without frantic motion or excessive glow.
 */
enum class VanRingStyle {
    /** No status ring — nominal presence. */
    NONE,

    /** Continuous sweeping arc: listening, working, connecting. */
    PROGRESS,

    /** Orbiting dots: thinking, searching, delegating, waiting. */
    DOTS,

    /** Broken arc: something is unavailable and Van says so. */
    DASHED,

    /** Slow breathing ring: attention wanted from the owner. */
    PULSE,

    /** Twin arcs plus caution chevron: warning, error, urgent. */
    DOUBLE,
}

/** Coarse mood used by the face rig (brows and mouth curve). */
enum class VanMood {
    CALM,
    ALERT,
    CONCERNED,
    PLEASED,
    MUTED,
}

/**
 * Owner-facing state copy, taken from the captions on the owner design sheet.
 *
 * §16 of the glassmorphic spec forbids any state from relying on colour alone, so every state
 * carries words as well as an accent and a silhouette cue.
 */
object VanCaptions {
    fun forState(state: VanDurableState): String = when (state) {
        VanDurableState.OFFLINE -> "Offline — I'll catch up."
        VanDurableState.CONNECTING -> "Connecting…"
        VanDurableState.IDLE -> "Ready when you are."
        VanDurableState.ATTENTIVE -> "You have new updates."
        VanDurableState.LISTENING -> "I'm listening…"
        VanDurableState.THINKING -> "Let me think…"
        VanDurableState.SEARCHING -> "Checking sources…"
        VanDurableState.WORKING -> "Working on it…"
        VanDurableState.DELEGATING -> "Handing this to Hermes…"
        VanDurableState.SPEAKING -> "Here's what I found."
        VanDurableState.WAITING -> "Waiting on a reply…"
        VanDurableState.WAITING_FOR_OWNER -> "I need your approval for this action."
        VanDurableState.DEGRADED -> "Some subsystems are down."
        VanDurableState.WARNING -> "I need your approval for this action."
        VanDurableState.ERROR -> "That didn't work."
        VanDurableState.SUCCESS -> "All done!"
        VanDurableState.URGENT -> "This needs you now."
        VanDurableState.SLEEPING -> "Sleeping."
    }
}

data class VanStatusPalette(
    val accent: Int,
    val ringStyle: VanRingStyle,
    val desaturation: Float,
    val dim: Float,
    val glow: Float,
    val mood: VanMood,
    val label: String,
) {
    companion object {
        private const val CYAN = 0xFF00E5FFL
        private const val CYAN_SOFT = 0xFF4DD0E1L
        private const val SLATE = 0xFF78909CL
        private const val INDIGO = 0xFF5C6BC0L
        private const val AMBER = 0xFFFFB300L
        private const val AMBER_SOFT = 0xFFFFD54FL
        private const val ORANGE = 0xFFFF9100L
        private const val RED = 0xFFFF5252L
        private const val CRIMSON = 0xFFFF1744L
        private const val GREEN = 0xFF69F0AEL

        fun forState(state: VanDurableState): VanStatusPalette = when (state) {
            VanDurableState.OFFLINE -> VanStatusPalette(
                accent = VanColors.of(SLATE),
                ringStyle = VanRingStyle.DASHED,
                desaturation = 0.78f,
                dim = 0.55f,
                glow = 0f,
                mood = VanMood.MUTED,
                label = "Offline",
            )
            VanDurableState.SLEEPING -> VanStatusPalette(
                accent = VanColors.of(INDIGO),
                ringStyle = VanRingStyle.NONE,
                desaturation = 0.45f,
                dim = 0.70f,
                glow = 0.1f,
                mood = VanMood.MUTED,
                label = "Sleeping",
            )
            VanDurableState.CONNECTING -> VanStatusPalette(
                accent = VanColors.of(CYAN_SOFT),
                ringStyle = VanRingStyle.PROGRESS,
                desaturation = 0.25f,
                dim = 0.85f,
                glow = 0.25f,
                mood = VanMood.CALM,
                label = "Connecting",
            )
            VanDurableState.IDLE -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.NONE,
                desaturation = 0f,
                dim = 1f,
                glow = 0.30f,
                mood = VanMood.CALM,
                label = "Ready",
            )
            VanDurableState.ATTENTIVE -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.PULSE,
                desaturation = 0f,
                dim = 1f,
                glow = 0.38f,
                mood = VanMood.ALERT,
                label = "Attentive",
            )
            VanDurableState.LISTENING -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.PROGRESS,
                desaturation = 0f,
                dim = 1f,
                glow = 0.42f,
                mood = VanMood.ALERT,
                label = "Listening",
            )
            VanDurableState.THINKING -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.DOTS,
                desaturation = 0f,
                dim = 1f,
                glow = 0.32f,
                mood = VanMood.CALM,
                label = "Thinking",
            )
            VanDurableState.SEARCHING -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.DOTS,
                desaturation = 0f,
                dim = 1f,
                glow = 0.32f,
                mood = VanMood.ALERT,
                label = "Searching",
            )
            VanDurableState.WORKING -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.PROGRESS,
                desaturation = 0f,
                dim = 1f,
                glow = 0.35f,
                mood = VanMood.CALM,
                label = "Working",
            )
            VanDurableState.DELEGATING -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.DOTS,
                desaturation = 0f,
                dim = 1f,
                glow = 0.35f,
                mood = VanMood.CALM,
                label = "Delegating",
            )
            VanDurableState.SPEAKING -> VanStatusPalette(
                accent = VanColors.of(CYAN),
                ringStyle = VanRingStyle.NONE,
                desaturation = 0f,
                dim = 1f,
                glow = 0.40f,
                mood = VanMood.PLEASED,
                label = "Speaking",
            )
            VanDurableState.WAITING -> VanStatusPalette(
                accent = VanColors.of(AMBER_SOFT),
                ringStyle = VanRingStyle.DOTS,
                desaturation = 0.10f,
                dim = 0.95f,
                glow = 0.22f,
                mood = VanMood.CALM,
                label = "Waiting",
            )
            VanDurableState.WAITING_FOR_OWNER -> VanStatusPalette(
                accent = VanColors.of(AMBER_SOFT),
                ringStyle = VanRingStyle.PULSE,
                desaturation = 0.10f,
                dim = 1f,
                glow = 0.30f,
                mood = VanMood.ALERT,
                label = "Needs you",
            )
            VanDurableState.DEGRADED -> VanStatusPalette(
                accent = VanColors.of(AMBER),
                ringStyle = VanRingStyle.DASHED,
                desaturation = 0.45f,
                dim = 0.85f,
                glow = 0.15f,
                mood = VanMood.CONCERNED,
                label = "Degraded",
            )
            VanDurableState.WARNING -> VanStatusPalette(
                accent = VanColors.of(ORANGE),
                ringStyle = VanRingStyle.DOUBLE,
                desaturation = 0.15f,
                dim = 1f,
                glow = 0.28f,
                mood = VanMood.CONCERNED,
                label = "Warning",
            )
            VanDurableState.ERROR -> VanStatusPalette(
                accent = VanColors.of(RED),
                ringStyle = VanRingStyle.DOUBLE,
                desaturation = 0.25f,
                dim = 1f,
                glow = 0.28f,
                mood = VanMood.CONCERNED,
                label = "Error",
            )
            VanDurableState.SUCCESS -> VanStatusPalette(
                accent = VanColors.of(GREEN),
                ringStyle = VanRingStyle.PROGRESS,
                desaturation = 0f,
                dim = 1f,
                glow = 0.35f,
                mood = VanMood.PLEASED,
                label = "Done",
            )
            VanDurableState.URGENT -> VanStatusPalette(
                accent = VanColors.of(CRIMSON),
                ringStyle = VanRingStyle.PULSE,
                desaturation = 0f,
                dim = 1f,
                glow = 0.34f,
                mood = VanMood.ALERT,
                label = "Urgent",
            )
        }
    }
}
