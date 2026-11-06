package com.dial.van.voice

import kotlinx.coroutines.CoroutineExceptionHandler
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.awaitCancellation
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class SpeakerCaptureJobTest {
    @Test fun cancellationImmediatelyAfterLaunchReleasesTheEstablishedReservationExactlyOnce() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        var started = 0; var released = 0
        val capture = SpeakerCaptureJob.launch(scope, release = { released++ }) {
            started++
            awaitCancellation()
        }
        assertEquals(1, started) // The body has established its cleanup before launch returns.
        capture.cancel(); capture.join(); capture.cancel()
        assertEquals(1, released)
        assertTrue(capture.isCancelled)
    }
    @Test fun anAlreadyCancelledScopeStillReleasesButNeverCaptures() = runBlocking {
        val owner = Job().also { it.cancel() }
        val scope = CoroutineScope(owner + Dispatchers.Unconfined)
        var started = 0; var released = 0
        val capture = SpeakerCaptureJob.launch(scope, release = { released++ }) { started++ }
        capture.join()
        assertEquals(0, started)
        assertEquals(1, released)
    }
    @Test fun refusedOrFailingCaptureAlsoReleasesItsReservation() = runBlocking {
        var errors = 0; var released = 0
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined + CoroutineExceptionHandler { _, _ -> errors++ })
        val capture = SpeakerCaptureJob.launch(scope, release = { released++ }) { error("capture_unavailable") }
        capture.join()
        assertEquals(1, released)
        assertEquals(1, errors)
    }
    @Test fun wakeReleaseBarrierWaitsForTheActualNativeHandleToBeReleased() = runBlocking {
        var released = false
        launch { delay(35); released = true }
        assertTrue(SpeakerCaptureJob.awaitReleased({ released }, timeoutMs = 1_000))
        assertTrue(released)
    }
    @Test fun aWedgedMicrophoneHasABoundedFailClosedReleaseBarrier() = runBlocking {
        assertEquals(false, SpeakerCaptureJob.awaitReleased({ false }, timeoutMs = 40))
    }

}
