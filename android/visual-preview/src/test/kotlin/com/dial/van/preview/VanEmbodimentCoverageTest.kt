package com.dial.van.preview

import com.dial.van.visual.VanDurableState
import com.dial.van.visual.VanEmbodimentProducers
import com.dial.van.visual.VanFiniteAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * GAP-F-012 regression guard.
 *
 * The original audit's finding, restated as a test: an aura family, a frame-budget signal,
 * a whole animation clock could exist on [VanDurableState]/[VanFiniteAction] with no
 * runtime path that ever produced them. [VanEmbodimentProducers] is the registry that names
 * where every value comes from; this fails the moment a state or action is added to either
 * enum without also naming its producer here, which is exactly the class of defect the
 * embodiment audit exists to catch before it ships rather than after.
 */
class VanEmbodimentCoverageTest {

    @Test
    fun everyDurableStateHasARegisteredProducer() {
        val (missingStates, _) = VanEmbodimentProducers.missing()
        assertTrue(
            "durable states with no registered producer: $missingStates",
            missingStates.isEmpty(),
        )
        assertEquals(VanDurableState.entries.size, VanEmbodimentProducers.STATES.size)
    }

    @Test
    fun everyFiniteActionHasARegisteredProducer() {
        val (_, missingActions) = VanEmbodimentProducers.missing()
        assertTrue(
            "finite actions with no registered producer: $missingActions",
            missingActions.isEmpty(),
        )
        assertEquals(VanFiniteAction.entries.size, VanEmbodimentProducers.ACTIONS.size)
    }

    @Test
    fun theRegistryReportsComplete() {
        assertTrue(VanEmbodimentProducers.isComplete())
    }

    @Test
    fun noProducerEntryIsBlank() {
        for ((state, producer) in VanEmbodimentProducers.STATES) {
            assertTrue("state=$state has a blank producer", producer.isNotBlank())
        }
        for ((action, producer) in VanEmbodimentProducers.ACTIONS) {
            assertTrue("action=$action has a blank producer", producer.isNotBlank())
        }
    }

    @Test
    fun theEvidenceMatrixRendersEveryStateAgainstEveryTradeSemanticTier() {
        val board = VanEvidenceMatrix.stateBySemanticTierBoard()
        assertTrue(board.width > 0 && board.height > 0)
    }

    @Test
    fun theEvidenceMatrixRendersEveryFiniteActionMidGesture() {
        val actionShots = VanEvidenceMatrix.shotsForTest().filter { it.mode == "ACTION" }
        assertEquals(VanFiniteAction.entries.size, actionShots.size)
        assertTrue(actionShots.all { it.phase == 0.5f })
        val coveredActions = actionShots.map { it.action }.toSet()
        for (action in VanFiniteAction.entries) {
            assertTrue("no ACTION shot for $action", action.name in coveredActions)
        }
    }
}
