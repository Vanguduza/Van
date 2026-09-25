package com.dial.van.onboarding

/**
 * What VAN asks the owner for, in VAN's own words, and when.
 *
 * Owner direction (2026-09-25): no setup checklist and no pairing screen. The phone is
 * provisioned by the installer (ADR-RB-026), so there is nothing for the owner to set up
 * before they meet VAN. Each Android permission is asked for by VAN himself, on his own
 * screen, the first time a feature actually needs it — never as a list up front.
 *
 * The rules that survive from the old onboarding (P1-AND-002) are kept here, because they
 * were right: whether a permission is held is read from the device, never inferred from an
 * intent having been fired, and "not now" is remembered so VAN does not nag.
 *
 * Pure Kotlin, executed in `android/verification`.
 */
enum class VanPermission(val id: String) {
    /** Floating VAN: drawing over other apps. */
    OVERLAY("overlay"),

    /** The ongoing notification while VAN runs, and the one that says something needs you. */
    NOTIFICATIONS("notifications"),

    /** Speaking to VAN. */
    MICROPHONE("microphone"),

    /** Accessibility window metadata, so Floating VAN moves off the keyboard and full-screen apps. */
    DISPLAY_AWARENESS("display_awareness"),

    /** Optional: reading notifications. */
    NOTIFICATION_LISTENER("notification_listener"),

    /** Approving anything VAN cannot undo. */
    BIOMETRIC("biometric"),
    ;

    companion object {
        fun fromId(id: String?): VanPermission? = entries.firstOrNull { it.id == id }
    }
}

/** One ask, as VAN says it. */
data class VanAsk(
    val permission: VanPermission,
    /** VAN speaking, first person. */
    val line: String,
    /** What happens when the owner agrees: a system prompt, or a settings page VAN points at. */
    val allow: String,
    val later: String,
    /** Whether the owner will be taken to a system settings page rather than shown a prompt. */
    val opensSettings: Boolean,
)

/** Why VAN is asking now. The owner reaching for a feature is not the same as VAN starting. */
enum class AskTrigger {
    /** VAN needs this to do something by himself (float, notify). A "not now" holds. */
    VAN_NEEDS_IT,

    /** The owner just tried to use the feature (tapped Voice, pressed Enable). Always asks. */
    OWNER_REACHED_FOR_IT,
}

object VanAskPlan {

    /** Asked for while VAN starts floating, in this order, and only while missing. */
    val FLOATING_NEEDS: List<VanPermission> = listOf(VanPermission.OVERLAY, VanPermission.NOTIFICATIONS)

    fun ask(permission: VanPermission): VanAsk = when (permission) {
        VanPermission.OVERLAY -> VanAsk(
            permission,
            "Can I float over your other apps? That's how I stay with you when you leave this screen.",
            "Sure", "Not now", opensSettings = true,
        )
        VanPermission.NOTIFICATIONS -> VanAsk(
            permission,
            "Can I send you notifications? I'll keep one quiet one while I'm running, and tap you on the shoulder when something needs you.",
            "Sure", "Not now", opensSettings = false,
        )
        VanPermission.MICROPHONE -> VanAsk(
            permission,
            "I need your microphone to hear you. I only listen when you ask me to, or when you say my name.",
            "Sure", "Not now", opensSettings = false,
        )
        VanPermission.DISPLAY_AWARENESS -> VanAsk(
            permission,
            "Turn on my screen awareness and I'll move out of the way of your keyboard and full-screen apps. I only see where windows are, never what's in them.",
            "Show me where", "Not now", opensSettings = true,
        )
        VanPermission.NOTIFICATION_LISTENER -> VanAsk(
            permission,
            "If you let me read your notifications I can notice things for you. Codes and passwords are stripped before anything leaves the phone. This one's optional.",
            "Show me where", "No thanks", opensSettings = true,
        )
        VanPermission.BIOMETRIC -> VanAsk(
            permission,
            "Before I do anything I can't undo, I'll want your fingerprint or face. This phone doesn't have one set up yet, so until it does I'll refuse those things rather than guess.",
            "Set it up", "Later", opensSettings = true,
        )
    }

    /**
     * Whether VAN should put the ask screen up now.
     *
     * Never when the grant is already held — read from the device, not remembered. A "not
     * now" silences only VAN's own asks: when the owner reaches for the feature themselves,
     * VAN asks again, because refusing to ask would leave the button doing nothing.
     */
    fun shouldAsk(granted: Boolean, declined: Boolean, trigger: AskTrigger): Boolean = when {
        granted -> false
        trigger == AskTrigger.OWNER_REACHED_FOR_IT -> true
        else -> !declined
    }

    /** The first permission VAN still needs in order to float, or null when it can. */
    fun nextFloatingAsk(granted: (VanPermission) -> Boolean, declined: (VanPermission) -> Boolean): VanPermission? =
        FLOATING_NEEDS.firstOrNull { shouldAsk(granted(it), declined(it), AskTrigger.VAN_NEEDS_IT) }

    /**
     * What VAN says as he appears.
     *
     * [connected] is whether this phone has been provisioned to its gateway. When it has
     * not, VAN says so in his own words — there is no pairing step for the owner to take;
     * setting the phone up is the installer's job.
     */
    fun greeting(firstLaunch: Boolean, connected: Boolean): String {
        val hello = if (firstLaunch) "Hi, I'm VAN." else "Welcome back."
        return if (connected) hello else "$hello I can't reach my home base yet, so I'll be limited until I'm set up."
    }
}
