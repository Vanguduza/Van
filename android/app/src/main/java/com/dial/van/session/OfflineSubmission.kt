package com.dial.van.session

/**
 * Rev 1.5 §§20.14, 20.15 — what happens to an owner command whose dispatch failed.
 *
 * The decision, separated from the catch block it used to live in. `VanCommandController`
 * appended "Command dispatch failed" and stopped: nothing stored the command, nothing
 * retried it, and the owner's instruction given in a tunnel was gone. That is the exact
 * failure §20.14 exists to prevent, and it was reached by the one path nobody had
 * connected to the outbox (P0-SESS-011).
 *
 * Pure, because the two rules that matter here are the ones no integration test produces
 * on demand:
 *
 *  * **A refusal is not a failure.** If the Gateway answered — any HTTP status — the
 *    command arrived and was declined for a reason the owner should hear. Storing it
 *    would mean replaying, later and silently, something the Gateway has already said no
 *    to. Only a command that never arrived may be held.
 *  * **§20.14's last sentence.** An A4 or A5 is never stored, so it cannot execute hours
 *    later because connectivity returned. The classification is [OutboxPolicy]'s, called
 *    here rather than re-stated, so there is one rule rather than two that agree.
 *
 * What the owner is told is part of the verdict rather than left to the caller. Three
 * outcomes that feel similar to write and are completely different to receive — *saved*,
 * *saved but I'll ask again*, *not sent and not saved* — and a caller choosing its own
 * wording is how the third one ends up reading like the first.
 */
object OfflineSubmission {

    /** What to do, and what to say. */
    sealed interface Verdict {

        /** The owner's own words, for an owner-readable line. */
        val ownerMessage: String

        /**
         * Hold it in §20.14's outbox and send it when a path returns.
         *
         * [needsReconfirm] when the command only means anything with the owner present:
         * it is stored, and the owner is asked again before it runs rather than having it
         * happen on their behalf at a moment they have forgotten about.
         */
        data class Store(
            override val ownerMessage: String,
            val needsReconfirm: Boolean,
        ) : Verdict

        /**
         * Not stored. The owner is told, and that is the whole of it.
         *
         * Covers both "the Gateway said no" and "this is not the kind of thing that may
         * wait", which are different reasons and produce different sentences.
         */
        data class Drop(override val ownerMessage: String) : Verdict
    }

    /**
     * @param gatewayAnswered true when an HTTP response came back, whatever its status.
     *   A timeout, a DNS failure or a dropped connection is false — those mean the
     *   command never arrived, which is the only case that may be held.
     * @param failureSummary what to show when there is nothing to store. Already trimmed
     *   by the caller; this does not shorten it, because a truncation rule in two places
     *   is a truncation rule that will disagree with itself.
     */
    fun decide(
        actionClass: String,
        requiresLiveOwnerContext: Boolean,
        gatewayAnswered: Boolean,
        failureSummary: String,
    ): Verdict {
        if (gatewayAnswered) {
            // It arrived. Whatever happened next is an answer, not a lost command.
            return Verdict.Drop("Not done: $failureSummary")
        }
        return when (OutboxPolicy.classify(actionClass, requiresLiveOwnerContext)) {
            CommandStorability.NEVER_STORE -> Verdict.Drop(
                // Deliberately not "I'll try again". An A4 is irreversible and an A5 is
                // approval-bearing; the honest sentence is that it did not happen and
                // the owner has to ask again when they are online.
                "Not sent — this one needs you online. Nothing was changed.",
            )
            CommandStorability.REQUIRE_RECONFIRM_ON_RECONNECT -> Verdict.Store(
                // Deliberately not "I'll check with you before I send it". §20.14 stores
                // this class and §20.15 says the owner is asked again before it runs —
                // and nothing asks yet (P1-SESS-012). The sentence says what is true now:
                // it is kept, and it will not go out on its own.
                "Saved, and held. This one won't be sent without you.",
                needsReconfirm = true,
            )
            CommandStorability.SAFE_TO_RETRY, CommandStorability.STORE_UNTIL_TTL ->
                Verdict.Store("Saved — I'll send this when you're back online.", needsReconfirm = false)
        }
    }
}
