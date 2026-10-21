package com.dial.van.onboarding

/**
 * Observed OS grants for the optional permission review.
 * Installer enrollment is independent and is never an owner-facing setup step.
 * Opening Android settings cannot satisfy a permission.
 */
enum class OnboardingStep(val id: String) {
    OVERLAY("overlay"),
    DISPLAY_AWARENESS("display_awareness"),
    NOTIFICATIONS("notifications"),
    NOTIFICATION_LISTENER("notification_listener"),
    MICROPHONE("microphone"),
    BIOMETRIC("biometric"),
    DONE("done"),
}

/**
 * What the device actually reports. Every field is a *grant*, never an intent that was
 * fired: that distinction is the finding.
 */
data class OnboardingGrants(
    val overlayGranted: Boolean = false,
    val displayAwarenessEnabled: Boolean = false,
    val notificationsGranted: Boolean = false,
    val notificationListenerEnabled: Boolean = false,
    val microphoneGranted: Boolean = false,
    val biometricAvailable: Boolean = false,
    /** True on Android below 13, where POST_NOTIFICATIONS does not exist to grant. */
    val notificationsNotApplicable: Boolean = false,
)

data class OnboardingStepView(
    val step: OnboardingStep,
    val title: String,
    val body: String,
    val button: String,
    val satisfied: Boolean,
    /** Whether the owner may move past this step without satisfying it. */
    val skippable: Boolean,
)

object OnboardingPlan {

    /**
     * Steps the owner may pass without granting.
     *
     * The notification listener is genuinely optional — VAN works without reading
     * notifications, it just knows less. The biometric depends on hardware the owner cannot
     * install. The remaining grants are required to complete this permission review.
     * The Command Centre remains accessible independently.
     */
    val SKIPPABLE = setOf(OnboardingStep.NOTIFICATION_LISTENER, OnboardingStep.BIOMETRIC)

    fun satisfied(step: OnboardingStep, grants: OnboardingGrants): Boolean = when (step) {
        OnboardingStep.OVERLAY -> grants.overlayGranted
        OnboardingStep.DISPLAY_AWARENESS -> grants.displayAwarenessEnabled
        OnboardingStep.NOTIFICATIONS ->
            grants.notificationsGranted || grants.notificationsNotApplicable
        OnboardingStep.NOTIFICATION_LISTENER -> grants.notificationListenerEnabled
        OnboardingStep.MICROPHONE -> grants.microphoneGranted
        OnboardingStep.BIOMETRIC -> grants.biometricAvailable
        OnboardingStep.DONE -> true
    }

    /**
     * Where the owner is, from what the device reports.
     *
     * Derived rather than remembered. A step index in `remember` is what let the flow
     * advance on an intent and then disagree with reality when the owner came back from
     * settings; recomputing from grants means a permission granted anywhere shows up here.
     */
    fun currentStep(grants: OnboardingGrants, skipped: Set<OnboardingStep> = emptySet()): OnboardingStep {
        for (step in OnboardingStep.entries) {
            if (step == OnboardingStep.DONE) break
            if (satisfied(step, grants)) continue
            if (step in skipped && step in SKIPPABLE) continue
            return step
        }
        return OnboardingStep.DONE
    }

    /**
     * Whether onboarding may finish.
     *
     * Required OS permissions must be observed before this review is marked complete.
     * This result does not establish enrollment, connectivity or provider readiness.
     */
    fun mayComplete(grants: OnboardingGrants): Boolean =
        OnboardingStep.entries
            .filter { it != OnboardingStep.DONE && it !in SKIPPABLE }
            .all { satisfied(it, grants) }

    fun view(step: OnboardingStep, grants: OnboardingGrants): OnboardingStepView = when (step) {
        OnboardingStep.OVERLAY -> OnboardingStepView(
            step,
            "Let VAN appear over other apps",
            "This is how the floating assistant reaches you while you are using something else.",
            "Allow",
            satisfied(step, grants), skippable = false,
        )
        OnboardingStep.DISPLAY_AWARENESS -> OnboardingStepView(
            step,
            "Let VAN understand screen obstruction",
            "VAN uses Android Accessibility window metadata to detect the keyboard and immersive full-screen apps, so the floating assistant can move or pause instead of blocking what you are doing. VAN does not read accessibility text.",
            "Open accessibility settings",
            satisfied(step, grants), skippable = false,
        )
        OnboardingStep.NOTIFICATIONS -> OnboardingStepView(
            step,
            "Let VAN send you notifications",
            "VAN uses one ongoing notification while the assistant is running, and sends you " +
                "one when something needs you.",
            "Allow",
            satisfied(step, grants), skippable = false,
        )
        OnboardingStep.NOTIFICATION_LISTENER -> OnboardingStepView(
            step,
            "Let VAN read your notifications",
            "Optional. It lets VAN notice things you would otherwise have to tell it. " +
                "Codes and passwords are removed before anything leaves the phone.",
            "Open settings",
            satisfied(step, grants), skippable = true,
        )
        OnboardingStep.MICROPHONE -> OnboardingStepView(
            step,
            "Let VAN hear you",
            "Without this you can still type to VAN, but you cannot speak to it.",
            "Allow",
            satisfied(step, grants), skippable = false,
        )
        OnboardingStep.BIOMETRIC -> OnboardingStepView(
            step,
            "Set up approval",
            "VAN asks for your fingerprint or face before anything it cannot undo. " +
                "If this device has none, VAN will refuse those actions rather than guess.",
            "Continue",
            satisfied(step, grants), skippable = true,
        )
        OnboardingStep.DONE -> OnboardingStepView(
            step,
            "Permission review complete",
            "Android confirms the required grants for the features in this review. " +
                "Connection readiness is shown separately in VAN.",
            "Enter Command Centre",
            satisfied = true, skippable = false,
        )
    }

    /** What is still missing, for the screen that has to say why it cannot finish. */
    fun blockers(grants: OnboardingGrants): List<OnboardingStep> =
        OnboardingStep.entries.filter {
            it != OnboardingStep.DONE && it !in SKIPPABLE && !satisfied(it, grants)
        }
}
