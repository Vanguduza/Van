package com.dial.van.dialdev

import com.dial.van.design.MissionStatus
import com.dial.van.design.StatusSemantics

/**
 * VAN-DEV-004 — DIAL task/stage state → VAN semantics (`VAN-DEVCC-R1` §4), exhaustively.
 *
 * VAN only *displays* DIAL state. The one thing this file must never do is turn an agent's
 * own "I am done" into a passed task: [DialDevState.COMPLETION_CANDIDATE] reads "Claimed
 * done · verifying" in the `cognition` role, and only the projection's own [DialDevState.PASS]
 * reads "Passed". Every `when` below is on the enum and has no `else` — a DIAL state added
 * upstream without a row here is a compile error, not a silent inheritance of whatever the
 * last branch said.
 *
 * Pure Kotlin (no Android, no Compose) so `android/verification` executes the table.
 */
enum class DialDevState {
    NOT_APPLICABLE,
    BLOCKED,
    READY,
    RUNNING,
    WAITING_OWNER,
    WAITING_EXTERNAL,
    VERIFYING,
    PASS,
    FAIL,
    INVALIDATED,
    SUPERSEDED,

    /** An agent reported completion; DIAL has not admitted the evidence. Never "passed". */
    COMPLETION_CANDIDATE,
    ;

    companion object {
        /** The wire name → state, or null for a name this build does not know. Never a guess. */
        fun parse(raw: String?): DialDevState? {
            val name = raw?.trim()?.uppercase().orEmpty()
            return entries.firstOrNull { it.name == name }
        }
    }
}

/**
 * What a row shows for one DIAL state. [missionStatus] is null only for
 * [DialDevState.NOT_APPLICABLE], which is hidden from lists ([visibleInLists] = false).
 */
data class DialDevPresentation(
    val state: DialDevState,
    val missionStatus: MissionStatus?,
    val role: String,
    val caption: String,
    val visibleInLists: Boolean,
)

/** The variable parts of a caption, all read from the projection; blank means "not sent". */
data class DialDevCaptionContext(
    val firstBlocker: String? = null,
    val harness: String? = null,
    val model: String? = null,
    val external: String? = null,
)

object DialDevSemantics {

    /**
     * The state a row is presented in. A completion candidate is a flag DIAL may send beside a
     * RUNNING or VERIFYING state (`completion_candidate: true`) or as its own state name; either
     * way it is presented as [DialDevState.COMPLETION_CANDIDATE] and never as PASS. A PASS from
     * the projection is PASS whatever the flag says — admission is DIAL's decision, not VAN's.
     */
    fun effectiveState(rawState: String?, completionCandidate: Boolean): DialDevState? {
        val parsed = DialDevState.parse(rawState) ?: return null
        if (!completionCandidate) return parsed
        return when (parsed) {
            DialDevState.RUNNING, DialDevState.VERIFYING, DialDevState.READY -> DialDevState.COMPLETION_CANDIDATE
            DialDevState.NOT_APPLICABLE,
            DialDevState.BLOCKED,
            DialDevState.WAITING_OWNER,
            DialDevState.WAITING_EXTERNAL,
            DialDevState.PASS,
            DialDevState.FAIL,
            DialDevState.INVALIDATED,
            DialDevState.SUPERSEDED,
            DialDevState.COMPLETION_CANDIDATE,
            -> parsed
        }
    }

    fun present(state: DialDevState, context: DialDevCaptionContext = DialDevCaptionContext()): DialDevPresentation =
        when (state) {
            DialDevState.NOT_APPLICABLE -> row(state, null, StatusSemantics.ROLE_DISABLED, "Not applicable", visible = false)
            DialDevState.BLOCKED -> row(
                state, MissionStatus.WAITING, StatusSemantics.ROLE_DETERIORATING,
                joinCaption("Blocked", context.firstBlocker),
            )
            DialDevState.READY -> row(state, MissionStatus.WAITING, StatusSemantics.ROLE_MONITOR, "Ready")
            DialDevState.RUNNING -> row(
                state, MissionStatus.RUNNING, StatusSemantics.ROLE_ENGAGED,
                joinCaption("Running", harnessModel(context)),
            )
            DialDevState.WAITING_OWNER -> row(state, MissionStatus.WAITING, StatusSemantics.ROLE_EVENT_RISK, "Needs you")
            DialDevState.WAITING_EXTERNAL -> row(
                state, MissionStatus.WAITING_EXTERNAL, StatusSemantics.ROLE_HYPOTHESIS,
                joinCaption("Waiting", context.external),
            )
            DialDevState.VERIFYING -> row(state, MissionStatus.RUNNING, StatusSemantics.ROLE_COGNITION, "Verifying")
            DialDevState.PASS -> row(state, MissionStatus.DONE, StatusSemantics.ROLE_FAVOURABLE, "Passed · evidence admitted")
            DialDevState.FAIL -> row(state, MissionStatus.FAILED, StatusSemantics.ROLE_CRITICAL, "Failed")
            DialDevState.INVALIDATED -> row(
                state, MissionStatus.FAILED, StatusSemantics.ROLE_DETERIORATING, "Invalidated · plan changed",
            )
            DialDevState.SUPERSEDED -> row(state, MissionStatus.DONE, StatusSemantics.ROLE_DISABLED, "Superseded")
            DialDevState.COMPLETION_CANDIDATE -> row(
                state, MissionStatus.RUNNING, StatusSemantics.ROLE_COGNITION, "Claimed done · verifying",
            )
        }

    /**
     * A state name this build does not know is shown as itself, in the `disabled` role, and
     * stays visible — an unknown state is exactly what the owner should see rather than have
     * VAN translate into something familiar.
     */
    fun presentRaw(
        rawState: String?,
        completionCandidate: Boolean = false,
        context: DialDevCaptionContext = DialDevCaptionContext(),
    ): RawPresentation {
        val state = effectiveState(rawState, completionCandidate)
            ?: return RawPresentation(
                known = null,
                role = StatusSemantics.ROLE_DISABLED,
                caption = "Unknown state · ${rawState?.trim()?.ifBlank { null } ?: "not reported"}",
                visibleInLists = true,
            )
        val p = present(state, context)
        return RawPresentation(known = p, role = p.role, caption = p.caption, visibleInLists = p.visibleInLists)
    }

    data class RawPresentation(
        val known: DialDevPresentation?,
        val role: String,
        val caption: String,
        val visibleInLists: Boolean,
    )

    private fun row(
        state: DialDevState,
        missionStatus: MissionStatus?,
        role: String,
        caption: String,
        visible: Boolean = true,
    ) = DialDevPresentation(state, missionStatus, role, caption, visible)

    private fun harnessModel(context: DialDevCaptionContext): String? {
        val harness = context.harness?.trim().orEmpty()
        val model = context.model?.trim().orEmpty()
        return when {
            harness.isNotEmpty() && model.isNotEmpty() -> "$harness/$model"
            harness.isNotEmpty() -> harness
            model.isNotEmpty() -> model
            else -> null
        }
    }

    private fun joinCaption(head: String, tail: String?): String {
        val detail = tail?.trim().orEmpty()
        return if (detail.isEmpty()) head else "$head · $detail"
    }
}
