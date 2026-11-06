package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotEquals
import kotlin.test.assertTrue

class VanAuraNoFieldLinesTest {
    private fun plan(state: VanDurableState, budget: VanEffectBudget, t: Float, slow: Float = 0f) =
        VanAuraPlanner.plan(VanAuraSpecs.forState(state, budget), VanAuraSpecs.forState(state, budget),
            200f, 200f, 100f, budget, t, slowPhase = slow)

    @Test fun rejectedArcRimAndStrandOpsNeverReachAnyLiveAuraPlan() {
        for (state in VanDurableState.entries) for (budget in VanEffectBudget.entries) for (phase in listOf(0f, .17f, .49f, .83f)) {
            val ops = plan(state, budget, phase)
            assertTrue(ops.none { it is VanAuraOp.Rim || it is VanAuraOp.Polyline || it is VanAuraOp.Quad }, "$state / $budget / $phase")
        }
    }
    @Test fun proceduralFallbackDoesNotReintroduceOuterStatusArcs() {
        for (state in VanDurableState.entries) for (phase in listOf(0f, .31f, .72f)) {
            val ops = VanScene.build(VanVisualState(durableState = state), VanSceneFrame(phase = phase))
            assertTrue(ops.filterIsInstance<VanDrawOp.Arc>().none { it.r >= .30f }, state.name)
        }
    }
    @Test fun idleEnergyMovesEvenWhenBodyStateAndInputsDoNotChange() {
        for (budget in listOf(VanEffectBudget.FULL, VanEffectBudget.REDUCED, VanEffectBudget.LOW)) {
            assertNotEquals(plan(VanDurableState.IDLE, budget, .10f), plan(VanDurableState.IDLE, budget, .16f), budget.name)
        }
    }
    @Test fun staticAndReducedMotionCannotAccidentallyAnimateFromCallerPhase() {
        for (state in VanDurableState.entries) for (budget in listOf(VanEffectBudget.STATIC, VanEffectBudget.REDUCED_MOTION)) {
            assertEquals(plan(state, budget, .10f, .10f), plan(state, budget, .80f, .60f), "$state / $budget")
        }
    }
    @Test fun auraClockHasItsOwnContinuousPeriodWithoutAnotherFrameLoop() {
        assertEquals(VanAuraMotionPhase.at(0), VanAuraMotionPhase.at(VanAuraMotionPhase.FLOW_PERIOD_NANOS))
        assertNotEquals(VanAuraMotionPhase.at(100_000_000), VanAuraMotionPhase.at(200_000_000))
        assertEquals(0f, VanAuraMotionPhase.at(-1))
    }
    @Test fun pausingTheSharedClockDoesNotReplayTimeSpentHidden() {
        val clock = VanAnimationClock(); clock.advance(1_000_000, 4_200); clock.advance(17_000_000, 4_200)
        val before = VanAuraMotionPhase.at(clock.elapsedNanos); clock.suspendTiming()
        clock.advance(100_000_000_000, 2_000)
        assertEquals(before, VanAuraMotionPhase.at(clock.elapsedNanos))
    }
    @Test fun liveFlowPreservesNonColourWarningAndApprovalSymbols() {
        val error = VanScene.build(VanVisualState(durableState = VanDurableState.ERROR), VanSceneFrame())
        val approval = VanScene.build(VanVisualState(durableState = VanDurableState.WAITING_FOR_OWNER), VanSceneFrame())
        val idle = VanScene.build(VanVisualState(durableState = VanDurableState.IDLE), VanSceneFrame())
        assertNotEquals(error, approval); assertNotEquals(error, idle); assertNotEquals(approval, idle)
    }
    @Test fun invalidGeometryProducesNoDrawOperations() {
        val spec = VanAuraSpecs.forState(VanDurableState.IDLE)
        assertTrue(VanAuraPlanner.plan(spec, spec, Float.NaN, 200f, 100f).isEmpty())
        assertTrue(VanAuraPlanner.plan(spec, spec, 200f, 200f, Float.POSITIVE_INFINITY).isEmpty())
    }
}
