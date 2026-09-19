package com.dial.van.onboarding

/**
 * What first run has to establish, and whether it actually has.
 *
 * P1-AND-002. Onboarding covered overlay, notifications, the listener, the microphone and
 * the biometric — and not pairing, which lives at Home > Connections. So a new owner
 * finished onboarding, landed on a dashboard where every call returned 401, and had no way
 * to know that the thing they had not done was several taps away under a menu they had
 * never opened. The most important step was the one that was missing.
 *
 * Worse, steps advanced on `startActivity`. Opening the Android settings screen counted as
 * granting the permission: an owner could tap through the whole flow, grant nothing, and be
 * told they were set. Nothing re-checked on resume either, so a permission granted in
 * settings and then returned from still showed as pending.
 *
 * This file is the plan and the advancement rule. It takes the *observed* grant state and
 * says where the owner is, so the flow cannot advance on an intent that was merely fired.
 *
 * Pure Kotlin, executed in `android/verification`.
 */
enum class OnboardingStep(val id: String) {
    /** Without this VAN cannot talk to its gateway at all, so it is first. */
    PAIRING("pairing"),
    OVERLAY("overlay"),
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
    val paired: Boolean = false,
    val overlayGranted: Boolean = false,
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
     * install. Everything else is required, and pairing most of all: without it every
     * screen is an error message.
     */
    val SKIPPABLE = setOf(OnboardingStep.NOTIFICATION_LISTENER, OnboardingStep.BIOMETRIC)

    fun satisfied(step: OnboardingStep, grants: OnboardingGrants): Boolean = when (step) {
        OnboardingStep.PAIRING -> grants.paired
        OnboardingStep.OVERLAY -> grants.overlayGranted
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
     * The required steps must be satisfied outright. An owner cannot skip past pairing, and
     * the "you're set" screen cannot appear while VAN cannot reach its gateway — which is
     * exactly what used to happen.
     */
    fun mayComplete(grants: OnboardingGrants): Boolean =
        OnboardingStep.entries
            .filter { it != OnboardingStep.DONE && it !in SKIPPABLE }
            .all { satisfied(it, grants) }

    fun view(step: OnboardingStep, grants: OnboardingGrants): OnboardingStepView = when (step) {
        OnboardingStep.PAIRING -> OnboardingStepView(
            step,
            "Pair this phone with your gateway",
            "Until this is done VAN cannot reach anything: every screen will show an error. " +
                "You will need the pairing code from the machine running the gateway.",
            "Pair now",
            satisfied(step, grants), skippable = false,
        )
        OnboardingStep.OVERLAY -> OnboardingStepView(
            step,
            "Let VAN appear over other apps",
            "This is how the floating assistant reaches you while you are using something else.",
            "Allow",
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
            "You're set",
            "VAN is paired and can reach your gateway.",
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
