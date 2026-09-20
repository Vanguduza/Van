package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Rev 1.5 §§0B, 20.6-20.10, 20.14 — the decisions a failover is made of.
 *
 * The case §0B names explicitly is the one worth reading first: two carriers over one
 * ingress are not redundancy, and a status that says otherwise tells the owner they are
 * covered for the failure that is going to happen.
 */
class TransportSupervisorTest {

    private fun path(
        id: String,
        route: String,
        cls: PathClass = PathClass.A_REALTIME,
        priority: Int = 100,
    ) = TransportPathDescriptor(
        pathId = id,
        pathClass = cls,
        protocol = if (cls == PathClass.A_REALTIME) "WSS" else "HTTP2",
        endpoint = "/v1/session",
        routeId = route,
        priority = priority,
    )

    private fun healthy() = PathObservation(
        connected = true, rttMs = 40, lastRxAgeMs = 500,
        consecutiveWriteFailures = 0, recentDisconnects = 0,
    )

    @Test
    fun `two carriers on one route are protocol diversity, not route diversity`() {
        val supervisor = TransportSupervisor(
            listOf(
                path("primary", "oracle-ingress"),
                path("fallback", "oracle-ingress", PathClass.B_STREAMING),
            ),
        )
        supervisor.observe("primary", healthy(), interactionActive = true)
        supervisor.observe("fallback", healthy(), interactionActive = true)

        val verdict = supervisor.continuity()
        assertEquals(SupervisorState.SINGLE_PATH, verdict.state)
        assertFalse(verdict.routeRedundant)
        assertTrue(verdict.reason.contains("protocol diversity"))
    }

    @Test
    fun `two independent routes are multipath`() {
        val supervisor = TransportSupervisor(
            listOf(path("primary", "oracle-ingress"), path("fallback", "alternate-relay")),
        )
        supervisor.observe("primary", healthy(), interactionActive = true)
        supervisor.observe("fallback", healthy(), interactionActive = true)

        val verdict = supervisor.continuity()
        assertEquals(SupervisorState.MULTIPATH_HEALTHY, verdict.state)
        assertTrue(verdict.routeRedundant)
    }

    @Test
    fun `a failed path does not count towards redundancy`() {
        val supervisor = TransportSupervisor(
            listOf(path("primary", "oracle-ingress"), path("fallback", "alternate-relay")),
        )
        supervisor.observe("primary", healthy(), interactionActive = true)
        supervisor.observe(
            "fallback",
            healthy().copy(connected = false),
            interactionActive = true,
        )
        assertEquals(SupervisorState.SINGLE_PATH, supervisor.continuity().state)
    }

    @Test
    fun `no usable path reports offline rather than a degraded socket`() {
        val supervisor = TransportSupervisor(listOf(path("primary", "oracle-ingress")))
        supervisor.observe("primary", healthy().copy(connected = false), interactionActive = true)
        val verdict = supervisor.continuity()
        assertEquals(SupervisorState.OFFLINE_LOCAL, verdict.state)
        assertTrue(verdict.reason.contains("local capabilities carry on"))
    }

    @Test
    fun `a write that failed outranks every timing signal`() {
        // A slow link is still carrying messages. A failed write is not.
        val supervisor = TransportSupervisor(listOf(path("primary", "oracle-ingress")))
        val health = supervisor.observe(
            "primary",
            healthy().copy(consecutiveWriteFailures = 2, rttMs = 5, lastRxAgeMs = 0),
            interactionActive = true,
        )
        assertEquals(PathHealth.FAILED, health)
    }

    @Test
    fun `two missed heartbeats make a path suspect`() {
        val supervisor = TransportSupervisor(listOf(path("primary", "oracle-ingress")))
        val health = supervisor.observe(
            "primary",
            healthy().copy(lastRxAgeMs = HeartbeatPolicy.ACTIVE_INTERVAL_MS * 2),
            interactionActive = true,
        )
        assertEquals(PathHealth.SUSPECT, health)
    }

    @Test
    fun `the idle cadence does not call a background path suspect for being quiet`() {
        // §20.8 — VAN must not wake the radio every two seconds in the background, so the
        // same silence means different things depending on what the owner is doing.
        val supervisor = TransportSupervisor(listOf(path("primary", "oracle-ingress")))
        val quiet = healthy().copy(lastRxAgeMs = HeartbeatPolicy.ACTIVE_INTERVAL_MS * 3)
        // Three beats of silence while the owner is waiting is suspect — prepare a
        // failover — and four is failed. The same six seconds in the background is one
        // idle beat, which is nothing at all.
        assertEquals(PathHealth.SUSPECT, supervisor.observe("p", quiet, interactionActive = true))
        assertEquals(PathHealth.HEALTHY, supervisor.observe("p", quiet, interactionActive = false))
        assertEquals(
            PathHealth.FAILED,
            supervisor.observe(
                "p",
                healthy().copy(lastRxAgeMs = HeartbeatPolicy.ACTIVE_INTERVAL_MS * 4),
                interactionActive = true,
            ),
        )
    }

    @Test
    fun `a healthy active path needs no failover`() {
        val supervisor = TransportSupervisor(
            listOf(path("primary", "oracle-ingress"), path("fallback", "alternate-relay")),
        )
        supervisor.observe("primary", healthy(), interactionActive = true)
        supervisor.observe("fallback", healthy(), interactionActive = true)
        assertNull(supervisor.failoverTarget("primary"))
    }

    @Test
    fun `failover prefers a different road to the one that just broke`() {
        val supervisor = TransportSupervisor(
            listOf(
                path("primary", "oracle-ingress"),
                path("same-road", "oracle-ingress", PathClass.B_STREAMING, priority = 10),
                path("other-road", "alternate-relay", PathClass.B_STREAMING, priority = 50),
            ),
        )
        supervisor.observe("primary", healthy().copy(connected = false), interactionActive = true)
        supervisor.observe("same-road", healthy(), interactionActive = true)
        supervisor.observe("other-road", healthy(), interactionActive = true)

        val target = supervisor.failoverTarget("primary")
        assertEquals(
            "other-road",
            target?.pathId,
            "failing over onto the road that just broke is the failover that changes nothing",
        )
    }

    @Test
    fun `a suspect path prepares a failover and a failed one commits it`() {
        val supervisor = TransportSupervisor(listOf(path("primary", "oracle-ingress")))
        assertEquals(
            SupervisorState.FAILOVER_PREPARING,
            supervisor.stateDuringFailover(PathHealth.SUSPECT),
        )
        assertEquals(
            SupervisorState.FAILOVER_COMMITTING,
            supervisor.stateDuringFailover(PathHealth.FAILED),
        )
    }
}

class OutboxPolicyTest {

    @Test
    fun `irreversible and approval-bearing work is never stored`() {
        // §20.14 — a queue flushing after an hour offline must not be able to perform one.
        assertEquals(CommandStorability.NEVER_STORE, OutboxPolicy.classify("A5", false))
        assertEquals(CommandStorability.NEVER_STORE, OutboxPolicy.classify("A4", false))
    }

    @Test
    fun `anything that depends on the moment is reconfirmed rather than replayed`() {
        val classified = OutboxPolicy.classify("A1", requiresLiveOwnerContext = true)
        assertEquals(CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT, classified)
        assertFalse(classified.mayReplaySilently)
    }

    @Test
    fun `ordinary work replays silently`() {
        assertTrue(OutboxPolicy.classify("A1", false).mayReplaySilently)
        assertTrue(OutboxPolicy.classify("A3", false).mayReplaySilently)
    }

    @Test
    fun `live owner context outranks a low action class`() {
        // Otherwise "read that back to me" would be stored as ordinary work and replayed an
        // hour later, when it refers to something the owner has long since moved past.
        assertEquals(
            CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT,
            OutboxPolicy.classify("A3", requiresLiveOwnerContext = true),
        )
    }
}
