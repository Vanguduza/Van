package com.dial.van.session

/**
 * Rev 1.5 §§0B, 20.6-20.10 — path health and failover, as a decision rather than a reflex.
 *
 * This file holds the *decisions*, not the sockets. Health scoring, when a path becomes
 * suspect, whether a failover should be prepared, and — the one §0B names explicitly —
 * whether VAN may honestly call itself multipath. Keeping that pure means it can be executed
 * in the harness, which matters because every interesting case here is a failure nobody can
 * produce on demand on a real network.
 *
 * §0B's distinction, implemented rather than described:
 *
 *     PROTOCOL_DIVERSITY   different transport mechanisms
 *     ROUTE_DIVERSITY      independently reachable ingress paths
 *
 * Two carriers over one ingress fail together. Calling that `MULTIPATH_HEALTHY` would tell
 * the owner they are covered for the failure that is actually going to happen, so it reports
 * `SINGLE_PATH` and says why.
 */
enum class PathClass { A_REALTIME, B_STREAMING, C_REPLAY_FLOOR }

enum class PathHealth {
    HEALTHY,
    SUSPECT,
    DEGRADED,
    FAILED,
    COOLDOWN;

    val usable: Boolean
        get() = this == HEALTHY || this == DEGRADED
}

enum class SupervisorState {
    STARTING,
    PRIMARY_CONNECTING,
    MULTIPATH_HEALTHY,
    SINGLE_PATH,
    FAILOVER_PREPARING,
    FAILOVER_COMMITTING,
    RECOVERING,
    STORE_AND_FORWARD,
    OFFLINE_LOCAL,
}

/** §20.6 — a carrier, and the route it traverses. */
data class TransportPathDescriptor(
    val pathId: String,
    val pathClass: PathClass,
    val protocol: String,
    val endpoint: String,
    /** Two paths sharing this are one road, whatever protocols they speak. */
    val routeId: String,
    val priority: Int = 100,
    val supportsFullDuplex: Boolean = false,
    val supportsStreamingDownlink: Boolean = false,
    val meteredAllowed: Boolean = true,
)

/** One observation of a path. */
data class PathObservation(
    val connected: Boolean,
    val rttMs: Long,
    val lastRxAgeMs: Long,
    val consecutiveWriteFailures: Int,
    val recentDisconnects: Int,
)

/**
 * §20.8 — the heartbeat cadence, which is a battery decision as much as a liveness one.
 *
 * Two seconds while the owner is waiting on something; ten to thirty when idle. §20.8 is
 * explicit that VAN must not wake the radio every two seconds permanently in the
 * background, and a supervisor that ignored that would drain the phone to watch a socket
 * nobody is using.
 */
object HeartbeatPolicy {
    const val ACTIVE_INTERVAL_MS: Long = 2_000
    const val IDLE_INTERVAL_MS: Long = 20_000
    const val MISSED_BEATS_BEFORE_SUSPECT: Int = 2

    fun intervalMs(interactionActive: Boolean): Long =
        if (interactionActive) ACTIVE_INTERVAL_MS else IDLE_INTERVAL_MS

    fun health(observation: PathObservation, interactionActive: Boolean): PathHealth {
        if (!observation.connected) return PathHealth.FAILED
        // A write that failed is not a slow link; it is a link that did not carry the
        // message, which is why this outranks every timing signal below.
        if (observation.consecutiveWriteFailures >= 2) return PathHealth.FAILED
        if (observation.consecutiveWriteFailures == 1) return PathHealth.SUSPECT

        val interval = intervalMs(interactionActive)
        val missed = observation.lastRxAgeMs / interval
        return when {
            missed >= MISSED_BEATS_BEFORE_SUSPECT * 2 -> PathHealth.FAILED
            missed >= MISSED_BEATS_BEFORE_SUSPECT -> PathHealth.SUSPECT
            observation.rttMs > 1_500 || observation.recentDisconnects >= 3 -> PathHealth.DEGRADED
            else -> PathHealth.HEALTHY
        }
    }
}

data class ContinuityVerdict(
    val state: SupervisorState,
    val reason: String,
    /** True only when two live paths traverse genuinely different routes (§20.6). */
    val routeRedundant: Boolean,
)

/**
 * The supervisor's judgement. Sockets live elsewhere; this decides what they mean.
 */
class TransportSupervisor(
    private val paths: List<TransportPathDescriptor>,
) {
    private val health = mutableMapOf<String, PathHealth>()

    fun observe(pathId: String, observation: PathObservation, interactionActive: Boolean): PathHealth {
        val verdict = HeartbeatPolicy.health(observation, interactionActive)
        health[pathId] = verdict
        return verdict
    }

    fun healthOf(pathId: String): PathHealth = health[pathId] ?: PathHealth.COOLDOWN

    fun continuity(): ContinuityVerdict {
        val usable = paths.filter { healthOf(it.pathId).usable }
        if (usable.isEmpty()) {
            return ContinuityVerdict(
                SupervisorState.OFFLINE_LOCAL,
                "no usable path: queued work waits and local capabilities carry on",
                routeRedundant = false,
            )
        }
        val routes = usable.map { it.routeId }.toSet()
        if (routes.size >= 2) {
            return ContinuityVerdict(
                SupervisorState.MULTIPATH_HEALTHY,
                "${usable.size} live paths across ${routes.size} independent routes",
                routeRedundant = true,
            )
        }
        val reason = if (usable.size >= 2) {
            "${usable.size} live paths, one route (${routes.first()}): " +
                "protocol diversity, not route diversity"
        } else {
            "one live path on route ${routes.first()}"
        }
        return ContinuityVerdict(SupervisorState.SINGLE_PATH, reason, routeRedundant = false)
    }

    /**
     * §20.10 — whether to start a failover, and to what.
     *
     * Make-before-break when the active path is merely suspect: the standby is opened and
     * resumed while the old one still carries traffic. When it has failed outright there is
     * nothing to keep, and the same transaction runs break-before-make.
     */
    fun failoverTarget(activePathId: String): TransportPathDescriptor? {
        val active = healthOf(activePathId)
        if (active == PathHealth.HEALTHY) return null
        return paths
            .filter { it.pathId != activePathId && healthOf(it.pathId).usable }
            // Prefer a different route: failing over to another carrier on the road that
            // just broke is the most common way a failover changes nothing.
            .sortedWith(
                compareByDescending<TransportPathDescriptor> {
                    it.routeId != paths.firstOrNull { p -> p.pathId == activePathId }?.routeId
                }.thenBy { it.priority },
            )
            .firstOrNull()
    }

    fun stateDuringFailover(active: PathHealth): SupervisorState = when (active) {
        PathHealth.SUSPECT, PathHealth.DEGRADED -> SupervisorState.FAILOVER_PREPARING
        PathHealth.FAILED -> SupervisorState.FAILOVER_COMMITTING
        else -> SupervisorState.SINGLE_PATH
    }
}

/**
 * §20.14 — what the local outbox may do with a command while there is no path.
 *
 * Classified before storage. A command stored first and judged later is a command that has
 * already been kept, and the queue flushing an hour later is exactly when that matters.
 */
enum class CommandStorability {
    SAFE_TO_RETRY,
    STORE_UNTIL_TTL,
    REQUIRE_RECONFIRM_ON_RECONNECT,
    NEVER_STORE;

    val mayReplaySilently: Boolean
        get() = this == SAFE_TO_RETRY || this == STORE_UNTIL_TTL
}

object OutboxPolicy {
    /**
     * Irreversible or owner-approval-bearing work is never stored, and anything whose
     * meaning depends on the moment must be reconfirmed.
     *
     * "Read that back to me" replayed an hour later is not the same request, and neither is
     * "cancel it" once the thing it referred to has finished.
     */
    fun classify(actionClass: String, requiresLiveOwnerContext: Boolean): CommandStorability = when {
        actionClass == "A5" || actionClass == "A4" -> CommandStorability.NEVER_STORE
        requiresLiveOwnerContext -> CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT
        actionClass == "A3" -> CommandStorability.STORE_UNTIL_TTL
        else -> CommandStorability.SAFE_TO_RETRY
    }
}
