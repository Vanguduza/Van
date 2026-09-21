package com.dial.van.visual

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * GAP-F-012 — every durable state and finite action has a real runtime producer.
 *
 * These exercise [VanEmbodimentReducer]'s decision functions against the exact wire shapes
 * the backend emits (`MissionEventType` values from `mission/models.py`,
 * `attention.upserted` from `attention/engine.py`), and [VanEmbodimentProducers] as the
 * completeness guard the original audit was missing: a state or action added to
 * [VanDurableState]/[VanFiniteAction] with no registered producer fails
 * [VanEmbodimentProducers.isComplete] here rather than shipping unreachable.
 */
class VanEmbodimentReducerTest {

    // -------------------------------------------------------------- completeness guard

    @Test
    fun `every durable state and finite action has a registered producer`() {
        val (missingStates, missingActions) = VanEmbodimentProducers.missing()
        assertTrue(missingStates.isEmpty(), "states with no producer: $missingStates")
        assertTrue(missingActions.isEmpty(), "actions with no producer: $missingActions")
        assertTrue(VanEmbodimentProducers.isComplete())
    }

    // -------------------------------------------------------------- mission events

    @Test
    fun `mission started without a hermes run id is local work`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.started", hasHermesRunId = false)
        assertEquals(VanEmbodimentReducer.Effect.ToState(VanDurableState.WORKING), effect)
    }

    @Test
    fun `mission started with a hermes run id delegates`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.started", hasHermesRunId = true)
        assertEquals(VanEmbodimentReducer.Effect.ToState(VanDurableState.DELEGATING), effect)
    }

    @Test
    fun `mission waiting owner asks and cautions`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.waiting_owner")
        assertEquals(
            VanEmbodimentReducer.Effect.Both(VanDurableState.WAITING_FOR_OWNER, VanFiniteAction.CAUTION, 0.45f),
            effect,
        )
    }

    @Test
    fun `mission completed presents the result card`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.completed")
        assertEquals(
            VanEmbodimentReducer.Effect.Both(VanDurableState.SUCCESS, VanFiniteAction.PRESENT_CARD),
            effect,
        )
    }

    @Test
    fun `mission completed unverifiable shrugs instead of celebrating`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.completed", stateHint = "UNVERIFIABLE")
        assertEquals(VanDurableState.WARNING, (effect as VanEmbodimentReducer.Effect.Both).state)
        assertEquals(VanFiniteAction.SHRUG, effect.action)
    }

    @Test
    fun `mission completed partial success also shrugs`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.completed", stateHint = "PARTIAL_SUCCESS")
        assertEquals(VanFiniteAction.SHRUG, (effect as VanEmbodimentReducer.Effect.Both).action)
    }

    @Test
    fun `mission failed is an error with urgency`() {
        val effect = VanEmbodimentReducer.forMissionEvent("mission.failed") as VanEmbodimentReducer.Effect.ToState
        assertEquals(VanDurableState.ERROR, effect.state)
        assertTrue(effect.urgency > 0f)
    }

    @Test
    fun `activity started with a research kind searches`() {
        val effect = VanEmbodimentReducer.forMissionEvent(
            "activity.started", activityKind = "web_research",
        )
        assertEquals(VanEmbodimentReducer.Effect.ToState(VanDurableState.SEARCHING), effect)
    }

    @Test
    fun `activity started with no kind hint just works`() {
        val effect = VanEmbodimentReducer.forMissionEvent("activity.started")
        assertEquals(VanEmbodimentReducer.Effect.ToState(VanDurableState.WORKING), effect)
    }

    @Test
    fun `an unrecognised event type with no hint produces nothing`() {
        assertEquals(VanEmbodimentReducer.Effect.None, VanEmbodimentReducer.forMissionEvent("mission.unknown_future_event"))
    }

    @Test
    fun `a state hint the device does not yet receive an event for still lands`() {
        // Backend gap: WAITING_EXTERNAL has no EVENT_FOR_STATE entry today. This proves the
        // reducer is forward-compatible with the day it does, without a second device change.
        val effect = VanEmbodimentReducer.forMissionEvent("mission.state_changed", stateHint = "WAITING_EXTERNAL")
        assertEquals(VanEmbodimentReducer.Effect.ToState(VanDurableState.WAITING), effect)
    }

    @Test
    fun `the json overload reads summary, hermes_run_id and activity_kind`() {
        val json = """{"summary":"UNVERIFIABLE","hermes_run_id":"run_1"}"""
        val effect = VanEmbodimentReducer.forMissionEvent(eventType = "mission.completed", payloadJson = json)
        assertEquals(VanFiniteAction.SHRUG, (effect as VanEmbodimentReducer.Effect.Both).action)
    }

    @Test
    fun `the json overload tolerates malformed json`() {
        assertEquals(
            VanEmbodimentReducer.Effect.ToState(VanDurableState.WORKING),
            VanEmbodimentReducer.forMissionEvent("mission.started", "{not json"),
        )
    }

    // -------------------------------------------------------------- attention

    @Test
    fun `attention urgent interrupts and cautions`() {
        val effect = VanEmbodimentReducer.forAttentionEvent("attention.upserted", "URGENT")
        assertEquals(
            VanEmbodimentReducer.Effect.Both(VanDurableState.URGENT, VanFiniteAction.CAUTION, 1f),
            effect,
        )
    }

    @Test
    fun `attention info blocker and follow_up do not interrupt the pose`() {
        for (severity in listOf("INFO", "FOLLOW_UP", "BLOCKER")) {
            assertEquals(
                VanEmbodimentReducer.Effect.None,
                VanEmbodimentReducer.forAttentionEvent("attention.upserted", severity),
                "severity=$severity",
            )
        }
    }

    @Test
    fun `the json overload reads severity off the payload`() {
        val effect = VanEmbodimentReducer.forAttentionEventJson("attention.upserted", """{"severity":"URGENT"}""")
        assertEquals(VanDurableState.URGENT, (effect as VanEmbodimentReducer.Effect.Both).state)
    }

    @Test
    fun `a non-attention event type produces nothing regardless of severity`() {
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forAttentionEvent("mission.started", "URGENT"),
        )
    }

    // -------------------------------------------------------------- trading (guarded on presence)

    @Test
    fun `a closed trade in the good decision good outcome quadrant celebrates`() {
        val effect = VanEmbodimentReducer.forTradingEvent(
            "trading.trade.closed", "GOOD_DECISION_GOOD_OUTCOME",
        )
        assertEquals(VanEmbodimentReducer.Effect.ToAction(VanFiniteAction.CELEBRATE), effect)
    }

    @Test
    fun `a closed trade in any other quadrant does not celebrate`() {
        for (quadrant in listOf("GOOD_DECISION_BAD_OUTCOME", "BAD_DECISION_GOOD_OUTCOME", "BAD_DECISION_BAD_OUTCOME", "")) {
            assertEquals(
                VanEmbodimentReducer.Effect.None,
                VanEmbodimentReducer.forTradingEvent("trading.trade.closed", quadrant.ifBlank { null }),
                "quadrant=$quadrant",
            )
        }
    }

    @Test
    fun `an absent quadrant field never celebrates — guarded on presence`() {
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forTradingEventJson("trading.trade.closed", payloadJson = "{}"),
        )
    }

    @Test
    fun `a different event type never celebrates even with a matching quadrant`() {
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forTradingEvent("trading.position.opened", "GOOD_DECISION_GOOD_OUTCOME"),
        )
    }

    // -------------------------------------------------------------- day marker / quiet hours / handshake

    @Test
    fun `the first session of a new day waves hello`() {
        assertEquals(
            VanEmbodimentReducer.Effect.ToAction(VanFiniteAction.HELLO_WAVE),
            VanEmbodimentReducer.forFirstSessionOfDay(lastMarkerDay = "2026-09-20", todayDay = "2026-09-21"),
        )
    }

    @Test
    fun `a second session on the same day does not wave again`() {
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forFirstSessionOfDay(lastMarkerDay = "2026-09-21", todayDay = "2026-09-21"),
        )
    }

    @Test
    fun `quiet hours with nothing open sleeps`() {
        assertEquals(
            VanEmbodimentReducer.Effect.ToState(VanDurableState.SLEEPING),
            VanEmbodimentReducer.forQuietHours(quietNow = true, hasOpenAttention = false),
        )
    }

    @Test
    fun `an open attention item outranks quiet hours`() {
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forQuietHours(quietNow = true, hasOpenAttention = true),
        )
    }

    @Test
    fun `outside quiet hours nothing sleeps`() {
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forQuietHours(quietNow = false, hasOpenAttention = false),
        )
    }

    @Test
    fun `a session handshake connects`() {
        assertEquals(
            VanEmbodimentReducer.Effect.ToState(VanDurableState.CONNECTING),
            VanEmbodimentReducer.forSessionHandshake(connecting = true),
        )
        assertEquals(
            VanEmbodimentReducer.Effect.None,
            VanEmbodimentReducer.forSessionHandshake(connecting = false),
        )
    }

    // -------------------------------------------------------------- overlay interaction

    @Test
    fun `overlay expand and collapse open and close the panel`() {
        assertEquals(
            VanEmbodimentReducer.Effect.ToAction(VanFiniteAction.OPEN_PANEL),
            VanEmbodimentReducer.forOverlayTransition(expanding = true),
        )
        assertEquals(
            VanEmbodimentReducer.Effect.ToAction(VanFiniteAction.CLOSE_PANEL),
            VanEmbodimentReducer.forOverlayTransition(expanding = false),
        )
    }

    @Test
    fun `every card direction maps to its own point action`() {
        val expected = mapOf(
            VanEmbodimentReducer.CardDirection.LEFT to VanFiniteAction.POINT_LEFT,
            VanEmbodimentReducer.CardDirection.RIGHT to VanFiniteAction.POINT_RIGHT,
            VanEmbodimentReducer.CardDirection.UP to VanFiniteAction.POINT_UP,
            VanEmbodimentReducer.CardDirection.DOWN to VanFiniteAction.POINT_DOWN,
            VanEmbodimentReducer.CardDirection.TARGET to VanFiniteAction.POINT_TARGET,
        )
        for ((direction, action) in expected) {
            assertEquals(
                VanEmbodimentReducer.Effect.ToAction(action),
                VanEmbodimentReducer.forCardHighlight(direction),
                "direction=$direction",
            )
        }
    }
}

class VanMotionMapTest {

    @Test
    fun `every finite action has a positive, bounded auto-clear duration`() {
        for (action in VanFiniteAction.entries) {
            val duration = VanMotionMap.actionDurationMs(action)
            assertTrue(duration > 0, "action=$action duration=$duration")
            assertTrue(duration <= 2_000L, "action=$action duration=$duration should stay legible, not linger")
        }
    }

    @Test
    fun `reduced motion collapses every overlay motion spec to zero`() {
        assertEquals(0, VanMotionMap.presentationChange(reducedMotion = true).durationMs)
        assertEquals(0, VanMotionMap.panelReveal(reducedMotion = true).durationMs)
        assertEquals(0, VanMotionMap.dockSnap(reducedMotion = true).durationMs)
        assertEquals(0, VanMotionMap.pressFeedback(reducedMotion = true).durationMs)
        assertEquals(0, VanMotionMap.flingDockDurationMs(5f, reducedMotion = true))
    }

    @Test
    fun `a fast flick docks faster than a slow release`() {
        val fast = VanMotionMap.flingDockDurationMs(10f)
        val slow = VanMotionMap.flingDockDurationMs(0.05f)
        assertTrue(fast < slow, "fast=$fast slow=$slow")
    }

    @Test
    fun `every duration stays within the DNA quick to expressive band`() {
        for (spec in listOf(
            VanMotionMap.presentationChange(),
            VanMotionMap.panelReveal(),
            VanMotionMap.dockSnap(),
            VanMotionMap.pressFeedback(),
        )) {
            assertTrue(spec.durationMs in VanMotionTokens.INSTANT_MS..VanMotionTokens.EXPRESSIVE_MS)
        }
    }
}
