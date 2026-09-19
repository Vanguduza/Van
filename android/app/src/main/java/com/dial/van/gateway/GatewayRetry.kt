package com.dial.van.gateway

import kotlin.math.min
import kotlin.random.Random

/**
 * Bounded backoff and a circuit breaker for the gateway client.
 *
 * P3-AND-001. `VanGatewayClient` used raw `HttpURLConnection` with no retry, no backoff and
 * no circuit breaker. On a phone that means the first request after a tunnel drop fails, the
 * owner taps again, that fails, and VAN looks broken — while a gateway that is briefly
 * unreachable, which is the normal condition of a self-hosted service on a home connection,
 * is indistinguishable from one that is down.
 *
 * Two rules the naive version gets wrong.
 *
 * **Not everything is retryable.** A 401 will be 401 again; a 409 idempotency conflict
 * means the command already exists and retrying is how one command becomes two. Only
 * transport failures and the server's own "try later" codes are retried.
 *
 * **Jitter is not decoration.** Every screen in the app refreshes on the same tick, so a
 * gateway that comes back finds every pending request arriving in the same millisecond.
 * Full jitter spreads them.
 */
enum class RetryVerdict { RETRY, GIVE_UP }

object GatewayRetryPolicy {
    const val MAX_ATTEMPTS = 4
    const val BASE_DELAY_MS = 250L
    const val MAX_DELAY_MS = 8_000L

    /** HTTP codes where the server is telling us to come back. */
    val RETRYABLE_STATUS = setOf(408, 429, 500, 502, 503, 504)

    /**
     * Codes that are answers, not failures. Retrying a 409 is how one command becomes two,
     * and retrying a 401 is how a revoked device hammers the gateway.
     */
    val TERMINAL_STATUS = setOf(400, 401, 403, 404, 409, 410, 422)

    fun verdict(attempt: Int, status: Int?, transportFailed: Boolean): RetryVerdict {
        if (attempt + 1 >= MAX_ATTEMPTS) return RetryVerdict.GIVE_UP
        if (transportFailed) return RetryVerdict.RETRY
        if (status == null) return RetryVerdict.GIVE_UP
        if (status in TERMINAL_STATUS) return RetryVerdict.GIVE_UP
        return if (status in RETRYABLE_STATUS) RetryVerdict.RETRY else RetryVerdict.GIVE_UP
    }

    /**
     * The ceiling the jittered draw is taken from: doubling per attempt, capped.
     *
     * Exposed separately because it is the part that is a promise. The draw is random by
     * design, so a test that asserts on draws is asserting on the random number generator;
     * the *window* is what the policy actually guarantees, and it is what callers reason
     * about when they ask how long a failing gateway will be retried for.
     */
    fun backoffWindowMillis(attempt: Int): Long =
        min(BASE_DELAY_MS shl attempt.coerceIn(0, 16), MAX_DELAY_MS)

    /**
     * Full jitter: a uniform draw from the whole window rather than the window plus a
     * wobble. It is what actually decorrelates callers, and the cost — an occasional very
     * short wait — is one extra request, not a thundering herd.
     */
    fun delayMillis(attempt: Int, random: Random = Random.Default): Long =
        random.nextLong(0, backoffWindowMillis(attempt) + 1)
}

enum class CircuitState {
    /** Requests go through. */
    CLOSED,

    /** The gateway has failed enough times that trying is wasting the owner's battery. */
    OPEN,

    /** One request is allowed through to find out whether it came back. */
    HALF_OPEN,
}

/**
 * Stops VAN hammering a gateway that is down.
 *
 * Deliberately *not* a hard block on the owner's own action: `allow()` reports whether the
 * circuit is open and the caller decides. A refresh loop should honour it; the owner
 * pressing send should not be told "no" by a client-side heuristic about a server they can
 * see is up.
 */
class GatewayCircuitBreaker(
    private val failureThreshold: Int = 5,
    private val openForMillis: Long = 30_000L,
    private val now: () -> Long = System::currentTimeMillis,
) {
    private var consecutiveFailures = 0
    private var openedAtMillis: Long? = null

    fun state(): CircuitState {
        val opened = openedAtMillis ?: return CircuitState.CLOSED
        return if (now() - opened >= openForMillis) CircuitState.HALF_OPEN else CircuitState.OPEN
    }

    /** Whether a *background* request should be attempted now. */
    fun allow(): Boolean = state() != CircuitState.OPEN

    fun recordSuccess() {
        consecutiveFailures = 0
        openedAtMillis = null
    }

    fun recordFailure() {
        consecutiveFailures += 1
        if (consecutiveFailures >= failureThreshold && openedAtMillis == null) {
            openedAtMillis = now()
        }
    }

    /** For the health surface: how many consecutive failures the breaker has seen. */
    fun failures(): Int = consecutiveFailures

    fun reset() {
        consecutiveFailures = 0
        openedAtMillis = null
    }
}
