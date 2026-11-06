package com.dial.van.session

/** Original-result evidence controls recovery; an unanswered lookup never proves absence. */
object SessionReconciliation {

    const val UNKNOWN: String = "UNKNOWN"
    const val RESULT_PENDING: String = "RESULT_PENDING"
    enum class Verdict { RESEND, SETTLE, HOLD }

    // These are existing mission/admission handoffs, not claims of native success.
    private val ownedResults = setOf("CAPTURED", "UNDERSTOOD", "PLANNED", "AUTHORIZED", "RUNNING",
        "WAITING_EXTERNAL", "WAITING_FOR_OWNER", "RESUME_AUTHORIZED", "VERIFYING", "VERIFIED_SUCCESS",
        "PARTIAL_SUCCESS", "FAILED", "CANCELLED", "EXPIRED", "BLOCKED_POLICY", "BLOCKED_UNSAFE",
        "UNVERIFIABLE", "ADMITTED", "ALREADY_KNOWN", "ORIGINAL_COMPLETED")

    fun verdictFor(state: String?): Verdict = when (state) {
        in ownedResults -> Verdict.SETTLE
        else -> Verdict.HOLD
    }

    /** Preserve both original identities; neither is a replacement request key. */
    fun identityOf(messageId: String, commandId: String?): String =
        commandId?.takeIf { it.isNotBlank() && it != messageId } ?: messageId

    /** One thing the phone is still holding, reduced to the two facts this needs. */
    data class Pending(val messageId: String, val commandId: String?, val neverDispatched: Boolean = false,
                       val kind: String? = null, val sessionOnlyOrigin: Boolean = false,
                       val sameOriginalSession: Boolean = false, val verifiedOriginalRead: Boolean = false)

    /**
     * Split what the phone holds into what it must send again and what it may let go of.
     *
     * Order is preserved within each list: the outbox is a queue and the owner's commands
     * were issued in an order, so a reconciliation that reordered them would change what
     * the owner asked for.
     */
    data class Plan(val resend: List<String>, val settle: List<String>, val hold: List<String> = emptyList())

    fun plan(pending: List<Pending>, states: Map<String, String>): Plan {
        val resend = mutableListOf<String>()
        val settle = mutableListOf<String>()
        val hold = mutableListOf<String>()
        for (item in pending) {
            val identity = identityOf(item.messageId, item.commandId)
            when (verdictFor(states[identity])) {
                Verdict.RESEND -> resend += item.messageId
                Verdict.SETTLE -> {
                    if (item.kind == "command.submit" && !item.neverDispatched &&
                        !(states[identity] == "ORIGINAL_COMPLETED" && item.verifiedOriginalRead))
                        hold += item.messageId else settle += item.messageId
                }
                Verdict.HOLD -> {
                    val state = states[identity]
                    val fresh = item.neverDispatched && (state == null || state == UNKNOWN)
                    // Existing non-command owners recover the SAME envelope through
                    // their writer/key+digest and idempotent effect owners (365-day
                    // admission retention vs the producer's 4-hour window). This is
                    // not proof of absence or permission to mint/re-execute a command.
                    val ownedTransportRecovery = item.sessionOnlyOrigin && item.sameOriginalSession &&
                        item.kind in setOf("mission.message", "mission.cancel", "decision.answer") &&
                        state in setOf(UNKNOWN, RESULT_PENDING)
                    if (fresh || ownedTransportRecovery) resend += item.messageId else hold += item.messageId
                }
            }
        }
        return Plan(resend = resend, settle = settle, hold = hold)
    }
}
