package com.dial.van.trading

import kotlinx.serialization.json.JsonObject

/**
 * Pure closure predicates for owner strategy promotion.
 *
 * Transport success is never promotion success. A receipt must be bound to the
 * exact candidate and carry durable ledger evidence; then the old parent
 * certificate must disappear from the authoritative promotion-candidate view.
 */
object StrategyPromotionVerification {

    fun receiptMatches(
        candidate: StrategyPromotionCandidate,
        body: JsonObject?,
    ): Boolean {
        if (body == null || body.bool("promoted") != true) return false
        val newCapsule = body.str("capsule_hash")
        return body.str("strategy_id") == candidate.strategyId &&
            body.str("to") == candidate.targetState &&
            body.str("validation_hash") == candidate.validationHash &&
            !newCapsule.isNullOrBlank() &&
            newCapsule != candidate.capsuleHash &&
            !body.str("event_hash").isNullOrBlank()
    }

    fun oldParentStillOffered(
        candidate: StrategyPromotionCandidate,
        refreshed: List<StrategyPromotionCandidate>,
    ): Boolean = refreshed.any {
        it.strategyId == candidate.strategyId &&
            it.validationHash == candidate.validationHash &&
            it.capsuleHash == candidate.capsuleHash
    }

    fun verified(
        candidate: StrategyPromotionCandidate,
        receipt: JsonObject?,
        refreshed: List<StrategyPromotionCandidate>,
    ): Boolean = receiptMatches(candidate, receipt) &&
        !oldParentStillOffered(candidate, refreshed)
}
