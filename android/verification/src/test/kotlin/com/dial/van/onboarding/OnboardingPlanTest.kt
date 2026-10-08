package com.dial.van.onboarding

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/** Permission grants remain observed OS state; enrollment never appears as an owner step. */
class OnboardingPlanTest {

    private val nothing = OnboardingGrants()

    private val everything = OnboardingGrants(
        overlayGranted = true,
        displayAwarenessEnabled = true,
        notificationsGranted = true,
        notificationListenerEnabled = true,
        microphoneGranted = true,
        biometricAvailable = true,
    )

    @Test
    fun `permission review never requests pairing or connection data`() {
        assertEquals(OnboardingStep.OVERLAY, OnboardingPlan.currentStep(nothing))
        for (step in OnboardingStep.entries) {
            val view = OnboardingPlan.view(step, nothing)
            val words = (view.title + " " + view.body + " " + view.button).lowercase()
            assertFalse(words.contains("pairing"), words)
            assertFalse(words.contains("pair now"), words)
            assertFalse(words.contains("gateway address"), words)
        }
    }

    @Test
    fun `opening a settings screen is not granting a permission`() {
        // The finding, as a test: the step advances on the observed grant, and there is no
        // parameter here through which a fired intent could advance it.
        var grants = nothing
        assertEquals(OnboardingStep.OVERLAY, OnboardingPlan.currentStep(grants))
        assertEquals(OnboardingStep.OVERLAY, OnboardingPlan.currentStep(grants))
        grants = grants.copy(overlayGranted = true)
        assertEquals(OnboardingStep.DISPLAY_AWARENESS, OnboardingPlan.currentStep(grants))
        grants = grants.copy(displayAwarenessEnabled = true)
        assertEquals(OnboardingStep.NOTIFICATIONS, OnboardingPlan.currentStep(grants))
    }

    @Test
    fun `a permission granted in settings shows up when the owner comes back`() {
        // Derived from grants rather than remembered in a step index, so nothing re-checks
        // on resume is no longer possible: there is nothing to re-check against.
        val before = everything.copy(microphoneGranted = false)
        assertEquals(OnboardingStep.MICROPHONE, OnboardingPlan.currentStep(before))
        assertEquals(OnboardingStep.DONE, OnboardingPlan.currentStep(before.copy(microphoneGranted = true)))
    }

    @Test
    fun `the whole flow walks in order and ends`() {
        var grants = nothing
        val walked = mutableListOf<OnboardingStep>()
        repeat(OnboardingStep.entries.size + 2) {
            val step = OnboardingPlan.currentStep(grants)
            if (step == OnboardingStep.DONE) return@repeat
            walked += step
            grants = grant(grants, step)
        }
        assertEquals(
            OnboardingStep.entries.filter { it != OnboardingStep.DONE },
            walked,
        )
        assertEquals(OnboardingStep.DONE, OnboardingPlan.currentStep(grants))
        assertTrue(OnboardingPlan.mayComplete(grants))
    }

    @Test
    fun `the optional steps are the two the owner cannot simply grant`() {
        // The notification listener is genuinely optional; the biometric depends on
        // hardware the owner cannot install. Nothing else is.
        assertEquals(
            setOf(OnboardingStep.NOTIFICATION_LISTENER, OnboardingStep.BIOMETRIC),
            OnboardingPlan.SKIPPABLE,
        )
        val skipped = setOf(OnboardingStep.NOTIFICATION_LISTENER, OnboardingStep.BIOMETRIC)
        val partial = everything.copy(notificationListenerEnabled = false, biometricAvailable = false)
        assertEquals(OnboardingStep.DONE, OnboardingPlan.currentStep(partial, skipped))
        assertTrue(OnboardingPlan.mayComplete(partial))
        assertTrue(OnboardingPlan.blockers(partial).isEmpty())
    }

    @Test
    fun `a required step cannot be skipped by asking to skip it`() {
        val partial = everything.copy(overlayGranted = false)
        assertEquals(
            OnboardingStep.OVERLAY,
            OnboardingPlan.currentStep(partial, skipped = setOf(OnboardingStep.OVERLAY)),
        )
        assertFalse(OnboardingPlan.mayComplete(partial))
    }

    @Test
    fun `display awareness is required for obstruction-safe floating VAN`() {
        val partial = everything.copy(displayAwarenessEnabled = false)
        assertEquals(OnboardingStep.DISPLAY_AWARENESS, OnboardingPlan.currentStep(partial))
        assertFalse(OnboardingPlan.mayComplete(partial))
        assertTrue(OnboardingPlan.blockers(partial).contains(OnboardingStep.DISPLAY_AWARENESS))
    }

    @Test
    fun `a phone too old to have the permission is not blocked on granting it`() {
        // POST_NOTIFICATIONS does not exist below Android 13, and a step that can never be
        // satisfied is a flow that can never finish.
        val old = everything.copy(notificationsGranted = false, notificationsNotApplicable = true)
        assertTrue(OnboardingPlan.satisfied(OnboardingStep.NOTIFICATIONS, old))
        assertTrue(OnboardingPlan.mayComplete(old))
    }

    @Test
    fun `every step has words for the owner and none of them is an enum`() {
        for (step in OnboardingStep.entries) {
            val view = OnboardingPlan.view(step, nothing)
            assertEquals(step, view.step)
            assertTrue(view.title.isNotBlank(), step.name)
            assertTrue(view.body.length > 24, "${step.name}: ${view.body}")
            assertTrue(view.button.isNotBlank(), step.name)
            assertFalse(view.title.contains('_'), view.title)
            assertFalse(view.body.contains('_'), view.body)
            assertEquals(step in OnboardingPlan.SKIPPABLE, view.skippable, step.name)
        }
    }

    private fun grant(grants: OnboardingGrants, step: OnboardingStep): OnboardingGrants = when (step) {
        OnboardingStep.OVERLAY -> grants.copy(overlayGranted = true)
        OnboardingStep.DISPLAY_AWARENESS -> grants.copy(displayAwarenessEnabled = true)
        OnboardingStep.NOTIFICATIONS -> grants.copy(notificationsGranted = true)
        OnboardingStep.NOTIFICATION_LISTENER -> grants.copy(notificationListenerEnabled = true)
        OnboardingStep.MICROPHONE -> grants.copy(microphoneGranted = true)
        OnboardingStep.BIOMETRIC -> grants.copy(biometricAvailable = true)
        OnboardingStep.DONE -> grants
    }
}
