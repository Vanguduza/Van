package com.dial.van.browser

import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanStatePriority

/**
 * Rev 1.5 §24 — what the browser is allowed to say about how VAN looks.
 *
 * Two rules, and both are prohibitions.
 *
 * **"Do not animate SUCCESS merely because navigation finished."** A page finishing
 * loading is not a task succeeding, and the difference is the whole of PR #48's contract:
 * the owner asked VAN to do something, and a green flourish when the page arrives tells
 * them it is done when nothing has been verified. `propose` therefore has no path to
 * `SUCCESS` at all — not a guarded one, not a conditional one. A browser cannot say it.
 *
 * **"Browser activity must not overwrite a higher-priority urgent/trading visual state."**
 * A trade halt and a page load are not comparable events, and the priority ladder alone
 * does not say so: `WORKING` outranks `SUCCESS` numerically while being far less important
 * than a `WARNING` the trading authority set. So the arbitration refuses to displace a
 * state the authority holds, whatever the numbers say.
 */

/** What the browser knows about itself, in the terms §24 maps from. */
data class BrowserVisualSnapshot(
    val connecting: Boolean = false,
    val connected: Boolean = false,
    val degraded: Boolean = false,
    /** The owner is driving. */
    val ownerBrowsing: Boolean = false,
    /** An agent holds the control lease and is acting. */
    val agentDriving: Boolean = false,
    /** Hermes is deciding what to do next, with nothing happening on the page yet. */
    val agentDeciding: Boolean = false,
    /** A page is loading in the tab the owner is looking at. */
    val navigating: Boolean = false,
    /** VAN needs the owner: a login, a consent, a captcha. */
    val ownerRequired: Boolean = false,
    /** The owner has touched nothing for a while and no work is running. */
    val idle: Boolean = false,
)

object BrowserVisualState {

    /**
     * The state the browser would like, or null when it has nothing to say.
     *
     * Null rather than `IDLE`: "the browser has no opinion" and "the browser says VAN is
     * idle" are different claims, and a browser that reported IDLE whenever it was not
     * doing anything would keep pulling the embodiment down out of states set by voice or
     * by a mission.
     */
    fun propose(snapshot: BrowserVisualSnapshot): VanDurableState? = when {
        // Asked for first, because everything below it is something VAN is doing and this
        // is something VAN has stopped doing until the owner acts.
        snapshot.ownerRequired -> VanDurableState.WAITING_FOR_OWNER
        snapshot.degraded -> VanDurableState.DEGRADED
        snapshot.connecting -> VanDurableState.CONNECTING
        snapshot.agentDeciding -> VanDurableState.THINKING
        // Navigating *because an agent is driving* is the agent working, which is a
        // different sentence to the owner clicking a link.
        snapshot.agentDriving && snapshot.navigating -> VanDurableState.SEARCHING
        snapshot.agentDriving -> VanDurableState.DELEGATING
        snapshot.ownerBrowsing -> VanDurableState.ATTENTIVE
        snapshot.idle && snapshot.connected -> VanDurableState.IDLE
        else -> null
    }

    /**
     * Whether [proposal] may take the embodiment from [current].
     *
     * The authority check comes before the ladder. A browser proposing `SEARCHING` over a
     * trading `WARNING` loses even though 60 is not compared to 90 — because the reason it
     * loses is not that the number is smaller, it is that the state is not the browser's
     * to change.
     */
    fun mayApply(current: VanDurableState, proposal: VanDurableState): Boolean {
        // No exceptions, including for the browser's own WAITING_FOR_OWNER. A first
        // version let a blocked browser session replace a softer authority state, on the
        // reasoning that needing the owner is itself an authority claim. It is — but it
        // is not the *browser's* claim to make over a trading warning, and a captcha that
        // can take the embodiment from a halted trade is exactly what §24 forbids. A
        // blocked session reaches the owner through the needs-you surface, which is where
        // a thing waiting on them belongs, rather than by competing for the aura.
        if (current in VanStatePriority.AUTHORITY_HELD) return false
        return VanStatePriority.of(proposal) >= VanStatePriority.of(current)
    }

    /**
     * The state to apply, or null to leave the embodiment alone.
     *
     * One call rather than two so a caller cannot propose and then forget to arbitrate —
     * which is the shape of every "the check exists and nothing calls it" defect this
     * programme has found.
     */
    fun arbitrate(
        current: VanDurableState,
        snapshot: BrowserVisualSnapshot,
    ): VanDurableState? {
        val proposal = propose(snapshot) ?: return null
        return if (mayApply(current, proposal)) proposal else null
    }

    /**
     * States the browser can never produce, asserted as data so a test can read it.
     *
     * `SUCCESS` is the one §24 names. The others are here because they belong to
     * subsystems that would be misreported: a browser that could say `SPEAKING` would
     * claim VAN was talking, and one that could say `URGENT` would give a web page the
     * loudest signal VAN has.
     */
    val NEVER_PROPOSED = setOf(
        VanDurableState.SUCCESS,
        VanDurableState.URGENT,
        VanDurableState.ERROR,
        VanDurableState.WARNING,
        VanDurableState.SPEAKING,
        VanDurableState.LISTENING,
        VanDurableState.SLEEPING,
        VanDurableState.OFFLINE,
        VanDurableState.WAITING,
        VanDurableState.WORKING,
    )
}
