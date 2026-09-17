package com.dial.van.visual

/** Status topology used by the interim Canvas/owner-art renderers. */
enum class VanRingStyle {
    NONE,
    PROGRESS,
    DOTS,
    DASHED,
    PULSE,
    DOUBLE,
}

enum class VanMood {
    CALM,
    ALERT,
    CONCERNED,
    PLEASED,
    MUTED,
}

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

/**
 * Character/status palette.
 *
 * `dim` is intentionally locked to 1.0. Owner device verification proved that whole-character
 * alpha attenuation made VAN read as glass. Degraded/offline truth is now carried by desaturation,
 * status copy and the semantic aura instead; skin, hair, eyes and jacket remain optically solid.
 */
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
        private const val SOLID = 1f

        private fun palette(
            accent: Long,
            ring: VanRingStyle,
            desaturation: Float,
            glow: Float,
            mood: VanMood,
            label: String,
        ) = VanStatusPalette(
            accent = VanColors.of(accent),
            ringStyle = ring,
            desaturation = desaturation,
            dim = SOLID,
            glow = glow,
            mood = mood,
            label = label,
        )

        fun forState(state: VanDurableState): VanStatusPalette = when (state) {
            VanDurableState.OFFLINE -> palette(SLATE, VanRingStyle.DASHED, 0.78f, 0f, VanMood.MUTED, "Offline")
            VanDurableState.SLEEPING -> palette(INDIGO, VanRingStyle.NONE, 0.45f, 0.10f, VanMood.MUTED, "Sleeping")
            VanDurableState.CONNECTING -> palette(CYAN_SOFT, VanRingStyle.PROGRESS, 0.25f, 0.25f, VanMood.CALM, "Connecting")
            VanDurableState.IDLE -> palette(CYAN, VanRingStyle.NONE, 0f, 0.30f, VanMood.CALM, "Ready")
            VanDurableState.ATTENTIVE -> palette(CYAN, VanRingStyle.PULSE, 0f, 0.38f, VanMood.ALERT, "Attentive")
            VanDurableState.LISTENING -> palette(CYAN, VanRingStyle.PROGRESS, 0f, 0.42f, VanMood.ALERT, "Listening")
            VanDurableState.THINKING -> palette(CYAN, VanRingStyle.DOTS, 0f, 0.32f, VanMood.CALM, "Thinking")
            VanDurableState.SEARCHING -> palette(CYAN, VanRingStyle.DOTS, 0f, 0.32f, VanMood.ALERT, "Searching")
            VanDurableState.WORKING -> palette(CYAN, VanRingStyle.PROGRESS, 0f, 0.35f, VanMood.CALM, "Working")
            VanDurableState.DELEGATING -> palette(CYAN, VanRingStyle.DOTS, 0f, 0.35f, VanMood.CALM, "Delegating")
            VanDurableState.SPEAKING -> palette(CYAN, VanRingStyle.NONE, 0f, 0.40f, VanMood.PLEASED, "Speaking")
            VanDurableState.WAITING -> palette(AMBER_SOFT, VanRingStyle.DOTS, 0.10f, 0.22f, VanMood.CALM, "Waiting")
            VanDurableState.WAITING_FOR_OWNER -> palette(AMBER_SOFT, VanRingStyle.PULSE, 0.10f, 0.30f, VanMood.ALERT, "Needs you")
            VanDurableState.DEGRADED -> palette(AMBER, VanRingStyle.DASHED, 0.45f, 0.15f, VanMood.CONCERNED, "Degraded")
            VanDurableState.WARNING -> palette(ORANGE, VanRingStyle.DOUBLE, 0.15f, 0.28f, VanMood.CONCERNED, "Warning")
            VanDurableState.ERROR -> palette(RED, VanRingStyle.DOUBLE, 0.25f, 0.28f, VanMood.CONCERNED, "Error")
            VanDurableState.SUCCESS -> palette(GREEN, VanRingStyle.PROGRESS, 0f, 0.35f, VanMood.PLEASED, "Done")
            VanDurableState.URGENT -> palette(CRIMSON, VanRingStyle.PULSE, 0f, 0.34f, VanMood.ALERT, "Urgent")
        }
    }
}
