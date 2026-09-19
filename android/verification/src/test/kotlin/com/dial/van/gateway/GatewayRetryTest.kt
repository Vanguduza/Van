package com.dial.van.gateway

import kotlin.random.Random
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * P3-AND-001 — no retry, no backoff and no circuit breaker anywhere in the Android client.
 *
 * On a phone that means the first request after a tunnel drop fails, the owner taps again,
 * that fails, and VAN looks broken — while a gateway that is briefly unreachable, which is
 * the normal condition of a self-hosted service on a home connection, is indistinguishable
 * from one that is down.
 */
class GatewayRetryTest {

    @Test
    fun `a transport failure is retried`() {
        assertEquals(
            RetryVerdict.RETRY,
            GatewayRetryPolicy.verdict(attempt = 0, status = null, transportFailed = true),
        )
    }

    @Test
    fun `an answer is not a failure`() {
        // Retrying a 409 is how one command becomes two, and retrying a 401 is how a
        // revoked device hammers the gateway.
        for (status in GatewayRetryPolicy.TERMINAL_STATUS) {
            assertEquals(
                RetryVerdict.GIVE_UP,
                GatewayRetryPolicy.verdict(0, status, transportFailed = false),
                status.toString(),
            )
        }
    }

    @Test
    fun `the server's own try-later codes are retried`() {
        for (status in GatewayRetryPolicy.RETRYABLE_STATUS) {
            assertEquals(
                RetryVerdict.RETRY,
                GatewayRetryPolicy.verdict(0, status, transportFailed = false),
                status.toString(),
            )
        }
    }

    @Test
    fun `nothing is both an answer and a try-later`() {
        // The retry decision is an allowlist, so TERMINAL_STATUS is a second, explicit
        // statement of intent rather than the thing that does the work. A code that ends up
        // in both sets is therefore silent: it would be retried, and the deny list that
        // says otherwise would keep reading as though it were not.
        assertEquals(
            emptySet(),
            GatewayRetryPolicy.TERMINAL_STATUS intersect GatewayRetryPolicy.RETRYABLE_STATUS,
        )
    }

    @Test
    fun `a success is not retried`() {
        assertEquals(RetryVerdict.GIVE_UP, GatewayRetryPolicy.verdict(0, 200, false))
    }

    @Test
    fun `retries are bounded`() {
        assertEquals(
            RetryVerdict.GIVE_UP,
            GatewayRetryPolicy.verdict(
                GatewayRetryPolicy.MAX_ATTEMPTS - 1, null, transportFailed = true,
            ),
        )
    }

    @Test
    fun `the backoff grows and stops growing`() {
        // The window is the promise; the draw inside it is random on purpose, so asserting
        // on draws would be asserting on the random number generator.
        val windows = (0 until 10).map(GatewayRetryPolicy::backoffWindowMillis)
        assertEquals(GatewayRetryPolicy.BASE_DELAY_MS, windows[0])
        assertEquals(GatewayRetryPolicy.BASE_DELAY_MS * 2, windows[1])
        assertTrue(windows.zipWithNext().all { (a, b) -> b >= a }, "$windows")
        assertTrue(windows.all { it <= GatewayRetryPolicy.MAX_DELAY_MS }, "$windows")
        assertEquals(GatewayRetryPolicy.MAX_DELAY_MS, windows.last())
        // A large attempt index must not shift the window off the end of a Long and wrap
        // negative: a negative delay is an instant retry, which is the herd this prevents.
        assertEquals(GatewayRetryPolicy.MAX_DELAY_MS, GatewayRetryPolicy.backoffWindowMillis(4_000))
    }

    @Test
    fun `every draw falls inside its window`() {
        for (attempt in 0 until 8) {
            val window = GatewayRetryPolicy.backoffWindowMillis(attempt)
            for (seed in 0 until 50) {
                val delay = GatewayRetryPolicy.delayMillis(attempt, Random(seed))
                assertTrue(delay in 0..window, "attempt=$attempt seed=$seed delay=$delay")
            }
        }
    }

    @Test
    fun `jitter actually decorrelates callers`() {
        // Every screen refreshes on the same tick, so a gateway that comes back finds every
        // pending request arriving in the same millisecond.
        val draws = (0 until 200).map { GatewayRetryPolicy.delayMillis(3, Random(it)) }.toSet()
        assertTrue(draws.size > 50, "only ${draws.size} distinct delays")
    }

    @Test
    fun `the breaker opens after sustained failure and closes on success`() {
        var now = 0L
        val breaker = GatewayCircuitBreaker(failureThreshold = 3, openForMillis = 1_000) { now }
        assertTrue(breaker.allow())
        repeat(2) { breaker.recordFailure() }
        assertTrue(breaker.allow(), "opened too early")
        breaker.recordFailure()
        assertFalse(breaker.allow())
        assertEquals(CircuitState.OPEN, breaker.state())

        now += 1_000
        assertEquals(CircuitState.HALF_OPEN, breaker.state())
        assertTrue(breaker.allow(), "never lets anything through again")

        breaker.recordSuccess()
        assertEquals(CircuitState.CLOSED, breaker.state())
        assertEquals(0, breaker.failures())
    }

    @Test
    fun `an intermittent failure does not open the breaker`() {
        var now = 0L
        val breaker = GatewayCircuitBreaker(failureThreshold = 3, openForMillis = 1_000) { now }
        repeat(10) {
            breaker.recordFailure()
            breaker.recordFailure()
            breaker.recordSuccess()
            now += 100
        }
        assertEquals(CircuitState.CLOSED, breaker.state())
    }
}
