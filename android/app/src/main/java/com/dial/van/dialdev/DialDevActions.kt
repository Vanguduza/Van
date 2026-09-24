package com.dial.van.dialdev

import com.dial.van.design.StatusSemantics
import org.json.JSONException
import org.json.JSONObject

/**
 * VAN-DEV-009 — typed owner actions (`VAN-DEVCC-R1` §3.3, §5), the pure half.
 *
 * VAN forwards; DIAL decides. Nothing here marks anything done: an action is `ACCEPTED ·
 * pending` from the moment the gateway answers 202 until the *projection* reports the same
 * `action_id` as APPLIED, REJECTED or SUPERSEDED. A 409 `STALE_VIEW` means the owner acted on
 * a view that DIAL has moved past — the screen refetches and shows the new state before a
 * retry is offered. No action is ever built without the projection revision it was decided
 * against, which is also why none is ever queued offline.
 */
enum class DialDevActionKind {
    STEER_TASK,
    PAUSE_TASK_SAFE,
    RESUME_TASK,
    REQUEST_CHECKPOINT,
    REQUEST_REVIEW,
    REVOKE_TASK,
    DECIDE,
    PAUSE_MISSION,
    RESUME_MISSION,
    REPRIORITISE,
}

/** What an action is aimed at. Blank fields are omitted from the wire body. */
data class DialDevActionTarget(
    val projectId: String? = null,
    val taskId: String? = null,
    val workspaceId: String? = null,
    val decisionId: String? = null,
)

object DialDevActionPolicy {

    /** The owner-facing verb for a control. */
    fun label(kind: DialDevActionKind): String = when (kind) {
        DialDevActionKind.STEER_TASK -> "Steer"
        DialDevActionKind.PAUSE_TASK_SAFE -> "Pause safely"
        DialDevActionKind.RESUME_TASK -> "Resume"
        DialDevActionKind.REQUEST_CHECKPOINT -> "Request checkpoint"
        DialDevActionKind.REQUEST_REVIEW -> "Request review"
        DialDevActionKind.REVOKE_TASK -> "Revoke"
        DialDevActionKind.DECIDE -> "Decide"
        DialDevActionKind.PAUSE_MISSION -> "Pause mission"
        DialDevActionKind.RESUME_MISSION -> "Resume mission"
        DialDevActionKind.REPRIORITISE -> "Reprioritise"
    }

    /**
     * §5: destructive actions go through `ApprovalSheet` with the consequence stated. Revoking
     * a task and rejecting an owner decision are destructive; every other control is
     * reversible by its own opposite (pause/resume) or only asks DIAL for something.
     */
    fun isDestructive(kind: DialDevActionKind, params: Map<String, String> = emptyMap()): Boolean = when (kind) {
        DialDevActionKind.REVOKE_TASK -> true
        DialDevActionKind.DECIDE -> params["decision"]?.lowercase() == "reject"
        DialDevActionKind.STEER_TASK,
        DialDevActionKind.PAUSE_TASK_SAFE,
        DialDevActionKind.RESUME_TASK,
        DialDevActionKind.REQUEST_CHECKPOINT,
        DialDevActionKind.REQUEST_REVIEW,
        DialDevActionKind.PAUSE_MISSION,
        DialDevActionKind.RESUME_MISSION,
        DialDevActionKind.REPRIORITISE,
        -> false
    }
}

/** The body of `POST /v1/dial-dev/actions`. Built only through [build]. */
data class DialDevActionRequest(
    val kind: DialDevActionKind,
    val target: DialDevActionTarget,
    val params: Map<String, String>,
    val idempotencyKey: String,
    val expectedProjectionRevision: String,
) {
    fun toJson(): JSONObject {
        val target = JSONObject()
        this.target.projectId?.takeIf { it.isNotBlank() }?.let { target.put("project_id", it) }
        this.target.taskId?.takeIf { it.isNotBlank() }?.let { target.put("task_id", it) }
        this.target.workspaceId?.takeIf { it.isNotBlank() }?.let { target.put("workspace_id", it) }
        this.target.decisionId?.takeIf { it.isNotBlank() }?.let { target.put("decision_id", it) }
        val params = JSONObject()
        this.params.forEach { (key, value) -> params.put(key, value) }
        // `owner_device_proof_ref` is not sent from here: the device proof travels as the
        // request's proof headers (`postProved`), and the VAN gateway, having verified it,
        // is the party that names it to DIAL.
        return JSONObject()
            .put("action", kind.name)
            .put("target", target)
            .put("params", params)
            .put("idempotency_key", idempotencyKey)
            .put("expected_projection_revision", expectedProjectionRevision)
    }

    companion object {
        /**
         * Refuses rather than guesses: no revision (nothing on screen came from DIAL, or the
         * phone is offline) → no action. A steer with no guidance → no action.
         */
        fun build(
            kind: DialDevActionKind,
            target: DialDevActionTarget,
            params: Map<String, String>,
            expectedProjectionRevision: String?,
            idempotencyKey: String,
        ): DialDevActionRequest? {
            val revision = expectedProjectionRevision?.trim().orEmpty()
            if (revision.isEmpty() || idempotencyKey.isBlank()) return null
            if (kind == DialDevActionKind.STEER_TASK && params["guidance"].isNullOrBlank()) return null
            if (kind == DialDevActionKind.DECIDE && params["decision"] !in setOf("approve", "reject")) return null
            return DialDevActionRequest(kind, target, params, idempotencyKey, revision)
        }
    }
}

/** Where one owner action stands, as far as VAN can honestly say. */
sealed class DialDevActionStatus {
    object Submitting : DialDevActionStatus()

    /** 202 from the gateway. Not done: DIAL has only accepted the request. */
    data class Accepted(val actionId: String) : DialDevActionStatus()

    /** The projection shows the action applied. */
    data class Applied(val actionId: String) : DialDevActionStatus()

    data class Rejected(val actionId: String?, val reason: String) : DialDevActionStatus()

    data class Superseded(val actionId: String) : DialDevActionStatus()

    /** 409 STALE_VIEW: the owner acted on an old view. Refetch, show, then allow a retry. */
    data class StaleView(val currentRevision: String?) : DialDevActionStatus()

    /** Not sent at all (offline, no revision, refused before sending). Nothing happened. */
    data class NotSent(val reason: String) : DialDevActionStatus()

    /**
     * The request may or may not have reached DIAL (the connection failed mid-flight).
     * Retrying with the same idempotency key is safe — DIAL will not apply it twice.
     */
    data class Unconfirmed(val reason: String) : DialDevActionStatus()
}

/** One action as the projection reports it (`data.actions[]`). */
data class ProjectedAction(val actionId: String, val state: String, val reason: String?)

object DialDevActionReducer {

    /** The gateway's answer to the POST. */
    fun onResponse(httpStatus: Int, body: String): DialDevActionStatus {
        val json = try {
            JSONObject(body)
        } catch (_: JSONException) {
            JSONObject()
        }
        return when {
            httpStatus == 409 -> DialDevActionStatus.StaleView(
                json.optString("projection_revision").takeIf { it.isNotBlank() }
                    ?: (json.opt("detail") as? JSONObject)?.optString("projection_revision")?.takeIf { it.isNotBlank() },
            )
            httpStatus in 200..299 -> {
                val actionId = json.optString("action_id").trim()
                val state = json.optString("state").trim().uppercase()
                when {
                    actionId.isEmpty() -> DialDevActionStatus.Unconfirmed("DIAL did not return an action id.")
                    state == "REJECTED" -> DialDevActionStatus.Rejected(actionId, json.optString("reason").ifBlank { "No reason given." })
                    // Even an immediate "APPLIED" in the POST answer waits for the projection:
                    // the projection, not the forwarder, is what says a thing happened.
                    else -> DialDevActionStatus.Accepted(actionId)
                }
            }
            httpStatus == 503 -> DialDevActionStatus.NotSent("DIAL is unreachable; the action was not forwarded.")
            else -> DialDevActionStatus.Rejected(
                null,
                DialDevScreenReducer.errorCode(body) ?: "The gateway refused the action ($httpStatus).",
            )
        }
    }

    /** Only an accepted action moves, and only on what the projection says about its id. */
    fun reconcile(current: DialDevActionStatus, projected: List<ProjectedAction>): DialDevActionStatus {
        val accepted = current as? DialDevActionStatus.Accepted ?: return current
        val seen = projected.firstOrNull { it.actionId == accepted.actionId } ?: return current
        return when (seen.state.trim().uppercase()) {
            "APPLIED" -> DialDevActionStatus.Applied(accepted.actionId)
            "REJECTED" -> DialDevActionStatus.Rejected(accepted.actionId, seen.reason?.ifBlank { null } ?: "No reason given.")
            "SUPERSEDED" -> DialDevActionStatus.Superseded(accepted.actionId)
            else -> current
        }
    }

    fun parseProjected(data: JSONObject): List<ProjectedAction> =
        data.optJSONArray("actions").objects().mapNotNull { item ->
            val id = item.optString("action_id").trim()
            if (id.isEmpty()) null else ProjectedAction(id, item.optString("state"), item.optString("reason").takeIf { it.isNotBlank() })
        }

    /** Whether the screen should keep refetching to learn the outcome. */
    fun isPending(status: DialDevActionStatus): Boolean = when (status) {
        DialDevActionStatus.Submitting, is DialDevActionStatus.Accepted -> true
        is DialDevActionStatus.Applied,
        is DialDevActionStatus.Rejected,
        is DialDevActionStatus.Superseded,
        is DialDevActionStatus.StaleView,
        is DialDevActionStatus.NotSent,
        is DialDevActionStatus.Unconfirmed,
        -> false
    }

    /**
     * The row's caption. Deliberately never "done"/"passed": an applied *action* (e.g. a
     * pause) says only that DIAL applied it. Whether the *task* passed is the task's own state.
     */
    fun caption(kind: DialDevActionKind, status: DialDevActionStatus): String {
        val verb = DialDevActionPolicy.label(kind)
        return when (status) {
            DialDevActionStatus.Submitting -> "$verb · sending"
            is DialDevActionStatus.Accepted -> "$verb · ACCEPTED · pending"
            is DialDevActionStatus.Applied -> "$verb · applied by DIAL"
            is DialDevActionStatus.Rejected -> "$verb · rejected: ${status.reason}"
            is DialDevActionStatus.Superseded -> "$verb · superseded by a later action"
            is DialDevActionStatus.StaleView -> "$verb · not sent: the view changed. Check the current state, then try again."
            is DialDevActionStatus.NotSent -> "$verb · not sent: ${status.reason}"
            is DialDevActionStatus.Unconfirmed -> "$verb · unconfirmed: ${status.reason} Retrying is safe."
        }
    }

    fun role(status: DialDevActionStatus): String = when (status) {
        DialDevActionStatus.Submitting -> StatusSemantics.ROLE_MONITOR
        is DialDevActionStatus.Accepted -> StatusSemantics.ROLE_COGNITION
        is DialDevActionStatus.Applied -> StatusSemantics.ROLE_ENGAGED
        is DialDevActionStatus.Rejected -> StatusSemantics.ROLE_CRITICAL
        is DialDevActionStatus.Superseded -> StatusSemantics.ROLE_DISABLED
        is DialDevActionStatus.StaleView -> StatusSemantics.ROLE_EVENT_RISK
        is DialDevActionStatus.NotSent -> StatusSemantics.ROLE_EVENT_RISK
        is DialDevActionStatus.Unconfirmed -> StatusSemantics.ROLE_EVENT_RISK
    }

    /**
     * Whether a retry is offered, and whether it must reuse the idempotency key. A stale-view
     * retry is a *new* decision against a new revision, so it gets a new key; an unconfirmed
     * send is the *same* decision, so it keeps its key.
     */
    fun retry(status: DialDevActionStatus): RetryMode = when (status) {
        is DialDevActionStatus.Unconfirmed -> RetryMode.SAME_KEY
        is DialDevActionStatus.StaleView, is DialDevActionStatus.NotSent, is DialDevActionStatus.Rejected -> RetryMode.NEW_KEY
        DialDevActionStatus.Submitting,
        is DialDevActionStatus.Accepted,
        is DialDevActionStatus.Applied,
        is DialDevActionStatus.Superseded,
        -> RetryMode.NONE
    }

    enum class RetryMode { NONE, SAME_KEY, NEW_KEY }
}
