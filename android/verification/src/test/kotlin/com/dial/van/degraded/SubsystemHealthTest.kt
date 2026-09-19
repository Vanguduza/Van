package com.dial.van.degraded

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P3-AND-004 / P3-AND-005.
 *
 * Five subsystems were in `defaultSubsystems()` and nothing ever wrote them, so all five
 * reported WORKING regardless of reality. These tests exist to make the reverse impossible:
 * every one of the five has to be derivable from a device fact, and the all-denied device
 * must come back broken across the board.
 */
class SubsystemHealthTest {

    private val denied = SubsystemSignals()

    private val granted = SubsystemSignals(
        overlayPermissionGranted = true,
        overlayRunning = true,
        notificationListenerConnected = true,
        microphonePermissionGranted = true,
        speechRecognitionAvailable = true,
        strongBiometricAvailable = true,
        biometricEnrolled = true,
    )

    private fun verdict(id: String, signals: SubsystemSignals): SubsystemVerdict =
        SubsystemHealth.evaluate(signals).single { it.id == id }

    @Test
    fun `a phone that has granted nothing does not report five healthy subsystems`() {
        // This is the finding, stated as a test: the old code returned WORKING for all five
        // of these on exactly this device.
        val verdicts = SubsystemHealth.evaluate(denied)
        assertEquals(
            setOf("overlay", "queue", "notifications", "voice", "biometric"),
            verdicts.map { it.id }.toSet(),
        )
        val broken = verdicts.filter { it.status == SubsystemStatus.BROKEN }.map { it.id }
        assertEquals(listOf("overlay", "notifications", "voice", "biometric"), broken)
    }

    @Test
    fun `a phone that has granted everything reports everything working`() {
        assertTrue(SubsystemHealth.evaluate(granted).all { it.status == SubsystemStatus.WORKING })
    }

    @Test
    fun `each subsystem follows its own signal`() {
        assertEquals(
            SubsystemStatus.BROKEN,
            verdict("overlay", granted.copy(overlayPermissionGranted = false)).status,
        )
        assertEquals(
            SubsystemStatus.BROKEN,
            verdict("notifications", granted.copy(notificationListenerConnected = false)).status,
        )
        assertEquals(
            SubsystemStatus.BROKEN,
            verdict("voice", granted.copy(microphonePermissionGranted = false)).status,
        )
        assertEquals(
            SubsystemStatus.BROKEN,
            verdict("voice", granted.copy(speechRecognitionAvailable = false)).status,
        )
        assertEquals(
            SubsystemStatus.BROKEN,
            verdict("biometric", granted.copy(strongBiometricAvailable = false)).status,
        )
        assertEquals(
            SubsystemStatus.BROKEN,
            verdict("biometric", granted.copy(biometricEnrolled = false)).status,
        )
    }

    @Test
    fun `an overlay the owner turned off is not a fault`() {
        // A health page that calls the owner's own choice a fault is lying in the other
        // direction, and an owner who is told they broke something they meant to do stops
        // trusting the page.
        val stopped = verdict("overlay", granted.copy(overlayRunning = false))
        assertEquals(SubsystemStatus.WONT_DO, stopped.status)
        assertEquals(RestoreAction.RESTART_OVERLAY, stopped.restoreAction)
    }

    @Test
    fun `working offline is not a broken queue`() {
        val queued = verdict("queue", granted.copy(queuedCommands = 3))
        assertEquals(SubsystemStatus.WORKING, queued.status)
        assertTrue(queued.detail.contains("3"), queued.detail)
    }

    @Test
    fun `a queue that cannot send is broken and a queue that will not drain is broken`() {
        val failing = verdict(
            "queue",
            granted.copy(queuedCommands = 2, queueReplayFailures = SubsystemHealth.REPLAY_FAILURE_THRESHOLD),
        )
        assertEquals(SubsystemStatus.BROKEN, failing.status)
        assertEquals(RestoreAction.RETRY_CONNECTION, failing.restoreAction)

        val backlog = verdict(
            "queue",
            granted.copy(queuedCommands = SubsystemHealth.QUEUE_BACKLOG_THRESHOLD),
        )
        assertEquals(SubsystemStatus.BROKEN, backlog.status)
        assertEquals(RestoreAction.CLEAR_QUEUE, backlog.restoreAction)
    }

    @Test
    fun `every broken subsystem carries something the owner can do`() {
        for (v in SubsystemHealth.evaluate(denied)) {
            if (v.status == SubsystemStatus.WORKING) continue
            assertTrue(
                SubsystemHealth.isActionable(v.restoreAction),
                "${v.id} is ${v.status} with no restore action",
            )
        }
    }

    @Test
    fun `every restore action renders words a person can read`() {
        // P3-AND-005: all seven values existed and no screen rendered any of them. If a new
        // value is added and forgotten, this fails rather than putting an enum name on a
        // button.
        for (action in RestoreAction.entries) {
            val label = SubsystemHealth.restoreLabel(action)
            val sentence = SubsystemHealth.restoreSentence(action)
            if (action == RestoreAction.NONE) {
                assertEquals("", label)
                assertFalse(SubsystemHealth.isActionable(action))
                continue
            }
            assertTrue(label.isNotBlank(), "$action has no label")
            assertTrue(sentence.isNotBlank(), "$action has no sentence")
            assertFalse(label.contains('_'), "$action label is an enum name: $label")
            assertFalse(label.drop(1).any { it.isUpperCase() }, "$action shouts: $label")
        }
    }

    @Test
    fun `no owner-facing detail is written in VAN's own vocabulary`() {
        val details = SubsystemHealth.evaluate(denied).map { it.detail }
        for (detail in details) {
            assertFalse(detail.contains('_'), detail)
            assertTrue(detail.length > 12, detail)
        }
    }
}
