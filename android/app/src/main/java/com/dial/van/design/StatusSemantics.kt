package com.dial.van.design

/**
 * Thesis state → colour role, decoupled from the trading package this worker does not own.
 *
 * `trading/` will migrate its own thesis-state type onto this input as part of adopting the
 * design system; until then this enum is the contract it migrates to. `CONFIRMED` and
 * `WEAKENING`/`INVALIDATED` are deliberately not "green means good, red means bad" — DNA §2:
 * "Never use raw green/red for P&L emotion." These are thesis-confidence states, not P&L.
 */
enum class ThesisState {
    /** The idea has not yet earned a confirmed/weakening read. */
    HYPOTHESIS,

    /** Being watched; nothing has moved for or against it yet. */
    MONITORING,

    /** Evidence continues to support the thesis. */
    CONFIRMED,

    /** Evidence is turning against the thesis, short of invalidation. */
    WEAKENING,

    /** The thesis's own invalidation condition has been met. */
    INVALIDATED,
}

/** Attention triage severity (DNA §4: "triage list INFO/FOLLOW_UP/BLOCKER/URGENT"). */
enum class AttentionSeverity {
    INFO,
    FOLLOW_UP,
    BLOCKER,
    URGENT,
}

/** Mission lifecycle status (DNA §6 embodiment binding, mission producers). */
enum class MissionStatus {
    RUNNING,
    WAITING,
    WAITING_EXTERNAL,
    DONE,
    FAILED,
    DEGRADED,
}

/**
 * Domain state → colour role name (DNA §2 status semantics), as strings rather than
 * `androidx.compose.ui.graphics.Color`.
 *
 * Strings, not colours, for the same reason `VanCaptions.forState` returns a `String` rather
 * than drawing anything: the mapping is a decision a test can assert on the JVM, and the
 * Compose layer (`VanColorTokens.forStatusRole` in `VanTokens.kt`) is the only place that
 * turns the name into a paintable value. Every `when` here is exhaustive on purpose — an
 * `else` branch is how an unmapped state quietly inherits whatever role came before it.
 *
 * Role names match DNA §2 exactly: `monitor`, `engaged`, `cognition`, `hypothesis`,
 * `eventRisk`, `favourable`, `deteriorating`, `critical`, `disabled`.
 */
object StatusSemantics {
    const val ROLE_MONITOR = "monitor"
    const val ROLE_ENGAGED = "engaged"
    const val ROLE_COGNITION = "cognition"
    const val ROLE_HYPOTHESIS = "hypothesis"
    const val ROLE_EVENT_RISK = "eventRisk"
    const val ROLE_FAVOURABLE = "favourable"
    const val ROLE_DETERIORATING = "deteriorating"
    const val ROLE_CRITICAL = "critical"
    const val ROLE_DISABLED = "disabled"

    /** All valid role names, for validating a role that arrived as a bare string. */
    val ALL_ROLES: Set<String> = setOf(
        ROLE_MONITOR, ROLE_ENGAGED, ROLE_COGNITION, ROLE_HYPOTHESIS,
        ROLE_EVENT_RISK, ROLE_FAVOURABLE, ROLE_DETERIORATING, ROLE_CRITICAL, ROLE_DISABLED,
    )

    fun forThesisState(state: ThesisState): String = when (state) {
        ThesisState.HYPOTHESIS -> ROLE_HYPOTHESIS
        ThesisState.MONITORING -> ROLE_MONITOR
        ThesisState.CONFIRMED -> ROLE_FAVOURABLE
        ThesisState.WEAKENING -> ROLE_DETERIORATING
        ThesisState.INVALIDATED -> ROLE_CRITICAL
    }

    fun forAttentionSeverity(severity: AttentionSeverity): String = when (severity) {
        AttentionSeverity.INFO -> ROLE_MONITOR
        AttentionSeverity.FOLLOW_UP -> ROLE_COGNITION
        AttentionSeverity.BLOCKER -> ROLE_EVENT_RISK
        AttentionSeverity.URGENT -> ROLE_CRITICAL
    }

    /**
     * RUNNING/WAITING map to the aura's own DELEGATING/WAITING/WAITING_EXTERNAL grammar
     * (DNA §6): work under way reads as `engaged`, a mission waiting on its own next step
     * reads as `cognition` (VAN is still tracking it), and a mission blocked on something
     * outside VAN reads as `hypothesis` (unconfirmed until that external step resolves) —
     * distinct from `WAITING_FOR_OWNER`, which is the owner's own attention queue and is
     * carried by [AttentionSeverity], not this mapping.
     */
    fun forMissionStatus(status: MissionStatus): String = when (status) {
        MissionStatus.RUNNING -> ROLE_ENGAGED
        MissionStatus.WAITING -> ROLE_COGNITION
        MissionStatus.WAITING_EXTERNAL -> ROLE_HYPOTHESIS
        MissionStatus.DONE -> ROLE_FAVOURABLE
        MissionStatus.FAILED -> ROLE_CRITICAL
        MissionStatus.DEGRADED -> ROLE_EVENT_RISK
    }
}
