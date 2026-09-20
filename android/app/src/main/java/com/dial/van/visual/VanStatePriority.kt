package com.dial.van.visual

/**
 * Which durable state wins when two parts of VAN want the embodiment at once.
 *
 * Extracted from `VanLiveVisualState`, where it was private and therefore unreachable by
 * anything that needed to ask the same question — including Rev 1.5 §24's browser
 * arbitration, which exists precisely so that "the page finished loading" cannot displace
 * "a trade needs you". A second copy of this ladder would have been two answers to one
 * question, and the two would have diverged on the state that mattered.
 *
 * Pure, so the ordering is executed rather than asserted in a comment.
 */
object VanStatePriority {

    fun of(state: VanDurableState): Int = when (state) {
        VanDurableState.ERROR, VanDurableState.URGENT -> 100
        VanDurableState.OFFLINE -> 95
        VanDurableState.DEGRADED, VanDurableState.WARNING -> 90
        VanDurableState.WAITING_FOR_OWNER -> 80
        VanDurableState.SPEAKING, VanDurableState.LISTENING -> 70
        VanDurableState.WORKING, VanDurableState.SEARCHING, VanDurableState.DELEGATING -> 60
        VanDurableState.THINKING, VanDurableState.CONNECTING, VanDurableState.ATTENTIVE -> 50
        VanDurableState.SUCCESS -> 45
        VanDurableState.WAITING -> 30
        VanDurableState.IDLE, VanDurableState.SLEEPING -> 10
    }

    /**
     * States that belong to something more important than whatever is being proposed.
     *
     * §24 — "Browser activity must not overwrite a higher-priority urgent/trading visual
     * state incorrectly." A trade halt and a page load are not comparable events and the
     * ladder alone does not say so: `WORKING` outranks `SUCCESS`, but a browser proposing
     * `WORKING` over a `WARNING` the trading authority set is the failure that section
     * names.
     */
    val AUTHORITY_HELD = setOf(
        VanDurableState.URGENT,
        VanDurableState.ERROR,
        VanDurableState.WARNING,
        VanDurableState.WAITING_FOR_OWNER,
        VanDurableState.OFFLINE,
    )
}
