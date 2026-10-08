package com.dial.van.status

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.withTimeoutOrNull

/** One independently observed dashboard source; a failed refresh preserves its age. */
data class OwnerSourceRead<T>(
    val value: T? = null,
    val observedAtMs: Long? = null,
    val unavailable: Boolean = false,
) {
    val hasObservation: Boolean get() = value != null && observedAtMs != null

    fun ageMs(nowMs: Long): Long? = observedAtMs?.let { (nowMs - it).coerceAtLeast(0) }
}

suspend fun <T> readOwnerSource(
    previous: OwnerSourceRead<T> = OwnerSourceRead(),
    clock: () -> Long = System::currentTimeMillis,
    timeoutMs: Long = 5_000L,
    read: suspend () -> T,
): OwnerSourceRead<T> = try {
    val value = withTimeoutOrNull(timeoutMs) { read() }
    if (value == null) previous.copy(unavailable = true)
    else OwnerSourceRead(value = value, observedAtMs = clock())
} catch (cancelled: CancellationException) {
    throw cancelled
} catch (_: Exception) {
    // No invented empty data or new observation timestamp after a failed request.
    previous.copy(unavailable = true)
}
