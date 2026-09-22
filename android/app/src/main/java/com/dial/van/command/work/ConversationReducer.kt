package com.dial.van.command.work

import com.dial.van.status.OwnerStatusProjection
import com.dial.van.status.OwnerWorkStatus
import com.dial.van.status.VanCommandStatus
import com.dial.van.status.commandStatusFor

/**
 * GAP-F-011 — the conversational surface never received the completed answer.
 *
 * `VanCommandController.recordResponse` stored the *synchronous* dispatch answer ("accepted")
 * as the VAN message and nothing polled `GET /v1/commands/{id}` afterwards, so an owner who
 * asked something in Work had to leave the conversation and open Missions/Activity to read
 * how it went — the chat thread itself never moved past "working on it".
 *
 * This is the pure half of the fix: whether a dispatched command's thread still needs
 * polling, and what `GET /v1/commands/{id}`'s JSON becomes once it answers. No Android
 * imports, so it is executed in `android/verification`; `VanCommandController.pollUnfinishedCommands`
 * is the one caller, on a 4s tick from the Work screen while any message is unfinished.
 */
object ConversationReducer {

    /** A dispatched command's status while its thread still needs to be re-asked about. */
    private val UNFINISHED: Set<VanCommandStatus> = setOf(
        VanCommandStatus.ACCEPTED,
        VanCommandStatus.IN_FLIGHT,
        VanCommandStatus.SUBMITTING,
        VanCommandStatus.QUEUED,
    )

    /** Whether a message carrying [commandId]/[status] should still be polled. */
    fun needsPolling(commandId: String?, status: VanCommandStatus?): Boolean =
        !commandId.isNullOrBlank() && status != null && status in UNFINISHED

    /** `GET /v1/commands/{id}`'s body, reduced to the four fields this reducer needs. */
    data class PollResult(
        val ownerStatus: String?,
        val sentence: String?,
        val finalOutcome: String?,
        val finished: Boolean,
    )

    data class Outcome(
        /** What to append to the thread as a new VAN message. */
        val text: String,
        val status: VanCommandStatus,
        /** Whether the caller should keep polling this command after this answer. */
        val keepPolling: Boolean,
    )

    /**
     * What a poll becomes.
     *
     * `final_outcome` — the Hermes/orchestrator summary GAP-F-011 exists to surface — wins
     * over the generic per-status [sentence] once the gateway says the work is finished and
     * actually gave one; before that, or when it did not, the per-status sentence (or this
     * device's own fallback, [OwnerStatusProjection.sentenceFor]) is what the owner reads.
     */
    fun outcomeFor(poll: PollResult): Outcome {
        val owner = poll.ownerStatus
            ?.let { runCatching { OwnerWorkStatus.valueOf(it) }.getOrNull() }
            ?: OwnerWorkStatus.UNKNOWN
        val status = commandStatusFor(owner)
        val text = if (poll.finished && !poll.finalOutcome.isNullOrBlank()) {
            poll.finalOutcome
        } else {
            poll.sentence?.takeIf { it.isNotBlank() } ?: OwnerStatusProjection.sentenceFor(owner)
        }
        return Outcome(text = text, status = status, keepPolling = status in UNFINISHED)
    }

    /** The "VAN did not know: …" line (GAP-F-019's `context_gaps`), or null when there is none. */
    fun contextGapsSentence(labels: List<String>): String? {
        val clean = labels.filter { it.isNotBlank() }
        if (clean.isEmpty()) return null
        return "VAN did not know: ${clean.joinToString("; ")}"
    }
}
