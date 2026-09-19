package com.dial.van.status

/**
 * What VAN tells the owner about a piece of work.
 *
 * Finding P0-EXEC-003: [com.dial.van.control.VanCommandController] mapped gateway statuses
 * with a `when` whose last branch was `else -> ACCEPTED`. Every status it did not
 * recognise — including every status the gateway grew after the controller was written —
 * read to the owner as "under way". It also answered `unverifiable`,
 * `verification_failed` and `partial_success` with the single word FAILED, which is three
 * different situations given one wrong answer.
 *
 * This file is the device's half of one projection. The gateway's half is
 * `backend/van_gateway/coherence/owner_status.py` and `wire_status.py`, and
 * `backend/tests/test_owner_status_kotlin_contract.py` parses this file and fails CI if
 * the two ever disagree. That test is the reason the tables below are written plainly,
 * one `to` per line, rather than in whatever form would be shortest.
 *
 * Deliberately free of Android imports: this is decision logic, and keeping it pure is
 * what lets it be compiled and executed by `android/verification`, which has no Android
 * toolchain.
 */
enum class OwnerWorkStatus {
    WAITING_ON_YOU,
    WORKING,
    WAITING_ON_SOMETHING_ELSE,
    DONE,
    DONE_WITH_GAPS,
    COULD_NOT_VERIFY,
    FAILED,
    STOPPED,
    REFUSED,
    UNKNOWN,
}

object OwnerStatusProjection {

    /** One sentence per status, in the second person. Must match the gateway's wording. */
    val sentence: Map<OwnerWorkStatus, String> = mapOf(
        OwnerWorkStatus.WAITING_ON_YOU to "Waiting for you",
        OwnerWorkStatus.WORKING to "Working on it",
        OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE to "Waiting on something outside VAN",
        OwnerWorkStatus.DONE to "Done, and checked",
        OwnerWorkStatus.DONE_WITH_GAPS to "Partly done — some of it did not happen",
        OwnerWorkStatus.COULD_NOT_VERIFY to "Finished, but VAN could not confirm it worked",
        OwnerWorkStatus.FAILED to "Did not work",
        OwnerWorkStatus.STOPPED to "Stopped before finishing",
        OwnerWorkStatus.REFUSED to "Refused — VAN would not do this",
        OwnerWorkStatus.UNKNOWN to "VAN does not know the state of this",
    )

    /** Statuses that belong in the owner's attention queue rather than in a list. */
    val needsOwner: Set<OwnerWorkStatus> = setOf(
        OwnerWorkStatus.WAITING_ON_YOU,
        OwnerWorkStatus.DONE_WITH_GAPS,
        OwnerWorkStatus.COULD_NOT_VERIFY,
        OwnerWorkStatus.FAILED,
        OwnerWorkStatus.REFUSED,
        OwnerWorkStatus.UNKNOWN,
    )

    /** Statuses that mean the work is over, however it ended. */
    val finished: Set<OwnerWorkStatus> = setOf(
        OwnerWorkStatus.DONE,
        OwnerWorkStatus.DONE_WITH_GAPS,
        OwnerWorkStatus.COULD_NOT_VERIFY,
        OwnerWorkStatus.FAILED,
        OwnerWorkStatus.STOPPED,
        OwnerWorkStatus.REFUSED,
    )

    /** The synchronous answer to POST /v1/commands. */
    val commandResult: Map<String, OwnerWorkStatus> = mapOf(
        "accepted" to OwnerWorkStatus.WORKING,
        "in_flight" to OwnerWorkStatus.WORKING,
        "approval_required" to OwnerWorkStatus.WAITING_ON_YOU,
        "degraded" to OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE,
        "denied" to OwnerWorkStatus.REFUSED,
        "rejected_untrusted" to OwnerWorkStatus.REFUSED,
        "expired" to OwnerWorkStatus.STOPPED,
        "conflict" to OwnerWorkStatus.WAITING_ON_YOU,
    )

    /** Mission states, which arrive later over the event stream. */
    val missionState: Map<String, OwnerWorkStatus> = mapOf(
        "CAPTURED" to OwnerWorkStatus.WORKING,
        "UNDERSTOOD" to OwnerWorkStatus.WORKING,
        "PLANNED" to OwnerWorkStatus.WORKING,
        "AUTHORIZED" to OwnerWorkStatus.WORKING,
        "RUNNING" to OwnerWorkStatus.WORKING,
        "WAITING_EXTERNAL" to OwnerWorkStatus.WAITING_ON_SOMETHING_ELSE,
        "WAITING_FOR_OWNER" to OwnerWorkStatus.WAITING_ON_YOU,
        "RESUME_AUTHORIZED" to OwnerWorkStatus.WORKING,
        "VERIFYING" to OwnerWorkStatus.WORKING,
        "VERIFIED_SUCCESS" to OwnerWorkStatus.DONE,
        "PARTIAL_SUCCESS" to OwnerWorkStatus.DONE_WITH_GAPS,
        "FAILED" to OwnerWorkStatus.FAILED,
        "CANCELLED" to OwnerWorkStatus.STOPPED,
        "EXPIRED" to OwnerWorkStatus.STOPPED,
        "BLOCKED_POLICY" to OwnerWorkStatus.REFUSED,
        "BLOCKED_UNSAFE" to OwnerWorkStatus.REFUSED,
        "UNVERIFIABLE" to OwnerWorkStatus.COULD_NOT_VERIFY,
    )

    /**
     * The owner status for a command result.
     *
     * There is no benign default. A status this build does not know is UNKNOWN, which the
     * owner reads as "VAN does not know the state of this" and which the attention queue
     * picks up. Guessing optimistically is how every unrecognised state became ACCEPTED.
     */
    fun fromCommandResult(status: String?): OwnerWorkStatus =
        commandResult[status?.trim()?.lowercase().orEmpty()] ?: OwnerWorkStatus.UNKNOWN

    fun fromMissionState(state: String?): OwnerWorkStatus =
        missionState[state?.trim()?.uppercase().orEmpty()] ?: OwnerWorkStatus.UNKNOWN

    fun sentenceFor(status: OwnerWorkStatus): String =
        sentence[status] ?: sentence.getValue(OwnerWorkStatus.UNKNOWN)

    fun needsOwner(status: OwnerWorkStatus): Boolean = status in needsOwner

    fun isFinished(status: OwnerWorkStatus): Boolean = status in finished
}
