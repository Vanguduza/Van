package com.dial.van.voice

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Establish cleanup before returning the job, including cancellation before dispatch starts. */
object SpeakerCaptureJob {
    /** Stopping AudioRecord and releasing its native handle happen on different threads. */
    suspend fun awaitReleased(released: () -> Boolean, timeoutMs: Long = 2_000): Boolean =
        withTimeoutOrNull(timeoutMs) {
            while (!released()) delay(20)
            true
        } == true

    fun launch(scope: CoroutineScope, release: suspend () -> Unit, capture: suspend () -> Unit): Job =
        scope.launch(start = CoroutineStart.UNDISPATCHED) {
            try {
                coroutineContext.ensureActive()
                capture()
            } finally {
                withContext(NonCancellable) { release() }
            }
        }
}
