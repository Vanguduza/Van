package com.dial.van.session

/**
 * Rev 1.5 §20.9 and ADR-RB-012 — the second path VAN keeps ready, and the four things it
 * must not do.
 *
 * Make-before-break only works if the standby is already authenticated when the primary
 * starts to fail; opening one at the moment of failure is break-before-make with extra
 * steps. So this decides *when* to hold one open, and the answer is not "always": a warm
 * standby is a second authenticated socket with its own heartbeats, and §20.9 is explicit
 * that it may be cold when the owner is not interacting, to preserve battery.
 *
 * What a warm standby carries, from §20.9:
 *
 *     heartbeats
 *     session cursor reconciliation
 *     no duplicate command uplink
 *
 * The third is the one with teeth and it is why [StandbyRole] exists rather than a
 * boolean. "Warm" and "authoritative" are different properties, and a standby that sent
 * an owner's command because it happened to be connected would produce the duplicate
 * §20.12's effectively-once admission exists to prevent — from VAN's own client, before
 * the Gateway ever sees it.
 *
 * Pure. The sockets are `VanHermesSessionManager`'s; every decision here is arithmetic
 * over battery, network and interaction state, and every case is one nobody can stage on
 * a real network on demand.
 */

/** What a path is allowed to do, which is not the same as whether it is connected. */
enum class StandbyRole {
    /** The one path epoch that may carry new upstream owner messages (§20.9). */
    AUTHORITATIVE,

    /**
     * Connected and authenticated, carrying heartbeats and cursor reconciliation only.
     *
     * Downstream duplicates arriving here are safe: `event_id` and response segment ids
     * are de-duplicated (§20.9). Upstream is the asymmetry — nothing new goes out.
     */
    WARM_STANDBY,

    /** Not connected. Opened on demand, which is break-before-make. */
    COLD,
}

/** What the phone can afford right now. */
data class StandbyConditions(
    val interactionActive: Boolean,
    val batteryPercent: Int,
    val charging: Boolean,
    /** The standby's own carrier, which may be the metered one. */
    val standbyIsMetered: Boolean,
    val dataSaverEnabled: Boolean,
    /** Whether a second genuinely independent route exists at all (§20.6). */
    val independentRouteAvailable: Boolean,
)

data class StandbyDecision(
    val role: StandbyRole,
    /** Why, in the owner's terms rather than in flags. */
    val reason: String,
)

object WarmStandbyPolicy {

    /**
     * Below this, a second socket is a cost the owner did not ask for.
     *
     * Not a cliff at zero: a phone at 15% that is about to need its remaining charge for
     * a call should not be spending it keeping a spare connection warm for a browser
     * session the owner is not currently looking at.
     */
    const val MIN_BATTERY_PERCENT = 20

    /**
     * Charging changes the calculation but not the rule about Data Saver.
     *
     * Data Saver is the owner saying "do less on mobile data", and a warm standby on a
     * metered carrier is precisely the background traffic it is about. Charging does not
     * make the data free.
     */
    fun decide(conditions: StandbyConditions): StandbyDecision {
        if (!conditions.independentRouteAvailable) {
            // §20.6 — a standby on the same route fails with the primary. Holding one
            // open would cost battery and buy nothing, and reporting it as redundancy
            // would tell the owner they are covered for the failure that will happen.
            return StandbyDecision(
                StandbyRole.COLD,
                "no second route: a spare path on the same road fails with the first",
            )
        }
        if (conditions.standbyIsMetered && conditions.dataSaverEnabled) {
            return StandbyDecision(
                StandbyRole.COLD,
                "Data Saver is on and the spare path is mobile data",
            )
        }
        if (!conditions.interactionActive) {
            // §20.9 — "when idle, fallback may be cold to preserve battery."
            return StandbyDecision(
                StandbyRole.COLD,
                "nothing is happening: the spare path opens when it is needed",
            )
        }
        if (!conditions.charging && conditions.batteryPercent < MIN_BATTERY_PERCENT) {
            return StandbyDecision(
                StandbyRole.COLD,
                "battery is low: VAN is not holding a spare connection open",
            )
        }
        return StandbyDecision(
            StandbyRole.WARM_STANDBY,
            "a spare path is ready, so a failure does not interrupt you",
        )
    }

    /**
     * §20.9 — whether this path may carry a new upstream owner message.
     *
     * The whole of "no duplicate command uplink", in one place that the send path asks.
     * A caller that could send on a warm path would produce the duplicate §20.12 exists
     * to reject — from VAN's own client, before the Gateway ever sees it.
     */
    fun mayCarryNewUpstream(role: StandbyRole): Boolean = role == StandbyRole.AUTHORITATIVE

    /**
     * What a warm path is allowed to send. Deliberately a closed list.
     *
     * Named rather than described so a test can read it, and so the next person adding a
     * message type has to decide which side of the line it is on rather than defaulting.
     */
    val WARM_UPSTREAM_ALLOWED = setOf("heartbeat", "cursor_ack", "resume_request")

    fun mayCarry(role: StandbyRole, messageType: String): Boolean = when (role) {
        StandbyRole.AUTHORITATIVE -> true
        StandbyRole.WARM_STANDBY -> messageType in WARM_UPSTREAM_ALLOWED
        StandbyRole.COLD -> false
    }
}

/**
 * §20.10 — a path switch is a transaction, and this is its ledger.
 *
 * The nine steps in §20.10 are not nine independent actions: steps 6 to 8 are the
 * promotion, and a client that performed 7 without 6 would be "just opening another
 * socket and continuing", which the section forbids in those words.
 *
 * So the epoch is granted by the Gateway and recorded here, and [promote] refuses a
 * promotion to an epoch the Gateway did not issue. The old path becomes non-authoritative
 * in the same call, because two authoritative paths is the state this whole mechanism
 * exists to never be in.
 */
class FailoverTransaction(
    private val currentEpoch: Int,
    private val activePathId: String,
) {
    enum class Phase { IDLE, SUSPECT, RESUMING, PROMOTED, ABANDONED }

    var phase: Phase = Phase.IDLE
        private set

    var epoch: Int = currentEpoch
        private set

    var authoritativePathId: String = activePathId
        private set

    /** Step 1. The primary is suspect; the standby has not been asked for anything yet. */
    fun markSuspect() {
        if (phase == Phase.IDLE) phase = Phase.SUSPECT
    }

    /** Steps 2-3. Resume the same logical session on the standby. */
    fun beginResume(): Boolean {
        if (phase != Phase.SUSPECT) return false
        phase = Phase.RESUMING
        return true
    }

    /**
     * Steps 6-8, atomically.
     *
     * Refuses an epoch that does not advance: a Gateway answer that re-granted the
     * current epoch is a Gateway that has not actually moved the session, and promoting
     * on it would leave the old path believing it is still authoritative.
     */
    fun promote(newPathId: String, grantedEpoch: Int): Boolean {
        if (phase != Phase.RESUMING) return false
        if (grantedEpoch <= epoch) return false
        epoch = grantedEpoch
        authoritativePathId = newPathId
        phase = Phase.PROMOTED
        return true
    }

    /** The standby could not resume. The old path keeps whatever life it has left. */
    fun abandon() {
        if (phase == Phase.RESUMING || phase == Phase.SUSPECT) phase = Phase.ABANDONED
    }

    /**
     * Step 9 — a late envelope from the old path.
     *
     * Rejected by epoch rather than by path id, because the same socket can legitimately
     * become authoritative again later and its earlier messages still must not apply.
     */
    fun acceptsUpstream(pathId: String, envelopeEpoch: Int): Boolean =
        pathId == authoritativePathId && envelopeEpoch == epoch
}
