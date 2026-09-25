package com.dial.van.command.jev

import com.dial.van.gateway.VanGatewayClient

class JevRepository(private val gateway: VanGatewayClient) {
    suspend fun snapshot(): JevServiceSnapshot =
        JevJson.snapshot(gateway.jevStatus(), gateway.jevHealth(), gateway.jevProvider())

    suspend fun activity(projectId: String, limit: Int = 100): List<JevActivityItem> =
        JevJson.activity(gateway.jevActivity(projectId, limit))

    suspend fun performance(projectId: String, moduleId: String? = null): JevPerformance =
        JevJson.performance(gateway.jevPerformance(projectId, moduleId))

    suspend fun contribution(projectId: String, moduleId: String): JevContribution =
        JevJson.contribution(moduleId, gateway.jevContribution(projectId, moduleId))

    suspend fun safety(projectId: String, moduleId: String): JevSafetySnapshot =
        JevJson.safety(gateway.jevSafety(projectId, moduleId))

    suspend fun evaluationProposals(moduleId: String? = null, limit: Int = 100): List<JevEvaluationProposal> =
        JevJson.proposals(gateway.jevEvaluationProposals(moduleId, limit))

    suspend fun evaluationReviews(proposalId: String? = null, limit: Int = 100): List<JevEvaluationReview> =
        JevJson.reviews(gateway.jevEvaluationReviews(proposalId, limit))

    suspend fun evaluationCandidates(moduleId: String? = null, limit: Int = 100): List<JevCandidateRevision> =
        JevJson.candidates(gateway.jevEvaluationCandidates(moduleId, limit))
}
