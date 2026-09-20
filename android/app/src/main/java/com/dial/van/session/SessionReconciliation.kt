package com.dial.van.session

/**
 * Rev 1.5 §20.12 — what the Gateway's account of this session means for what the phone
 * still holds.
 *
 * The sentence this file exists to make true: **a lost acknowledgement is not a lost
 * command, and a received command is not sent twice.** Both halves are failures of the
 * same decision, and both only happen on a network nobody can reproduce — the socket dies
 * in the gap between the Gateway writing the message down and the phone learning that it
 * did.
 *
 * ## What it replaced
 *
 * `adoptCursor` used to be three lines:
 *
 * ```
 * val states = resume.optJSONObject("command_states") ?: return
 * states.keys().forEach { messageId -> inFlight.remove(messageId) }
 * ```
 *
 * Two independent defects, neither visible in a passing suite:
 *
 *  1. **Wrong identity.** The phone sent `inFlight.keys` — *message* ids — as
 *     `pending_command_ids`, and the Gateway resolved each one as a *command* id against
 *     the mission table. A command id and a message id are different identities on the
 *     same envelope, so the lookup found nothing and every answer came back `UNKNOWN`.
 *  2. **Wrong consequence.** It then dropped every key it was given, including the
 *     `UNKNOWN`s. `UNKNOWN` is the Gateway saying *I have never heard of this*, which is
 *     the one answer that means resend. So a resume silently discarded every
 *     unacknowledged command the owner had issued — the precise outcome §20.12 exists to
 *     prevent — while reporting a successful reconciliation.
 *
 * The two cancelled out in every test: nothing was resent because nothing was known, and
 * nothing looked wrong because nothing was left behind.
 *
 * Pure, and separate from the socket for that reason: the case that matters is a resume
 * arriving with a partial answer, which no integration test on a healthy network produces.
 */
object SessionReconciliation {

    /**
     * The Gateway's answer for an identity it has never recorded.
     *
     * Spelled once here and compared against once below. The Gateway sends this string
     * rather than omitting the key, so that "I looked and found nothing" is distinguishable
     * from "I did not look" — and both must mean resend, which is why [verdictFor] treats
     * an absent key the same way.
     */
    const val UNKNOWN: String = "UNKNOWN"

    /** What the phone does with one thing it is still holding. */
    enum class Verdict {
        /**
         * The Gateway does not have it. Send it again, unchanged.
         *
         * Unchanged is the load-bearing word: the same `message_id` and the same
         * `idempotency_key`, so that if this is a *second* copy of something the Gateway
         * did receive but could not answer for, §20.12's admission recognises it and does
         * not run it twice.
         */
        RESEND,

        /**
         * The Gateway has it. Stop holding it, and forget it durably.
         *
         * Whatever happens to it now is the mission's business and reaches the owner as an
         * event. Re-sending would be the duplicate; holding it forever is the restart loop
         * where the same command is restored and re-delivered after every process death.
         */
        SETTLE,
    }

    /**
     * One identity's verdict.
     *
     * Absent and [UNKNOWN] are the same answer. Anything else — a mission state, or the
     * Gateway saying it admitted the message without opening a mission — means the
     * Gateway holds it.
     */
    fun verdictFor(state: String?): Verdict =
        if (state == null || state == UNKNOWN) Verdict.RESEND else Verdict.SETTLE

    /**
     * The identity to ask the Gateway about, and to match its answer by.
     *
     * The command id when there is one, the message id otherwise. One function so the
     * question and the answer cannot drift apart — asking by one identity and matching by
     * the other is exactly the defect described above, and it is invisible unless the two
     * are produced by the same line of code.
     *
     * The fallback is safe in the direction that matters: a message id the Gateway cannot
     * resolve comes back `UNKNOWN`, which resends, and the resend is de-duplicated by the
     * idempotency key. The opposite fallback — treating an unresolvable id as settled —
     * would drop the owner's command.
     */
    fun identityOf(messageId: String, commandId: String?): String =
        commandId?.takeIf { it.isNotBlank() && it != messageId } ?: messageId

    /** One thing the phone is still holding, reduced to the two facts this needs. */
    data class Pending(val messageId: String, val commandId: String?)

    /**
     * Split what the phone holds into what it must send again and what it may let go of.
     *
     * Order is preserved within each list: the outbox is a queue and the owner's commands
     * were issued in an order, so a reconciliation that reordered them would change what
     * the owner asked for.
     */
    data class Plan(val resend: List<String>, val settle: List<String>)

    fun plan(pending: List<Pending>, states: Map<String, String>): Plan {
        val resend = mutableListOf<String>()
        val settle = mutableListOf<String>()
        for (item in pending) {
            val identity = identityOf(item.messageId, item.commandId)
            when (verdictFor(states[identity])) {
                Verdict.RESEND -> resend += item.messageId
                Verdict.SETTLE -> settle += item.messageId
            }
        }
        return Plan(resend = resend, settle = settle)
    }
}
