package com.dial.van.visual

import org.json.JSONObject

/**
 * GAP-F-012 — event to embodiment decision, as pure functions.
 *
 * `VanLiveVisualState` already carries the mutable, main-thread half of the presence
 * runtime (delayed idle settling, generation tokens, the Handler). What was missing was a
 * single place that answers "given this real event, what should VAN's durable state or
 * finite action become" for the sources DNA §6 names but nothing wired: mission events off
 * the device event stream, attention upserts, the first session of the day, quiet hours, a
 * session handshake, an overlay expand/collapse, a card highlight, and a closed trade. Every
 * function here is total and defensive — an event type this reducer does not recognise, or a
 * payload missing an expected field, produces [Effect.None] rather than a guess, which is
 * the same discipline [VanTradeSemantics] already applies to an unreadable ledger.
 *
 * Pure Kotlin: JSON parsing is the only dependency, so this file executes in
 * `android/verification` and in the app, but is deliberately **not** shared into
 * `android/visual-preview` (which has no JSON library on its classpath) — the producer
 * registry other modules need to read is the dependency-free [VanEmbodimentProducers].
 */
object VanEmbodimentReducer {

    /** What a decision function asks the caller to do. At most one state and one action. */
    sealed interface Effect {
        data class ToState(val state: VanDurableState, val urgency: Float = 0f) : Effect
        data class ToAction(val action: VanFiniteAction) : Effect
        data class Both(
            val state: VanDurableState,
            val action: VanFiniteAction,
            val urgency: Float = 0f,
        ) : Effect
        object None : Effect
    }

    /** Directions the expanded overlay can point VAN toward a card (DNA §6's `POINT_*`). */
    enum class CardDirection { LEFT, RIGHT, UP, DOWN, TARGET }

    // ---------------------------------------------------------------- mission events

    /**
     * Mission events off the device event stream (`VanEventStreamStore`'s new-record flow).
     *
     * `eventType` is a `MissionEventType` wire value (`mission.started`, `mission.completed`,
     * ...). `stateHint`, when non-null, is the literal `MissionState` string when the backend
     * happened to carry one — `MissionService.transition` falls back to `target.value` as the
     * event's `summary` field when no explicit summary was given, so `mission.completed`
     * events for `VERIFIED_SUCCESS`, `PARTIAL_SUCCESS` and `FAILED` do carry it; the caller
     * passes the event's `summary` field here verbatim. `hasHermesRunId` distinguishes local
     * WORKING from Hermes-delegated DELEGATING for a running mission. `activityKind`, when
     * present, is whatever free-text kind label an activity event carries; a kind containing
     * "search"/"browser"/"research" routes to SEARCHING rather than the WORKING default.
     *
     * Two states DNA §6 names — WAITING (`mission WAITING_EXTERNAL`) and the UNVERIFIABLE/
     * EXPIRED branches of a completed mission — have no dedicated backend event today:
     * `mission/models.py`'s `EVENT_FOR_STATE` only covers UNDERSTOOD, PLANNED, RUNNING,
     * WAITING_FOR_OWNER, RESUME_AUTHORIZED, VERIFYING, VERIFIED_SUCCESS, PARTIAL_SUCCESS and
     * FAILED — a mission that reaches WAITING_EXTERNAL, UNVERIFIABLE, EXPIRED, CANCELLED or a
     * BLOCKED_* state publishes nothing at all. `stateHint` is read defensively for exactly
     * this reason: today it can only ever be one of the tokens above, and this function is
     * written to also do the right thing the day `mission/service.py` starts recording the
     * others, without a second change on the device side.
     */
    fun forMissionEvent(
        eventType: String,
        stateHint: String? = null,
        hasHermesRunId: Boolean = false,
        activityKind: String? = null,
    ): Effect = when (eventType) {
        "mission.started" ->
            Effect.ToState(if (hasHermesRunId) VanDurableState.DELEGATING else VanDurableState.WORKING)
        "mission.understood", "mission.planned" -> Effect.ToState(VanDurableState.THINKING)
        "mission.waiting_owner" ->
            Effect.Both(VanDurableState.WAITING_FOR_OWNER, VanFiniteAction.CAUTION, urgency = 0.45f)
        "mission.resumed" -> Effect.ToState(VanDurableState.WORKING)
        "mission.verifying" -> Effect.ToState(VanDurableState.WORKING)
        "mission.completed" -> when (stateHint) {
            "UNVERIFIABLE", "PARTIAL_SUCCESS" ->
                Effect.Both(VanDurableState.WARNING, VanFiniteAction.SHRUG, urgency = 0.30f)
            else -> Effect.Both(VanDurableState.SUCCESS, VanFiniteAction.PRESENT_CARD)
        }
        "mission.failed" -> Effect.ToState(VanDurableState.ERROR, urgency = 0.55f)
        "activity.started" ->
            Effect.ToState(if (activityKind.isResearchLike()) VanDurableState.SEARCHING else VanDurableState.WORKING)
        "activity.checkpointed" -> Effect.None
        "activity.completed" -> Effect.None
        "activity.failed" -> Effect.ToState(VanDurableState.WARNING, urgency = 0.25f)
        // Forward-compatible with a future `EVENT_FOR_STATE` entry: an event type this
        // reducer does not recognise, but whose hint is a state DNA does name, still lands.
        else -> when (stateHint) {
            "WAITING_EXTERNAL" -> Effect.ToState(VanDurableState.WAITING)
            "EXPIRED" -> Effect.ToState(VanDurableState.WARNING, urgency = 0.30f)
            else -> Effect.None
        }
    }

    /** Convenience overload reading the fields this needs straight off a JSON payload. */
    fun forMissionEvent(eventType: String, payloadJson: String): Effect {
        val payload = parseObjectOrNull(payloadJson)
        val summary = payload?.optString("summary")?.takeIf { it.isNotBlank() }
        val kind = payload?.optString("activity_kind")?.takeIf { it.isNotBlank() }
            ?: payload?.optString("kind")?.takeIf { it.isNotBlank() }
        val hermesRunId = payload?.optString("hermes_run_id")?.takeIf { it.isNotBlank() }
        return forMissionEvent(
            eventType = eventType,
            stateHint = summary,
            hasHermesRunId = hermesRunId != null,
            activityKind = kind,
        )
    }

    // ---------------------------------------------------------------- attention events

    /**
     * `attention.upserted`, DNA §6: severity URGENT is the only severity that reaches the
     * embodiment directly — INFO/FOLLOW_UP/BLOCKER stay on the Attention screen's triage list
     * rather than interrupting VAN's pose, which is [Effect.None] here by design, not an
     * omission.
     */
    fun forAttentionEvent(eventType: String, severity: String?): Effect {
        if (eventType != "attention.upserted") return Effect.None
        return if (severity == "URGENT") {
            Effect.Both(VanDurableState.URGENT, VanFiniteAction.CAUTION, urgency = 1f)
        } else {
            Effect.None
        }
    }

    fun forAttentionEventJson(eventType: String, payloadJson: String): Effect {
        val payload = parseObjectOrNull(payloadJson) ?: return Effect.None
        return forAttentionEvent(eventType, payload.optString("severity").takeIf { it.isNotBlank() })
    }

    // ---------------------------------------------------------------- trading events

    /**
     * A closed trade, DNA §6: CELEBRATE only in the GOOD_DECISION_GOOD_OUTCOME quadrant, and
     * only ever from the outcome quadrant — never from P&L alone, which is the rule
     * [VanTradeSemantics] already enforces for the aura and is repeated here for the action.
     *
     * Guarded on presence throughout: as of this change no producer in `trading/` or
     * `backend/van_gateway` emits a `trading.trade.closed` event or a `quadrant` field, so
     * every branch below is written to no-op cleanly on an absent or unrecognised event/field
     * rather than assume the shape exists. See the report for what the trading-events owner
     * needs to add for this to fire in production.
     */
    fun forTradingEvent(eventType: String, quadrant: String?): Effect {
        if (eventType != "trading.trade.closed") return Effect.None
        return if (quadrant == "GOOD_DECISION_GOOD_OUTCOME") {
            Effect.ToAction(VanFiniteAction.CELEBRATE)
        } else {
            Effect.None
        }
    }

    fun forTradingEventJson(eventType: String, payloadJson: String): Effect {
        val payload = parseObjectOrNull(payloadJson) ?: return Effect.None
        return forTradingEvent(eventType, payload.optString("quadrant").takeIf { it.isNotBlank() })
    }

    // ---------------------------------------------------------------- day / quiet hours / session

    /** HELLO_WAVE once, the first time a session opens on a calendar day the owner is in. */
    fun forFirstSessionOfDay(lastMarkerDay: String?, todayDay: String): Effect =
        if (todayDay.isNotBlank() && lastMarkerDay != todayDay) {
            Effect.ToAction(VanFiniteAction.HELLO_WAVE)
        } else {
            Effect.None
        }

    /**
     * SLEEPING while quiet hours hold and nothing open needs the owner. An open attention
     * item outranks quiet hours — DNA's exact phrasing, "quiet hours with no open attention"
     * — so a BLOCKER or URGENT item arriving at 2am still reaches VAN's pose.
     */
    fun forQuietHours(quietNow: Boolean, hasOpenAttention: Boolean): Effect =
        if (quietNow && !hasOpenAttention) Effect.ToState(VanDurableState.SLEEPING) else Effect.None

    fun forSessionHandshake(connecting: Boolean): Effect =
        if (connecting) Effect.ToState(VanDurableState.CONNECTING) else Effect.None

    // ---------------------------------------------------------------- overlay interaction

    fun forOverlayTransition(expanding: Boolean): Effect =
        Effect.ToAction(if (expanding) VanFiniteAction.OPEN_PANEL else VanFiniteAction.CLOSE_PANEL)

    fun forCardHighlight(direction: CardDirection): Effect = Effect.ToAction(
        when (direction) {
            CardDirection.LEFT -> VanFiniteAction.POINT_LEFT
            CardDirection.RIGHT -> VanFiniteAction.POINT_RIGHT
            CardDirection.UP -> VanFiniteAction.POINT_UP
            CardDirection.DOWN -> VanFiniteAction.POINT_DOWN
            CardDirection.TARGET -> VanFiniteAction.POINT_TARGET
        },
    )

    private fun String?.isResearchLike(): Boolean {
        val lower = this?.lowercase() ?: return false
        return "search" in lower || "browser" in lower || "research" in lower
    }

    private fun parseObjectOrNull(json: String): JSONObject? =
        if (json.isBlank()) null else runCatching { JSONObject(json) }.getOrNull()
}
