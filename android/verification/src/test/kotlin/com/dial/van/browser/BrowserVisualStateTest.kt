package com.dial.van.browser

import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanStatePriority
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Rev 1.5 §24 — what the browser may say about how VAN looks, and the two things it may
 * never say.
 */
class BrowserVisualStateTest {

    @Test
    fun `a finished navigation is never SUCCESS`() {
        // The sentence §24 states as a prohibition, and PR #48's contract in visual form:
        // a page arriving is not a task succeeding, and a green flourish tells the owner
        // it is done when nothing has been verified.
        //
        // Asserted over every combination rather than over one, because a guarded path to
        // SUCCESS would pass a single-case test.
        val flags = listOf(true, false)
        for (connected in flags) for (owner in flags) for (agent in flags) {
            for (navigating in flags) for (deciding in flags) for (idle in flags) {
                val proposal = BrowserVisualState.propose(
                    BrowserVisualSnapshot(
                        connected = connected, ownerBrowsing = owner, agentDriving = agent,
                        navigating = navigating, agentDeciding = deciding, idle = idle,
                    ),
                )
                assertFalse(
                    proposal in BrowserVisualState.NEVER_PROPOSED,
                    "proposed $proposal for connected=$connected owner=$owner agent=$agent " +
                        "navigating=$navigating deciding=$deciding idle=$idle",
                )
            }
        }
    }

    @Test
    fun `the states it maps are the ones section 24 lists`() {
        assertEquals(
            VanDurableState.CONNECTING,
            BrowserVisualState.propose(BrowserVisualSnapshot(connecting = true)),
        )
        assertEquals(
            VanDurableState.ATTENTIVE,
            BrowserVisualState.propose(BrowserVisualSnapshot(connected = true, ownerBrowsing = true)),
        )
        assertEquals(
            VanDurableState.THINKING,
            BrowserVisualState.propose(BrowserVisualSnapshot(connected = true, agentDeciding = true)),
        )
        assertEquals(
            VanDurableState.SEARCHING,
            BrowserVisualState.propose(
                BrowserVisualSnapshot(connected = true, agentDriving = true, navigating = true),
            ),
        )
        assertEquals(
            VanDurableState.DELEGATING,
            BrowserVisualState.propose(BrowserVisualSnapshot(connected = true, agentDriving = true)),
        )
        assertEquals(
            VanDurableState.WAITING_FOR_OWNER,
            BrowserVisualState.propose(BrowserVisualSnapshot(connected = true, ownerRequired = true)),
        )
        assertEquals(
            VanDurableState.DEGRADED,
            BrowserVisualState.propose(BrowserVisualSnapshot(connected = true, degraded = true)),
        )
    }

    @Test
    fun `needing the owner outranks everything else the browser is doing`() {
        // A captcha behind an agent that is still "working" is a browser that looks busy
        // and is in fact stopped.
        assertEquals(
            VanDurableState.WAITING_FOR_OWNER,
            BrowserVisualState.propose(
                BrowserVisualSnapshot(
                    connected = true, agentDriving = true, navigating = true,
                    degraded = true, ownerRequired = true,
                ),
            ),
        )
    }

    @Test
    fun `a browser with nothing to say says nothing`() {
        // Not IDLE. "The browser has no opinion" and "the browser says VAN is idle" are
        // different claims, and the second keeps pulling the embodiment out of states
        // that voice or a mission set.
        assertNull(BrowserVisualState.propose(BrowserVisualSnapshot()))
        assertNull(BrowserVisualState.propose(BrowserVisualSnapshot(idle = true)))
    }

    @Test
    fun `a page load does not displace a trading warning`() {
        // §24's other prohibition. The ladder alone does not decide this: the browser is
        // not proposing something less important, it is proposing something that is not
        // its to change.
        for (held in VanStatePriority.AUTHORITY_HELD) {
            val applied = BrowserVisualState.arbitrate(
                current = held,
                snapshot = BrowserVisualSnapshot(
                    connected = true, agentDriving = true, navigating = true,
                ),
            )
            assertNull(applied, "browser displaced $held")
        }
    }

    @Test
    fun `even needing the owner does not take an authority state`() {
        // The tempting exception, and the one that is wrong: needing the owner *is* an
        // authority claim, but it is not the browser's claim to make over a halted trade.
        // A captcha that can displace an URGENT is precisely what §24 forbids, and a
        // blocked session reaches the owner through the needs-you surface instead.
        for (held in VanStatePriority.AUTHORITY_HELD) {
            assertFalse(
                BrowserVisualState.mayApply(held, VanDurableState.WAITING_FOR_OWNER),
                "browser took $held",
            )
        }
    }

    @Test
    fun `a degraded connection outranks a blocked page by the ladder alone`() {
        // DEGRADED is not an authority state, so this is the ordinary comparison — and the
        // existing ladder puts a connection VAN cannot rely on above a page waiting for a
        // login. That ordering predates the browser and the browser does not get to bend
        // it for its own case.
        assertFalse(
            BrowserVisualState.mayApply(VanDurableState.DEGRADED, VanDurableState.WAITING_FOR_OWNER),
        )
        assertTrue(
            VanStatePriority.of(VanDurableState.DEGRADED) >
                VanStatePriority.of(VanDurableState.WAITING_FOR_OWNER),
        )
    }

    @Test
    fun `the browser does not pull VAN down out of a louder state it does not own`() {
        // SPEAKING is 70 and ATTENTIVE is 50: the owner scrolling a page while VAN is
        // reading an answer out loud must not stop the answer looking like an answer.
        assertNull(
            BrowserVisualState.arbitrate(
                current = VanDurableState.SPEAKING,
                snapshot = BrowserVisualSnapshot(connected = true, ownerBrowsing = true),
            ),
        )
    }

    @Test
    fun `the browser may take VAN up from idle`() {
        assertEquals(
            VanDurableState.DELEGATING,
            BrowserVisualState.arbitrate(
                current = VanDurableState.IDLE,
                snapshot = BrowserVisualSnapshot(connected = true, agentDriving = true),
            ),
        )
    }

    @Test
    fun `a proposal equal to what is showing is still applied`() {
        // Re-applying the same state is how a transient hold is refreshed. Refusing it
        // because it is not strictly greater would let a long agent run decay.
        assertEquals(
            VanDurableState.ATTENTIVE,
            BrowserVisualState.arbitrate(
                current = VanDurableState.ATTENTIVE,
                snapshot = BrowserVisualSnapshot(connected = true, ownerBrowsing = true),
            ),
        )
    }
}
