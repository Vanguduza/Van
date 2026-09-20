package com.dial.van.session

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

private fun conditions(
    interaction: Boolean = true,
    battery: Int = 80,
    charging: Boolean = false,
    metered: Boolean = false,
    dataSaver: Boolean = false,
    secondRoute: Boolean = true,
) = StandbyConditions(
    interactionActive = interaction,
    batteryPercent = battery,
    charging = charging,
    standbyIsMetered = metered,
    dataSaverEnabled = dataSaver,
    independentRouteAvailable = secondRoute,
)

/**
 * Rev 1.5 §20.9, ADR-RB-012 — the second path, and what it costs to keep it.
 */
class WarmStandbyPolicyTest {

    @Test
    fun `a spare path is held while the owner is interacting`() {
        assertEquals(StandbyRole.WARM_STANDBY, WarmStandbyPolicy.decide(conditions()).role)
    }

    @Test
    fun `an idle VAN lets the spare go cold`() {
        // §20.9 states it: "when idle, fallback may be cold to preserve battery." A
        // second authenticated socket with its own heartbeats is not free, and nothing is
        // happening that a failover would interrupt.
        val decision = WarmStandbyPolicy.decide(conditions(interaction = false))
        assertEquals(StandbyRole.COLD, decision.role)
        assertTrue(decision.reason.contains("nothing is happening"), decision.reason)
    }

    @Test
    fun `a spare on the same road is not redundancy`() {
        // §20.6. Two carriers over one ingress fail together, so holding the second open
        // costs battery and buys nothing — and reporting it as redundancy would tell the
        // owner they are covered for the failure that is actually going to happen.
        val decision = WarmStandbyPolicy.decide(conditions(secondRoute = false))
        assertEquals(StandbyRole.COLD, decision.role)
        assertTrue(decision.reason.contains("same road"), decision.reason)
    }

    @Test
    fun `a low battery closes the spare even mid-interaction`() {
        assertEquals(
            StandbyRole.COLD,
            WarmStandbyPolicy.decide(conditions(battery = 15)).role,
        )
    }

    @Test
    fun `charging pays for the spare that a low battery would not`() {
        assertEquals(
            StandbyRole.WARM_STANDBY,
            WarmStandbyPolicy.decide(conditions(battery = 15, charging = true)).role,
        )
    }

    @Test
    fun `Data Saver closes a metered spare even while charging`() {
        // Data Saver is the owner saying "do less on mobile data", and a warm standby on
        // a metered carrier is exactly the background traffic it is about. Being plugged
        // in does not make the data free.
        val decision = WarmStandbyPolicy.decide(
            conditions(metered = true, dataSaver = true, charging = true),
        )
        assertEquals(StandbyRole.COLD, decision.role)
        assertTrue(decision.reason.contains("Data Saver"), decision.reason)
    }

    @Test
    fun `Data Saver does not close an unmetered spare`() {
        assertEquals(
            StandbyRole.WARM_STANDBY,
            WarmStandbyPolicy.decide(conditions(metered = false, dataSaver = true)).role,
        )
    }

    @Test
    fun `only the authoritative path may carry a new owner message`() {
        // §20.9's third line, and the one with teeth. A standby that sent a command
        // because it happened to be connected would produce the duplicate §20.12's
        // effectively-once admission exists to reject — from VAN's own client, before the
        // Gateway ever sees it.
        assertTrue(WarmStandbyPolicy.mayCarryNewUpstream(StandbyRole.AUTHORITATIVE))
        assertFalse(WarmStandbyPolicy.mayCarryNewUpstream(StandbyRole.WARM_STANDBY))
        assertFalse(WarmStandbyPolicy.mayCarryNewUpstream(StandbyRole.COLD))
    }

    @Test
    fun `a warm path carries heartbeats and cursors and nothing else`() {
        for (allowed in WarmStandbyPolicy.WARM_UPSTREAM_ALLOWED) {
            assertTrue(WarmStandbyPolicy.mayCarry(StandbyRole.WARM_STANDBY, allowed), allowed)
        }
        for (forbidden in listOf("command", "approval", "voice_turn", "browser_input")) {
            assertFalse(WarmStandbyPolicy.mayCarry(StandbyRole.WARM_STANDBY, forbidden), forbidden)
        }
    }

    @Test
    fun `a cold path carries nothing at all`() {
        for (type in WarmStandbyPolicy.WARM_UPSTREAM_ALLOWED + setOf("command")) {
            assertFalse(WarmStandbyPolicy.mayCarry(StandbyRole.COLD, type), type)
        }
    }
}

/**
 * §20.10 — "The client must never 'just open another socket and continue.'"
 */
class FailoverTransactionTest {

    private fun transaction() = FailoverTransaction(currentEpoch = 4, activePathId = "wss")

    @Test
    fun `promotion requires the transaction to have run`() {
        // Steps 6-8 are not reachable without 1-3. A client that could promote from idle
        // is the one the section forbids in those words.
        val tx = transaction()
        assertFalse(tx.promote("h2", 5), "cannot promote from idle")
        tx.markSuspect()
        assertFalse(tx.promote("h2", 5), "cannot promote without resuming")
        assertTrue(tx.beginResume())
        assertTrue(tx.promote("h2", 5))
    }

    @Test
    fun `an epoch that does not advance is not a promotion`() {
        // A Gateway answer re-granting the current epoch is a Gateway that has not moved
        // the session. Promoting on it would leave the old path believing it is still
        // authoritative, which is the two-authoritative-paths state this exists to avoid.
        val tx = transaction()
        tx.markSuspect()
        tx.beginResume()
        assertFalse(tx.promote("h2", 4))
        assertFalse(tx.promote("h2", 3))
        assertEquals("wss", tx.authoritativePathId)
    }

    @Test
    fun `the old path stops being authoritative in the same call`() {
        val tx = transaction()
        tx.markSuspect()
        tx.beginResume()
        tx.promote("h2", 5)
        assertEquals("h2", tx.authoritativePathId)
        assertEquals(5, tx.epoch)
    }

    @Test
    fun `a late envelope from the old path is rejected`() {
        // §20.10 step 9. The old socket is still open for a while and its in-flight
        // messages still arrive.
        val tx = transaction()
        tx.markSuspect()
        tx.beginResume()
        tx.promote("h2", 5)
        assertFalse(tx.acceptsUpstream("wss", 4))
        assertFalse(tx.acceptsUpstream("wss", 5), "not even at the new epoch")
        assertTrue(tx.acceptsUpstream("h2", 5))
    }

    @Test
    fun `rejection is by epoch, so a reused path does not inherit its old messages`() {
        // The same socket can legitimately become authoritative again later. Its earlier
        // messages still must not apply, which is why the check is not path identity
        // alone.
        val tx = transaction()
        tx.markSuspect()
        tx.beginResume()
        tx.promote("h2", 5)
        assertFalse(tx.acceptsUpstream("h2", 4), "an envelope from before the promotion")
    }

    @Test
    fun `an abandoned failover leaves the old path in place`() {
        val tx = transaction()
        tx.markSuspect()
        tx.beginResume()
        tx.abandon()
        assertEquals(FailoverTransaction.Phase.ABANDONED, tx.phase)
        assertEquals("wss", tx.authoritativePathId)
        assertEquals(4, tx.epoch)
        assertFalse(tx.promote("h2", 5), "and cannot be promoted afterwards")
    }
}
